"""Unit tests for the anomaly detection engine."""
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import numpy as np
import pytest

from core.detector import AnomalyDetector


def _make_metrics(flap_counts: list, route_count: int = 1000) -> list:
    """Build minimal metric dicts from a list of flap counts."""
    return [
        {
            "time": f"2024-01-01T00:{i:02d}:00Z",
            "flap_count": fc,
            "route_count": route_count,
            "path_diversity": 2.0,
            "convergence_ms": 50.0,
            "as_path_length": 3,
        }
        for i, fc in enumerate(flap_counts)
    ]


class TestBaseline:
    def test_compute_baseline_mean_std(self):
        detector = AnomalyDetector()
        data = [2, 4, 4, 4, 5, 5, 7, 9]
        metrics = _make_metrics(data)
        baseline = detector._compute_baseline(metrics)
        assert abs(baseline["mean_flap_rate"] - np.mean(data)) < 0.01
        assert "std_flap_rate" in baseline
        assert "p95_flap_rate" in baseline
        assert baseline["p95_flap_rate"] >= baseline["mean_flap_rate"]

    def test_empty_metrics_handled(self):
        detector = AnomalyDetector()
        baseline = detector._compute_baseline([])
        assert baseline["mean_flap_rate"] == 0.0
        assert baseline["p95_flap_rate"] == 0.0

    def test_single_point_no_std_error(self):
        detector = AnomalyDetector()
        baseline = detector._compute_baseline(_make_metrics([5]))
        assert baseline["mean_flap_rate"] == 5.0


class TestZScoreDetection:
    def test_detects_high_flap_spike(self):
        detector = AnomalyDetector(z_score_threshold=3.0)
        normal = [1, 1, 2, 1, 1, 2, 1, 1, 2, 1]
        baseline = detector._compute_baseline(_make_metrics(normal))
        current = _make_metrics([50])[0]
        result = detector._detect_z_score_anomalies(current, baseline)
        assert len(result) == 1
        assert result[0]["anomaly_type"] == "UNUSUAL_CHURN"
        assert result[0]["details"]["z_score"] > 3.0

    def test_no_anomaly_within_threshold(self):
        detector = AnomalyDetector(z_score_threshold=3.0)
        baseline = detector._compute_baseline(_make_metrics([10] * 50))
        current = _make_metrics([12])[0]
        result = detector._detect_z_score_anomalies(current, baseline)
        assert result == []

    def test_severity_critical_above_5_sigma(self):
        detector = AnomalyDetector(z_score_threshold=3.0)
        baseline = detector._compute_baseline(_make_metrics([2] * 100))
        current = _make_metrics([10000])[0]
        result = detector._detect_z_score_anomalies(current, baseline)
        assert any(r["severity"] == "CRITICAL" for r in result)

    def test_compute_severity_mapping(self):
        assert AnomalyDetector._compute_severity(2.9) == "INFO"
        assert AnomalyDetector._compute_severity(3.0) == "WARNING"
        assert AnomalyDetector._compute_severity(4.9) == "WARNING"
        assert AnomalyDetector._compute_severity(5.0) == "CRITICAL"
        assert AnomalyDetector._compute_severity(9.0) == "CRITICAL"


class TestIsolationForestDetection:
    def test_detects_multivariate_anomaly(self):
        detector = AnomalyDetector(isolation_forest_contamination=0.2)
        historical = [
            {
                "flap_count": 2 + (i % 3),
                "route_count": 1000 + (i % 5),
                "path_diversity": 2.0,
                "convergence_ms": 50.0,
                "as_path_length": 3,
            }
            for i in range(50)
        ]
        current = {
            "flap_count": 9999,
            "route_count": 50,
            "path_diversity": 2.0,
            "convergence_ms": 50.0,
            "as_path_length": 3,
        }
        result = detector._detect_ml_anomalies(historical, current)
        assert len(result) == 1
        assert result[0]["anomaly_type"] == "UNUSUAL_CHURN"
        assert "isolation_forest_score" in result[0]["details"]

    def test_no_false_positive_on_normal(self):
        detector = AnomalyDetector(isolation_forest_contamination=0.01)
        historical = _make_metrics([5] * 100)
        current = _make_metrics([5])[0]
        result = detector._detect_ml_anomalies(historical, current)
        assert result == []

    def test_insufficient_history_returns_empty(self):
        detector = AnomalyDetector()
        historical = _make_metrics([5] * 5)
        current = _make_metrics([9999])[0]
        result = detector._detect_ml_anomalies(historical, current)
        assert result == []


class TestDeduplication:
    def test_deduplicates_same_anomaly_in_window(self):
        detector = AnomalyDetector(dedup_window_seconds=300)

        existing = MagicMock()
        existing.anomaly_type = "UNUSUAL_CHURN"
        existing.prefix = "10.0.0.0/24"
        existing.detected_at = datetime.now(timezone.utc) - timedelta(seconds=60)

        candidates = [{"anomaly_type": "UNUSUAL_CHURN", "prefix": "10.0.0.0/24"}]
        result = detector._deduplicate(candidates, [existing])
        assert result == []

    def test_different_prefix_not_deduped(self):
        detector = AnomalyDetector(dedup_window_seconds=300)
        candidates = [
            {"anomaly_type": "UNUSUAL_CHURN", "prefix": "10.0.0.0/24"},
            {"anomaly_type": "UNUSUAL_CHURN", "prefix": "10.0.1.0/24"},
        ]
        result = detector._deduplicate(candidates, [])
        assert len(result) == 2

    def test_expired_existing_anomaly_not_suppressed(self):
        detector = AnomalyDetector(dedup_window_seconds=300)

        existing = MagicMock()
        existing.anomaly_type = "UNUSUAL_CHURN"
        existing.prefix = "10.0.0.0/24"
        existing.detected_at = datetime.now(timezone.utc) - timedelta(seconds=600)

        candidates = [{"anomaly_type": "UNUSUAL_CHURN", "prefix": "10.0.0.0/24"}]
        result = detector._deduplicate(candidates, [existing])
        assert len(result) == 1


class TestCorrelatedFailure:
    def test_mass_withdrawal_detected(self):
        from api.models import RouteEvent

        speaker_id = str(uuid4())
        now = datetime.now(timezone.utc)

        mock_db = MagicMock()
        withdrawals = [
            MagicMock(spec=RouteEvent, prefix=f"10.0.{i}.0/24") for i in range(10)
        ]
        mock_db.query.return_value.filter.return_value.all.return_value = withdrawals

        detector = AnomalyDetector()
        result = detector._find_correlated_failures(
            speaker_id, now, window_seconds=60, db=mock_db
        )
        assert len(result) == 1
        assert result[0]["anomaly_type"] == "CORRELATED_FAILURE"
        assert result[0]["severity"] == "CRITICAL"
        assert result[0]["details"]["affected_prefix_count"] == 10

    def test_few_withdrawals_not_flagged(self):
        from api.models import RouteEvent

        mock_db = MagicMock()
        withdrawals = [MagicMock(spec=RouteEvent, prefix="10.0.0.0/24")]
        mock_db.query.return_value.filter.return_value.all.return_value = withdrawals

        detector = AnomalyDetector()
        result = detector._find_correlated_failures(
            str(uuid4()), datetime.now(timezone.utc), db=mock_db
        )
        assert result == []
