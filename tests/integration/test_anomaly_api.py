"""Integration tests for the anomaly detection + alerting API."""
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from tests.fixtures.bgp_telemetry_generator import MockBGPTelemetryGenerator


@pytest.mark.integration
class TestAnomalyEndpoints:
    def test_list_anomalies_empty(self, client):
        resp = client.get("/api/anomalies/")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_anomalies_returns_mock(self, client, mock_anomaly):
        resp = client.get("/api/anomalies/")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["anomaly_type"] == mock_anomaly.anomaly_type

    def test_list_anomalies_filter_by_severity(self, client, mock_anomaly):
        resp = client.get("/api/anomalies/", params={"severity": "WARNING"})
        assert resp.status_code == 200
        data = resp.json()
        assert all(a["severity"] == "WARNING" for a in data)
        ids = [a["id"] for a in data]
        assert str(mock_anomaly.id) in ids

    def test_list_anomalies_filter_by_speaker(self, client, mock_anomaly):
        resp = client.get(
            "/api/anomalies/",
            params={"speaker_id": str(mock_anomaly.speaker_id)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert all(a["speaker_id"] == str(mock_anomaly.speaker_id) for a in data)

    def test_get_anomaly_by_id(self, client, mock_anomaly):
        resp = client.get(f"/api/anomalies/{mock_anomaly.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(mock_anomaly.id)
        assert data["anomaly_type"] == mock_anomaly.anomaly_type

    def test_get_anomaly_not_found(self, client):
        resp = client.get(f"/api/anomalies/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_acknowledge_anomaly(self, client, mock_anomaly):
        resp = client.post(
            f"/api/anomalies/{mock_anomaly.id}/acknowledge",
            json={"acknowledged_by": "ops-engineer"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["acknowledged"] is True
        assert data["acknowledged_by"] == "ops-engineer"
        assert data["acknowledged_at"] is not None

    def test_acknowledge_nonexistent_anomaly(self, client):
        resp = client.post(
            f"/api/anomalies/{uuid.uuid4()}/acknowledge",
            json={"acknowledged_by": "ops-engineer"},
        )
        assert resp.status_code == 404

    def test_resolve_anomaly(self, client, mock_anomaly):
        resp = client.post(f"/api/anomalies/{mock_anomaly.id}/resolve")
        assert resp.status_code == 200
        data = resp.json()
        assert data["resolved_at"] is not None

    def test_list_anomalies_filter_acknowledged(self, client, mock_anomaly):
        resp = client.get("/api/anomalies/", params={"acknowledged": False})
        assert resp.status_code == 200
        assert all(not a["acknowledged"] for a in resp.json())

    def test_list_anomalies_filter_anomaly_type(self, client, mock_anomaly):
        resp = client.get("/api/anomalies/", params={"anomaly_type": "ROUTE_FLAP"})
        assert resp.status_code == 200
        assert all(a["anomaly_type"] == "ROUTE_FLAP" for a in resp.json())

    def test_forecast_anomalies(self, client, mock_speaker):
        from api.dependencies import get_influxdb_connector
        from api.main import app

        mock_influx = MagicMock()
        mock_influx.query_anomaly_timeline.return_value = [
            {"time": "2024-01-01T00:00:00Z", "flap_count": 2},
            {"time": "2024-01-01T01:00:00Z", "flap_count": 4},
            {"time": "2024-01-01T02:00:00Z", "flap_count": 6},
        ]
        mock_influx.close = MagicMock()
        app.dependency_overrides[get_influxdb_connector] = lambda: mock_influx

        resp = client.get(
            f"/api/anomalies/forecast/{mock_speaker.id}",
            params={"horizon_hours": 3},
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["speaker_id"] == str(mock_speaker.id)
        assert len(data["predictions"]) == 3
        assert data["predictions"][0]["risk"] in ("LOW", "HIGH")


@pytest.mark.integration
class TestAnomalyDetectionPipeline:
    def test_flapping_route_triggers_anomaly(self, client, mock_speaker, db_session):
        from tasks.ingestion import detect_anomalies_task

        with (
            patch("tasks.ingestion.InfluxDBConnector") as mock_influx_cls,
            patch("tasks.ingestion.dispatch_alerts_task") as mock_dispatch,
        ):
            mock_influx = MagicMock()
            mock_influx_cls.return_value = mock_influx
            mock_influx.query_route_stats.side_effect = [
                [
                    {
                        "time": f"2024-01-01T00:{i:02d}:00Z",
                        "flap_count": 1,
                        "route_count": 100,
                        "path_diversity": 2.0,
                        "convergence_ms": 10.0,
                    }
                    for i in range(50)
                ],
                [
                    {
                        "time": "2024-01-08T00:00:00Z",
                        "flap_count": 999,
                        "route_count": 100,
                        "path_diversity": 2.0,
                        "convergence_ms": 10.0,
                    }
                ],
            ]

            result = detect_anomalies_task.apply(args=[str(mock_speaker.id)]).get()

            assert result["anomalies_detected"] > 0
            mock_dispatch.delay.assert_called()

        resp = client.get(
            "/api/anomalies/",
            params={"speaker_id": str(mock_speaker.id)},
        )
        assert resp.status_code == 200
        assert len(resp.json()) > 0

    def test_anomaly_triggers_webhook_dispatch(self, client, mock_anomaly, db_session):
        from tasks.ingestion import dispatch_alerts_task

        resp = client.post(
            "/api/alerts/webhooks",
            json={
                "target_url": "http://localhost:9999/webhook",
                "severity_min": "INFO",
                "anomaly_types": ["ROUTE_FLAP"],
            },
        )
        assert resp.status_code == 201

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = MagicMock(status_code=200)

            result = dispatch_alerts_task.apply(args=[str(mock_anomaly.id)]).get()

            assert result["alerts_sent"] >= 1
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            payload = call_args.kwargs.get("json") or call_args[1].get("json", {})
            assert payload["anomaly_type"] == mock_anomaly.anomaly_type


@pytest.mark.integration
class TestAlertEndpoints:
    def test_register_webhook(self, client):
        resp = client.post(
            "/api/alerts/webhooks",
            json={
                "target_url": "https://example.com/hook",
                "severity_min": "WARNING",
                "anomaly_types": ["ROUTE_FLAP", "CORRELATED_FAILURE"],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "subscription_id" in data
        assert data["status"] == "active"

    def test_alert_history_empty(self, client):
        resp = client.get("/api/alerts/history")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_alert_history_returns_records(self, client, db_session, mock_anomaly):
        from api.models import Alert

        alert = Alert(
            id=uuid.uuid4(),
            anomaly_id=mock_anomaly.id,
            alert_type="WEBHOOK",
            target_url="https://example.com/hook",
            message="test",
            severity="WARNING",
            delivery_status="DELIVERED",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(alert)
        db_session.commit()

        resp = client.get("/api/alerts/history")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["delivery_status"] == "DELIVERED"

    def test_retry_non_failed_alert_rejected(self, client, db_session, mock_anomaly):
        from api.models import Alert

        alert = Alert(
            id=uuid.uuid4(),
            anomaly_id=mock_anomaly.id,
            alert_type="WEBHOOK",
            target_url="https://example.com/hook",
            message="{}",
            severity="WARNING",
            delivery_status="DELIVERED",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(alert)
        db_session.commit()

        resp = client.post(f"/api/alerts/{alert.id}/retry")
        assert resp.status_code == 400

    def test_retry_failed_alert(self, client, db_session, mock_anomaly):
        from api.models import Alert

        alert = Alert(
            id=uuid.uuid4(),
            anomaly_id=mock_anomaly.id,
            alert_type="WEBHOOK",
            target_url="https://example.com/hook",
            message="{}",
            severity="WARNING",
            delivery_status="FAILED",
            retry_count=1,
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(alert)
        db_session.commit()

        with patch("tasks.ingestion.dispatch_alerts_task") as mock_task:
            mock_task.delay.return_value = MagicMock(id="task-123")
            resp = client.post(f"/api/alerts/{alert.id}/retry")

        assert resp.status_code == 200
        assert resp.json()["status"] == "retry_queued"
