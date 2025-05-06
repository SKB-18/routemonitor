"""Integration tests for metrics API endpoints."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from api.models import Anomaly, RouteEvent


@pytest.mark.integration
class TestSpeakerMetrics:
    def test_speaker_metrics_empty(self, client, mock_speaker):
        resp = client.get(
            f"/api/metrics/speaker/{mock_speaker.id}",
            params={"time_range": "24h"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["speaker_id"] == str(mock_speaker.id)
        assert data["time_range"] == "24h"
        assert data["total_prefixes"] == 0
        assert data["total_flaps"] == 0
        assert data["anomaly_count"] == 0
        assert data["uptime_pct"] == 100.0
        assert data["avg_convergence_ms"] == 0.0

    def test_speaker_metrics_with_data(
        self, client, mock_speaker, mock_route_update, mock_withdrawal, mock_anomaly
    ):
        resp = client.get(
            f"/api/metrics/speaker/{mock_speaker.id}",
            params={"time_range": "24h"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_prefixes"] >= 1
        assert data["total_flaps"] >= 1
        assert data["anomaly_count"] >= 1

    def test_speaker_metrics_not_found_speaker_still_returns_zeros(self, client):
        resp = client.get(
            f"/api/metrics/speaker/{uuid.uuid4()}",
            params={"time_range": "1h"},
        )
        assert resp.status_code == 200
        assert resp.json()["total_prefixes"] == 0

    def test_invalid_speaker_uuid_returns_422(self, client):
        resp = client.get("/api/metrics/speaker/not-a-uuid")
        assert resp.status_code == 422

    def test_time_range_filters_old_events(self, client, db_session, mock_speaker):
        old = RouteEvent(
            speaker_id=mock_speaker.id,
            timestamp=datetime.now(timezone.utc) - timedelta(days=2),
            event_type="WITHDRAW",
            prefix="10.99.0.0/24",
            neighbor_ip="10.0.0.1",
            neighbor_asn=65001,
            sequence_number=1,
        )
        db_session.add(old)
        db_session.commit()

        resp = client.get(
            f"/api/metrics/speaker/{mock_speaker.id}",
            params={"time_range": "1h"},
        )
        assert resp.status_code == 200
        assert resp.json()["total_flaps"] == 0

    def test_updates_do_not_count_as_flaps(self, client, db_session, mock_speaker):
        db_session.add(
            RouteEvent(
                speaker_id=mock_speaker.id,
                timestamp=datetime.now(timezone.utc),
                event_type="UPDATE",
                prefix="10.1.0.0/24",
                neighbor_ip="10.0.0.1",
                neighbor_asn=65001,
                sequence_number=1,
            )
        )
        db_session.commit()

        resp = client.get(f"/api/metrics/speaker/{mock_speaker.id}")
        assert resp.json()["total_flaps"] == 0
        assert resp.json()["total_prefixes"] == 1

    def test_distinct_prefix_count(self, client, db_session, mock_speaker):
        for prefix in ("10.0.0.0/24", "10.0.1.0/24", "10.0.0.0/24"):
            db_session.add(
                RouteEvent(
                    speaker_id=mock_speaker.id,
                    timestamp=datetime.now(timezone.utc),
                    event_type="UPDATE",
                    prefix=prefix,
                    neighbor_ip="10.0.0.1",
                    neighbor_asn=65001,
                    sequence_number=0,
                )
            )
        db_session.commit()

        resp = client.get(f"/api/metrics/speaker/{mock_speaker.id}")
        assert resp.json()["total_prefixes"] == 2

    def test_anomaly_outside_time_window_excluded(
        self, client, db_session, mock_speaker
    ):
        db_session.add(
            Anomaly(
                speaker_id=mock_speaker.id,
                anomaly_type="ROUTE_FLAP",
                severity="WARNING",
                prefix="10.0.0.0/24",
                detected_at=datetime.now(timezone.utc) - timedelta(days=10),
                details={},
            )
        )
        db_session.commit()

        resp = client.get(
            f"/api/metrics/speaker/{mock_speaker.id}",
            params={"time_range": "1h"},
        )
        assert resp.json()["anomaly_count"] == 0

    def test_unknown_time_range_defaults_to_24h(self, client, mock_speaker):
        resp = client.get(
            f"/api/metrics/speaker/{mock_speaker.id}",
            params={"time_range": "invalid"},
        )
        assert resp.status_code == 200
        assert resp.json()["time_range"] == "invalid"


@pytest.mark.integration
class TestCorrelationMetrics:
    def test_correlation_returns_matrix(self, client):
        from unittest.mock import MagicMock

        from api.dependencies import get_influxdb_connector
        from api.main import app

        mock_influx = MagicMock()
        mock_influx.query_correlation_matrix.return_value = {
            "10.0.0.0/24": {"10.0.0.0/24": 1.0, "10.0.1.0/24": 0.5},
            "10.0.1.0/24": {"10.0.0.0/24": 0.5, "10.0.1.0/24": 1.0},
        }
        mock_influx.close = MagicMock()
        app.dependency_overrides[get_influxdb_connector] = lambda: mock_influx
        try:
            resp = client.get("/api/metrics/correlation", params={"time_range": "7d"})
        finally:
            app.dependency_overrides.pop(get_influxdb_connector, None)

        assert resp.status_code == 200
        assert "matrix" in resp.json()
        assert "10.0.0.0/24" in resp.json()["matrix"]

    def test_correlation_empty_matrix(self, client):
        from unittest.mock import MagicMock

        from api.dependencies import get_influxdb_connector
        from api.main import app

        mock_influx = MagicMock()
        mock_influx.query_correlation_matrix.return_value = {}
        mock_influx.close = MagicMock()
        app.dependency_overrides[get_influxdb_connector] = lambda: mock_influx
        try:
            resp = client.get("/api/metrics/correlation")
        finally:
            app.dependency_overrides.pop(get_influxdb_connector, None)

        assert resp.status_code == 200
        assert resp.json()["matrix"] == {}

    def test_correlation_passes_top_n_to_influx(self, client):
        from unittest.mock import MagicMock

        from api.dependencies import get_influxdb_connector
        from api.main import app

        mock_influx = MagicMock()
        mock_influx.query_correlation_matrix.return_value = {}
        mock_influx.close = MagicMock()
        app.dependency_overrides[get_influxdb_connector] = lambda: mock_influx
        try:
            client.get("/api/metrics/correlation", params={"top_n_prefixes": 25})
        finally:
            app.dependency_overrides.pop(get_influxdb_connector, None)

        mock_influx.query_correlation_matrix.assert_called_once_with(
            time_range="7d", top_n_prefixes=25
        )
        mock_influx.close.assert_called_once()

    def test_correlation_top_n_below_minimum_returns_422(self, client):
        resp = client.get("/api/metrics/correlation", params={"top_n_prefixes": 2})
        assert resp.status_code == 422

    def test_correlation_top_n_above_maximum_returns_422(self, client):
        resp = client.get("/api/metrics/correlation", params={"top_n_prefixes": 500})
        assert resp.status_code == 422

    def test_correlation_custom_time_range(self, client):
        from unittest.mock import MagicMock

        from api.dependencies import get_influxdb_connector
        from api.main import app

        mock_influx = MagicMock()
        mock_influx.query_correlation_matrix.return_value = {}
        mock_influx.close = MagicMock()
        app.dependency_overrides[get_influxdb_connector] = lambda: mock_influx
        try:
            client.get("/api/metrics/correlation", params={"time_range": "30d"})
        finally:
            app.dependency_overrides.pop(get_influxdb_connector, None)

        mock_influx.query_correlation_matrix.assert_called_once_with(
            time_range="30d", top_n_prefixes=50
        )
