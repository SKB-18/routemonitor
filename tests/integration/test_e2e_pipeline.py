"""End-to-end integration tests across Phases 1–5."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tests.fixtures.bgp_telemetry_generator import MockBGPTelemetryGenerator


@pytest.mark.integration
class TestFullPipeline:
    """Speaker → BMP ingest → route events → anomaly list."""

    def test_bmp_ingest_creates_route_event(self, client, mock_speaker):
        gen = MockBGPTelemetryGenerator()
        bmp = gen.generate_update("10.50.0.0/24", mock_speaker.local_asn)

        with (
            patch("tasks.ingestion.InfluxDBConnector") as mock_influx_cls,
            patch("tasks.ingestion.detect_anomalies_task"),
        ):
            mock_influx_cls.return_value = MagicMock()
            resp = client.post(
                "/api/telemetry/bmp/ingest",
                content=bmp,
                headers={"Content-Type": "application/octet-stream"},
            )

        assert resp.status_code == 202

        events = client.get(
            "/api/telemetry/route-events",
            params={"speaker_id": str(mock_speaker.id), "limit": 10},
        )
        assert events.status_code == 200
        data = events.json()
        assert len(data) >= 1
        assert any(e["prefix"] == "10.50.0.0/24" for e in data)

    def test_health_endpoint_structure(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert "status" in body
        assert "services" in body
        assert "version" in body
        for svc in ("db", "redis", "influxdb"):
            assert svc in body["services"]


@pytest.mark.integration
class TestCrossPhaseAPIs:
    """Smoke-test that all major API surfaces respond correctly."""

    def test_openapi_schema_available(self, client):
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert schema["info"]["title"] == "RouteMonitor"
        paths = schema.get("paths", {})
        assert "/api/auth/token" in paths
        assert "/api/telemetry/bmp/ingest" in paths
        assert "/api/anomalies/" in paths
        assert "/api/alerts/webhooks" in paths
        assert "/api/metrics/correlation" in paths

    def test_docs_ui_available(self, client):
        resp = client.get("/docs")
        assert resp.status_code == 200
        assert "swagger" in resp.text.lower() or "openapi" in resp.text.lower()

    def test_forecast_endpoint(self, client, mock_speaker):
        with patch("api.dependencies.InfluxDBConnector") as mock_cls:
            mock_conn = MagicMock()
            mock_conn.query_anomaly_timeline.return_value = [
                {"time": "2024-01-01T00:00:00Z", "flap_count": 1},
                {"time": "2024-01-01T01:00:00Z", "flap_count": 3},
            ]
            mock_cls.return_value = mock_conn
            resp = client.get(f"/api/anomalies/forecast/{mock_speaker.id}")
        assert resp.status_code == 200
        assert "predictions" in resp.json()

    def test_correlation_matrix_endpoint(self, client):
        with patch("api.dependencies.InfluxDBConnector") as mock_cls:
            mock_conn = MagicMock()
            mock_conn.query_correlation_matrix.return_value = {
                "prefixes": ["10.0.0.0/24"],
                "matrix": [[1.0]],
            }
            mock_cls.return_value = mock_conn
            resp = client.get("/api/metrics/correlation", params={"time_range": "7d"})
        assert resp.status_code == 200
        assert "matrix" in resp.json()

    def test_speaker_metrics_endpoint(self, client, mock_speaker, mock_route_update):
        resp = client.get(
            f"/api/metrics/speaker/{mock_speaker.id}",
            params={"time_range": "24h"},
        )
        assert resp.status_code == 200
        data = resp.json()
        for key in ("total_prefixes", "total_flaps", "anomaly_count", "uptime_pct"):
            assert key in data


@pytest.mark.integration
class TestPhase5SecurityIntegration:
    def test_cors_headers_on_response(self, client):
        resp = client.get(
            "/health",
            headers={"Origin": "http://localhost:3000"},
        )
        assert resp.status_code == 200
        assert "access-control-allow-origin" in {k.lower() for k in resp.headers.keys()}

    def test_invalid_host_rejected(self, client):
        resp = client.get("/health", headers={"Host": "evil.example.com"})
        assert resp.status_code == 400

    def test_jwt_round_trip(self, auth_client):
        login = auth_client.post(
            "/api/auth/token",
            data={"username": "admin", "password": "admin123"},
        )
        token = login.json()["access_token"]
        me = auth_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert me.json()["role"] == "admin"

        # Token works on protected route
        webhook = auth_client.post(
            "/api/alerts/webhooks",
            json={
                "target_url": "https://example.com/e2e-hook",
                "severity_min": "WARNING",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert webhook.status_code == 201
