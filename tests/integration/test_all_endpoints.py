"""Exhaustive integration tests — every HTTP endpoint in RouteMonitor.

Covers happy paths, auth boundaries, and key error responses for Phases 1–6.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from tests.fixtures.bgp_telemetry_generator import MockBGPTelemetryGenerator

SPEAKER = {
    "hostname": "matrix-router",
    "router_id": "10.88.0.1",
    "local_asn": 65088,
    "bmp_listen_address": "10.88.0.1:179",
}


def _token(client, user: str, password: str) -> str:
    r = client.post("/api/auth/token", data={"username": user, "password": password})
    assert r.status_code == 200
    return r.json()["access_token"]


# ─── Health & meta ────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestHealthAndMeta:
    def test_health(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] in ("healthy", "unhealthy")
        assert "services" in body

    def test_openapi_json(self, client):
        r = client.get("/openapi.json")
        assert r.status_code == 200
        paths = r.json()["paths"]
        assert "/health" in paths
        assert "/api/auth/token" in paths

    def test_swagger_docs(self, client):
        r = client.get("/docs")
        assert r.status_code == 200

    def test_redoc(self, client):
        r = client.get("/redoc")
        assert r.status_code == 200

    def test_prometheus_metrics(self, client):
        client.get("/health")
        r = client.get("/metrics")
        assert r.status_code == 200
        assert "routemonitor_http_requests_total" in r.text


# ─── Auth ─────────────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestAuthEndpoints:
    def test_token_admin(self, auth_client):
        r = auth_client.post(
            "/api/auth/token", data={"username": "admin", "password": "admin123"}
        )
        assert r.status_code == 200
        assert r.json()["token_type"] == "bearer"

    def test_token_operator(self, auth_client):
        r = auth_client.post(
            "/api/auth/token", data={"username": "operator", "password": "operator123"}
        )
        assert r.status_code == 200

    def test_token_readonly(self, auth_client):
        r = auth_client.post(
            "/api/auth/token", data={"username": "readonly", "password": "readonly123"}
        )
        assert r.status_code == 200

    def test_token_invalid(self, auth_client):
        r = auth_client.post(
            "/api/auth/token", data={"username": "admin", "password": "wrong"}
        )
        assert r.status_code == 401

    def test_me_requires_auth(self, auth_client):
        assert auth_client.get("/api/auth/me").status_code == 401

    def test_me_with_token(self, auth_client):
        token = _token(auth_client, "admin", "admin123")
        r = auth_client.get(
            "/api/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert r.status_code == 200
        assert r.json()["role"] == "admin"


# ─── Telemetry ────────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestTelemetryEndpoints:
    def test_register_speaker(self, client):
        r = client.post("/api/telemetry/speakers", json=SPEAKER)
        assert r.status_code == 201
        assert r.json()["hostname"] == SPEAKER["hostname"]

    def test_list_speakers(self, client, mock_speaker):
        r = client.get("/api/telemetry/speakers")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_get_speaker(self, client, mock_speaker):
        r = client.get(f"/api/telemetry/speakers/{mock_speaker.id}")
        assert r.status_code == 200
        assert r.json()["id"] == str(mock_speaker.id)

    def test_get_speaker_404(self, client):
        r = client.get(f"/api/telemetry/speakers/{uuid.uuid4()}")
        assert r.status_code == 404

    def test_speaker_status(self, client, mock_speaker, mock_route_update):
        r = client.get(f"/api/telemetry/speakers/{mock_speaker.id}/status")
        assert r.status_code == 200
        assert "status" in r.json()

    def test_route_events(self, client, mock_route_update):
        r = client.get("/api/telemetry/route-events", params={"limit": 10})
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_route_events_filter_prefix(self, client, mock_route_update):
        r = client.get(
            "/api/telemetry/route-events",
            params={"prefix": "10.0.0.0/24", "limit": 5},
        )
        assert r.status_code == 200

    def test_bmp_ingest_empty_body(self, client):
        r = client.post(
            "/api/telemetry/bmp/ingest",
            content=b"",
            headers={"Content-Type": "application/octet-stream"},
        )
        assert r.status_code == 400

    def test_bmp_ingest_valid(self, client, mock_speaker):
        bmp = MockBGPTelemetryGenerator().generate_update(
            "10.88.1.0/24", mock_speaker.local_asn
        )
        with (
            patch("tasks.ingestion.InfluxDBConnector") as mock_cls,
            patch("tasks.ingestion.detect_anomalies_task"),
        ):
            mock_cls.return_value = MagicMock()
            r = client.post(
                "/api/telemetry/bmp/ingest",
                content=bmp,
                headers={"Content-Type": "application/octet-stream"},
            )
        assert r.status_code == 202

    def test_telemetry_route_stats(self, client, mock_speaker):
        with patch("api.dependencies.InfluxDBConnector") as mock_cls:
            mock_cls.return_value.query_route_stats.return_value = [
                {
                    "time": "2024-01-01T00:00:00Z",
                    "flap_count": 1,
                    "route_count": 10,
                    "path_diversity": 1.0,
                    "convergence_ms": 5.0,
                }
            ]
            r = client.get(
                f"/api/telemetry/metrics/route-stats/{mock_speaker.id}",
                params={"time_range": "24h"},
            )
        assert r.status_code == 200
        assert "data_points" in r.json()

    def test_telemetry_correlation_not_implemented(self, client):
        r = client.get("/api/telemetry/metrics/correlation")
        assert r.status_code == 501


# ─── Metrics (Phase 4) ────────────────────────────────────────────────────────


@pytest.mark.integration
class TestMetricsEndpoints:
    def test_speaker_metrics(self, client, mock_speaker, mock_route_update):
        r = client.get(
            f"/api/metrics/speaker/{mock_speaker.id}", params={"time_range": "24h"}
        )
        assert r.status_code == 200
        for key in ("total_prefixes", "total_flaps", "anomaly_count", "uptime_pct"):
            assert key in r.json()

    def test_speaker_metrics_bad_uuid(self, client):
        r = client.get("/api/metrics/speaker/not-a-uuid")
        assert r.status_code == 422

    def test_correlation_matrix(self, client):
        with patch("api.dependencies.InfluxDBConnector") as mock_cls:
            mock_cls.return_value.query_correlation_matrix.return_value = {
                "prefixes": ["10.0.0.0/24"],
                "matrix": [[1.0]],
            }
            r = client.get("/api/metrics/correlation", params={"time_range": "7d"})
        assert r.status_code == 200
        assert "matrix" in r.json()

    def test_correlation_validation(self, client):
        r = client.get("/api/metrics/correlation", params={"top_n_prefixes": 0})
        assert r.status_code == 422


# ─── Anomalies ────────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestAnomalyEndpoints:
    def test_list(self, client, mock_anomaly):
        r = client.get("/api/anomalies/")
        assert r.status_code == 200

    def test_list_filters(self, client, mock_anomaly):
        r = client.get(
            "/api/anomalies/",
            params={
                "severity": "WARNING",
                "anomaly_type": "ROUTE_FLAP",
                "acknowledged": False,
                "time_range": "24h",
                "limit": 50,
            },
        )
        assert r.status_code == 200

    def test_get_by_id(self, client, mock_anomaly):
        r = client.get(f"/api/anomalies/{mock_anomaly.id}")
        assert r.status_code == 200

    def test_get_404(self, client):
        r = client.get(f"/api/anomalies/{uuid.uuid4()}")
        assert r.status_code == 404

    def test_forecast(self, client, mock_speaker):
        with patch("api.dependencies.InfluxDBConnector") as mock_cls:
            mock_cls.return_value.query_anomaly_timeline.return_value = [
                {"time": "2024-01-01T00:00:00Z", "flap_count": 1},
                {"time": "2024-01-01T01:00:00Z", "flap_count": 3},
            ]
            r = client.get(f"/api/anomalies/forecast/{mock_speaker.id}")
        assert r.status_code == 200
        assert "predictions" in r.json()

    def test_acknowledge(self, client, mock_anomaly):
        r = client.post(
            f"/api/anomalies/{mock_anomaly.id}/acknowledge",
            json={"acknowledged_by": "ops"},
        )
        assert r.status_code == 200

    def test_resolve(self, client, mock_anomaly):
        r = client.post(f"/api/anomalies/{mock_anomaly.id}/resolve")
        assert r.status_code == 200

    def test_acknowledge_requires_auth(self, auth_client, mock_anomaly):
        r = auth_client.post(
            f"/api/anomalies/{mock_anomaly.id}/acknowledge",
            json={"acknowledged_by": "x"},
        )
        assert r.status_code == 401


# ─── Alerts ───────────────────────────────────────────────────────────────────


@pytest.mark.integration
class TestAlertEndpoints:
    def test_register_webhook(self, client):
        r = client.post(
            "/api/alerts/webhooks",
            json={"target_url": "https://example.com/hook", "severity_min": "WARNING"},
        )
        assert r.status_code == 201

    def test_alert_history(self, client):
        r = client.get("/api/alerts/history")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_alert_history_limit(self, client):
        r = client.get("/api/alerts/history", params={"limit": 5})
        assert r.status_code == 200

    def test_retry_failed_alert(self, client, db_session, mock_anomaly):
        from api.models import Alert

        alert = Alert(
            id=uuid.uuid4(),
            anomaly_id=mock_anomaly.id,
            alert_type="WEBHOOK",
            target_url="https://example.com/hook",
            message="test",
            severity="WARNING",
            delivery_status="FAILED",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(alert)
        db_session.commit()
        r = client.post(f"/api/alerts/{alert.id}/retry")
        assert r.status_code == 200

    def test_retry_non_failed_rejected(self, client, db_session, mock_anomaly):
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
        r = client.post(f"/api/alerts/{alert.id}/retry")
        assert r.status_code == 400

    def test_webhook_requires_admin(self, auth_client):
        token = _token(auth_client, "operator", "operator123")
        r = auth_client.post(
            "/api/alerts/webhooks",
            json={"target_url": "https://example.com/hook"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert r.status_code == 403


# ─── Full pipeline E2E ───────────────────────────────────────────────────────


@pytest.mark.integration
class TestCompletePipeline:
    """End-to-end: speaker → BMP → events → anomaly detection → alert webhook."""

    def test_full_ingest_to_anomaly_flow(self, client, db_session):
        from api.models import Anomaly, RouteEvent, WebhookSubscription
        from tasks.ingestion import detect_anomalies_task

        r = client.post(
            "/api/telemetry/speakers",
            json={
                "hostname": f"e2e-{uuid.uuid4().hex[:6]}",
                "router_id": "10.77.0.1",
                "local_asn": 65077,
                "bmp_listen_address": "10.77.0.1:179",
            },
        )
        assert r.status_code == 201
        speaker_id = r.json()["id"]

        gen = MockBGPTelemetryGenerator()
        bmp = gen.generate_update("10.77.10.0/24", 65077)
        with (
            patch("tasks.ingestion.InfluxDBConnector") as mock_influx_cls,
            patch("tasks.ingestion.dispatch_alerts_task"),
        ):
            mock_influx_cls.return_value = MagicMock()
            assert (
                client.post(
                    "/api/telemetry/bmp/ingest",
                    content=bmp,
                    headers={"Content-Type": "application/octet-stream"},
                ).status_code
                == 202
            )

        events = client.get(
            "/api/telemetry/route-events",
            params={"speaker_id": speaker_id, "limit": 5},
        ).json()
        assert len(events) >= 1

        db_session.add(
            WebhookSubscription(
                target_url="https://example.com/e2e",
                severity_min="INFO",
                active=True,
            )
        )
        db_session.commit()

        with (
            patch("tasks.ingestion.InfluxDBConnector") as mock_influx_cls,
            patch("tasks.ingestion.dispatch_alerts_task") as mock_dispatch,
        ):
            mock_influx = MagicMock()
            mock_influx_cls.return_value = mock_influx
            mock_influx.query_route_stats.side_effect = [
                [{"flap_count": 2, "route_count": 100, "path_diversity": 2.0}] * 50,
                [{"flap_count": 500, "route_count": 100, "path_diversity": 2.0}],
            ]
            detect_anomalies_task.run(speaker_id)

        anomalies = (
            db_session.query(Anomaly)
            .filter(Anomaly.speaker_id == uuid.UUID(speaker_id))
            .all()
        )
        assert len(anomalies) >= 1

        listed = client.get("/api/anomalies/", params={"speaker_id": speaker_id})
        assert listed.status_code == 200
        assert len(listed.json()) >= 1

        ack = client.post(
            f"/api/anomalies/{anomalies[0].id}/acknowledge",
            json={"acknowledged_by": "e2e-test"},
        )
        assert ack.status_code == 200

        metrics = client.get(f"/api/metrics/speaker/{speaker_id}")
        assert metrics.status_code == 200

        history = client.get("/api/alerts/history")
        assert history.status_code == 200
