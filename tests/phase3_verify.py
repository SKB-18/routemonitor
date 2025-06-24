"""Phase 3 live-stack verification against real Docker services.

Run inside Docker:
    docker compose exec api python tests/phase3_verify.py
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from sqlalchemy import inspect

PASS = FAIL = SKIP = 0
RESULTS: list[tuple[str, str, str]] = []


def check(name: str, fn) -> None:
    global PASS, FAIL
    try:
        fn()
        PASS += 1
        RESULTS.append(("PASS", name, ""))
        print(f"  PASS  {name}")
    except Exception as e:
        FAIL += 1
        RESULTS.append(("FAIL", name, str(e)))
        print(f"  FAIL  {name}: {e}")


def test_detector_unit() -> None:
    print("\n=== 1. AnomalyDetector (unit smoke) ===")
    from core.detector import AnomalyDetector

    detector = AnomalyDetector()

    def baseline():
        metrics = [
            {"flap_count": i % 5, "route_count": 100, "path_diversity": 2.0}
            for i in range(20)
        ]
        b = detector._compute_baseline(metrics)
        assert abs(b["mean_flap_rate"] - 2.0) < 0.01

    def zscore():
        baseline = detector._compute_baseline(
            [{"flap_count": 2, "route_count": 100, "path_diversity": 2.0}] * 30
        )
        result = detector._detect_z_score_anomalies({"flap_count": 500}, baseline)
        assert len(result) == 1

    check("compute baseline", baseline)
    check("z-score spike detection", zscore)


def test_influxdb_phase3() -> None:
    print("\n=== 2. InfluxDB Phase 3 queries (live) ===")
    from core.influxdb_connector import InfluxDBConnector

    sid = f"phase3-{uuid.uuid4().hex[:8]}"

    def timeline():
        c = InfluxDBConnector()
        c.write_metrics_batch(
            [
                {
                    "measurement": "route_stats",
                    "tags": {"speaker_id": sid, "prefix": "10.1.0.0/24"},
                    "fields": {"flap_count": 3},
                },
                {
                    "measurement": "route_stats",
                    "tags": {"speaker_id": sid, "prefix": "10.2.0.0/24"},
                    "fields": {"flap_count": 5},
                },
            ]
        )
        results = c.query_anomaly_timeline(sid, time_range="1h")
        c.close()
        assert isinstance(results, list)

    def correlation():
        c = InfluxDBConnector()
        c.write_metrics_batch(
            [
                {
                    "measurement": "route_stats",
                    "tags": {"speaker_id": sid, "prefix": "10.1.0.0/24"},
                    "fields": {"flap_count": 3},
                },
                {
                    "measurement": "route_stats",
                    "tags": {"speaker_id": sid, "prefix": "10.2.0.0/24"},
                    "fields": {"flap_count": 5},
                },
            ]
        )
        matrix = c.query_correlation_matrix(time_range="1h", top_n_prefixes=5)
        c.close()
        assert isinstance(matrix, dict)

    check("query_anomaly_timeline", timeline)
    check("query_correlation_matrix", correlation)


def test_celery_phase3() -> None:
    print("\n=== 3. Celery Phase 3 tasks (live) ===")
    from api.database import SessionLocal
    from api.models import BGPSpeaker, WebhookSubscription
    from tasks.ingestion import detect_anomalies_task, dispatch_alerts_task
    from unittest.mock import patch, MagicMock

    hostname = f"p3-{uuid.uuid4().hex[:8]}"

    def detection_pipeline():
        db = SessionLocal()
        speaker = BGPSpeaker(
            hostname=hostname,
            router_id="10.88.0.1",
            local_asn=65088,
            bmp_listen_address="10.88.0.1:179",
        )
        db.add(speaker)
        db.commit()
        db.refresh(speaker)
        speaker_id = str(speaker.id)
        db.close()

        with patch("tasks.ingestion.InfluxDBConnector") as mock_cls:
            mock_influx = MagicMock()
            mock_cls.return_value = mock_influx
            mock_influx.query_route_stats.side_effect = [
                [
                    {"flap_count": 1, "route_count": 100, "path_diversity": 2.0}
                    for _ in range(50)
                ],
                [{"flap_count": 800, "route_count": 100, "path_diversity": 2.0}],
            ]
            with patch("tasks.ingestion.dispatch_alerts_task"):
                result = detect_anomalies_task.run(speaker_id)
        assert result["anomalies_detected"] >= 1

        db2 = SessionLocal()
        from api.models import Anomaly

        db2.query(Anomaly).filter(Anomaly.speaker_id == speaker.id).delete()
        db2.query(BGPSpeaker).filter(BGPSpeaker.id == speaker.id).delete()
        db2.commit()
        db2.close()

    def alert_dispatch():
        db = SessionLocal()
        from api.models import Anomaly, BGPSpeaker

        speaker = BGPSpeaker(
            hostname=f"{hostname}-alert",
            router_id="10.88.0.2",
            local_asn=65089,
            bmp_listen_address="10.88.0.2:179",
        )
        db.add(speaker)
        db.flush()

        from datetime import datetime, timezone

        anomaly = Anomaly(
            speaker_id=speaker.id,
            anomaly_type="ROUTE_FLAP",
            severity="WARNING",
            prefix="10.0.0.0/24",
            detected_at=datetime.now(timezone.utc),
            details={"model": "z_score"},
        )
        db.add(anomaly)
        sub = WebhookSubscription(
            target_url="http://localhost:9999/phase3-hook",
            severity_min="INFO",
            anomaly_types=["ROUTE_FLAP"],
            active=True,
        )
        db.add(sub)
        db.commit()
        anomaly_id = str(anomaly.id)
        anomaly_uuid = anomaly.id
        speaker_id = speaker.id
        db.close()

        with patch("httpx.AsyncClient.post", return_value=MagicMock(status_code=200)):
            result = dispatch_alerts_task.run(anomaly_id)
        assert result["alerts_sent"] >= 1

        db3 = SessionLocal()
        from api.models import Alert

        db3.query(Alert).filter(Alert.anomaly_id == anomaly_uuid).delete()
        db3.query(WebhookSubscription).delete()
        db3.query(Anomaly).filter(Anomaly.id == anomaly_uuid).delete()
        db3.query(BGPSpeaker).filter(BGPSpeaker.id == speaker_id).delete()
        db3.commit()
        db3.close()

    check("detect_anomalies_task", detection_pipeline)
    check("dispatch_alerts_task", alert_dispatch)


def test_api_phase3() -> None:
    print("\n=== 4. FastAPI Phase 3 endpoints (live) ===")
    base = "http://localhost:8000"

    def _admin_token() -> str:
        r = httpx.post(
            f"{base}/api/auth/token",
            data={"username": "admin", "password": "admin123"},
            timeout=5,
        )
        assert r.status_code == 200, r.text
        return r.json()["access_token"]

    def list_anomalies():
        r = httpx.get(f"{base}/api/anomalies/", timeout=5)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def register_webhook():
        token = _admin_token()
        r = httpx.post(
            f"{base}/api/alerts/webhooks",
            json={
                "target_url": "https://example.com/phase3-hook",
                "severity_min": "WARNING",
                "anomaly_types": ["UNUSUAL_CHURN"],
            },
            headers={"Authorization": f"Bearer {token}"},
            timeout=5,
        )
        assert r.status_code == 201
        assert r.json()["status"] == "active"

    def alert_history():
        r = httpx.get(f"{base}/api/alerts/history", timeout=5)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    check("GET /api/anomalies/", list_anomalies)
    check("POST /api/alerts/webhooks", register_webhook)
    check("GET /api/alerts/history", alert_history)


def test_postgres_webhook_table() -> None:
    print("\n=== 5. PostgreSQL webhook_subscriptions ===")
    from api.database import engine

    def table_exists():
        insp = inspect(engine)
        assert "webhook_subscriptions" in insp.get_table_names()

    check("webhook_subscriptions table", table_exists)


def main() -> int:
    print("=" * 60)
    print("RouteMonitor Phase 3 Live Verification")
    print("=" * 60)

    for fn in [
        test_detector_unit,
        test_influxdb_phase3,
        test_celery_phase3,
        test_api_phase3,
        test_postgres_webhook_table,
    ]:
        try:
            fn()
        except Exception as e:
            print(f"  SECTION ERROR: {e}")

    print("\n" + "=" * 60)
    print(f"RESULTS: {PASS} passed, {FAIL} failed, {SKIP} skipped")
    print("=" * 60)
    if FAIL:
        for status, name, detail in RESULTS:
            if status == "FAIL":
                print(f"  - {name}: {detail}")
        return 1
    print("\nPhase 3 live stack: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
