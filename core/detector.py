"""Anomaly detection engine for BGP routing telemetry."""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import numpy as np
from sklearn.ensemble import IsolationForest

from api.models import Anomaly


class AnomalyDetector:
    """Detect routing anomalies using statistical and ML methods."""

    def __init__(
        self,
        lookback_days: int = 7,
        z_score_threshold: float = 3.0,
        dedup_window_seconds: int = 300,
        isolation_forest_contamination: float = 0.05,
    ) -> None:
        self.lookback_days = lookback_days
        self.z_score_threshold = z_score_threshold
        self.dedup_window_seconds = dedup_window_seconds
        self.isolation_forest_contamination = isolation_forest_contamination

    async def detect_anomalies(
        self, speaker_id: str, influx=None, db=None
    ) -> List[Dict[str, Any]]:
        """Run the full anomaly detection pipeline for a speaker."""
        from tasks.ingestion import dispatch_alerts_task

        historical = influx.query_route_stats(
            speaker_id, time_range=f"{self.lookback_days}d"
        )
        if not historical:
            return []

        baseline = self._compute_baseline(historical)
        current_window = influx.query_route_stats(speaker_id, time_range="5m")
        current = current_window[-1] if current_window else {}
        now = datetime.now(timezone.utc)

        zscore_anomalies = self._detect_z_score_anomalies(current, baseline)
        ml_anomalies = self._detect_ml_anomalies(historical, current)
        correlated = self._find_correlated_failures(speaker_id, now, db=db)

        all_candidates = zscore_anomalies + ml_anomalies + correlated
        speaker_uuid = uuid.UUID(str(speaker_id))
        existing = (
            db.query(Anomaly)
            .filter(
                Anomaly.speaker_id == speaker_uuid,
                Anomaly.resolved_at.is_(None),
            )
            .all()
        )
        new_anomalies = self._deduplicate(all_candidates, existing)

        created = []
        for a in new_anomalies:
            record = Anomaly(
                speaker_id=speaker_uuid,
                anomaly_type=a["anomaly_type"],
                severity=a["severity"],
                prefix=a.get("prefix"),
                neighbor_ip=a.get("neighbor_ip"),
                detected_at=now,
                details=a.get("details", {}),
            )
            db.add(record)
            db.flush()
            created.append(record)

        db.commit()

        for record in created:
            dispatch_alerts_task.delay(str(record.id))

        return [
            {
                "id": str(r.id),
                "anomaly_type": r.anomaly_type,
                "severity": r.severity,
                "prefix": r.prefix,
                "detected_at": r.detected_at.isoformat(),
                "details": r.details,
            }
            for r in created
        ]

    def _compute_baseline(self, metrics: List[Dict[str, Any]]) -> Dict[str, float]:
        """Compute baseline statistics from historical metric points."""
        if not metrics:
            return {
                k: 0.0
                for k in [
                    "mean_flap_rate",
                    "std_flap_rate",
                    "mean_route_count",
                    "std_route_count",
                    "mean_path_diversity",
                    "std_path_diversity",
                    "p95_flap_rate",
                ]
            }

        flap_arr = np.array([m.get("flap_count", 0) for m in metrics], dtype=float)
        route_arr = np.array([m.get("route_count", 0) for m in metrics], dtype=float)
        path_arr = np.array([m.get("path_diversity", 0) for m in metrics], dtype=float)

        return {
            "mean_flap_rate": float(np.mean(flap_arr)),
            "std_flap_rate": float(np.std(flap_arr)) or 1.0,
            "mean_route_count": float(np.mean(route_arr)),
            "std_route_count": float(np.std(route_arr)) or 1.0,
            "mean_path_diversity": float(np.mean(path_arr)),
            "std_path_diversity": float(np.std(path_arr)) or 1.0,
            "p95_flap_rate": float(np.percentile(flap_arr, 95)),
        }

    def _detect_z_score_anomalies(
        self,
        current_metrics: Dict[str, Any],
        baseline: Dict[str, float],
    ) -> List[Dict[str, Any]]:
        """Detect statistical anomalies via Z-score on flap_rate."""
        if not current_metrics:
            return []

        current_flap = float(current_metrics.get("flap_count", 0))
        mean = baseline["mean_flap_rate"]
        std = baseline["std_flap_rate"] or 1.0
        z_score = (current_flap - mean) / std

        if z_score <= self.z_score_threshold:
            return []

        return [
            {
                "anomaly_type": "UNUSUAL_CHURN",
                "severity": self._compute_severity(z_score),
                "prefix": current_metrics.get("prefix"),
                "neighbor_ip": current_metrics.get("neighbor_ip"),
                "details": {
                    "z_score": round(z_score, 3),
                    "current_flap_rate": current_flap,
                    "baseline_mean": mean,
                    "baseline_std": std,
                    "p95_flap_rate": baseline.get("p95_flap_rate"),
                    "model": "z_score",
                },
            }
        ]

    def _detect_ml_anomalies(
        self,
        historical_metrics: List[Dict[str, Any]],
        current_metrics: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """Detect multivariate anomalies using IsolationForest."""

        def _featurize(m: Dict[str, Any]) -> List[float]:
            return [
                float(m.get("flap_count", 0)),
                float(m.get("route_count", 0)),
                float(m.get("path_diversity", 0)),
                float(m.get("convergence_ms", 0)),
                float(m.get("as_path_length", 0)),
            ]

        if len(historical_metrics) < 10 or not current_metrics:
            return []

        X = np.array([_featurize(m) for m in historical_metrics])
        iso = IsolationForest(
            contamination=self.isolation_forest_contamination,
            random_state=42,
        )
        iso.fit(X)

        x_new = np.array([_featurize(current_metrics)])
        label = iso.predict(x_new)[0]
        score = iso.decision_function(x_new)[0]

        if label != -1:
            return []

        return [
            {
                "anomaly_type": "UNUSUAL_CHURN",
                "severity": "WARNING",
                "prefix": current_metrics.get("prefix"),
                "neighbor_ip": current_metrics.get("neighbor_ip"),
                "details": {
                    "isolation_forest_score": round(float(score), 4),
                    "feature_vector": _featurize(current_metrics),
                    "model": "isolation_forest",
                },
            }
        ]

    def _find_correlated_failures(
        self,
        speaker_id: str,
        timestamp: datetime,
        window_seconds: int = 60,
        db=None,
        correlated_prefix_threshold: int = 5,
    ) -> List[Dict[str, Any]]:
        """Find prefixes simultaneously withdrawn within window_seconds."""
        from api.models import RouteEvent

        window_start = timestamp - timedelta(seconds=window_seconds)
        window_end = timestamp + timedelta(seconds=window_seconds)
        speaker_uuid = uuid.UUID(str(speaker_id))

        withdrawals = (
            db.query(RouteEvent)
            .filter(
                RouteEvent.speaker_id == speaker_uuid,
                RouteEvent.event_type == "WITHDRAW",
                RouteEvent.timestamp >= window_start,
                RouteEvent.timestamp <= window_end,
            )
            .all()
        )

        if len(withdrawals) < correlated_prefix_threshold:
            return []

        affected_prefixes = list({r.prefix for r in withdrawals if r.prefix})

        return [
            {
                "anomaly_type": "CORRELATED_FAILURE",
                "severity": "CRITICAL",
                "prefix": None,
                "details": {
                    "affected_prefix_count": len(affected_prefixes),
                    "affected_prefixes": affected_prefixes[:20],
                    "window_seconds": window_seconds,
                    "model": "correlation",
                },
            }
        ]

    def _deduplicate(
        self,
        anomalies: List[Dict[str, Any]],
        existing_anomalies: Optional[List[Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Remove duplicate anomalies within the dedup window."""
        seen_keys: set[tuple] = set()
        now = datetime.now(timezone.utc)
        window = timedelta(seconds=self.dedup_window_seconds)

        if existing_anomalies:
            for ex in existing_anomalies:
                detected = ex.detected_at
                if detected.tzinfo is None:
                    detected = detected.replace(tzinfo=timezone.utc)
                if (now - detected) <= window:
                    seen_keys.add((ex.anomaly_type, ex.prefix))

        result = []
        for a in anomalies:
            key = (a["anomaly_type"], a.get("prefix"))
            if key not in seen_keys:
                seen_keys.add(key)
                result.append(a)

        return result

    @staticmethod
    def _compute_severity(z_score: float) -> str:
        """Map Z-score to severity string."""
        if z_score >= 5.0:
            return "CRITICAL"
        elif z_score >= 3.0:
            return "WARNING"
        return "INFO"
