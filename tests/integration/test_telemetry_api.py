"""Integration tests for the telemetry ingestion API."""
from unittest.mock import MagicMock, patch

import pytest

from tests.fixtures.bgp_telemetry_generator import MockBGPTelemetryGenerator


SPEAKER_PAYLOAD = {
    "hostname": "router1",
    "router_id": "10.0.0.1",
    "local_asn": 65000,
    "bmp_listen_address": "10.0.0.1:179",
}


@pytest.mark.integration
class TestSpeakerRegistration:
    def test_register_speaker(self, client):
        resp = client.post("/api/telemetry/speakers", json=SPEAKER_PAYLOAD)
        assert resp.status_code == 201
        assert resp.json()["hostname"] == "router1"

    def test_duplicate_hostname_rejected(self, client):
        client.post("/api/telemetry/speakers", json=SPEAKER_PAYLOAD)
        resp = client.post("/api/telemetry/speakers", json=SPEAKER_PAYLOAD)
        assert resp.status_code == 409

    def test_list_speakers_empty(self, client):
        resp = client.get("/api/telemetry/speakers")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_speakers_after_insert(self, client, mock_speaker):
        resp = client.get("/api/telemetry/speakers")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["hostname"] == mock_speaker.hostname


@pytest.mark.integration
class TestSpeakerEndpoints:
    def test_get_speaker_by_id(self, client, mock_speaker):
        resp = client.get(f"/api/telemetry/speakers/{mock_speaker.id}")
        assert resp.status_code == 200
        assert resp.json()["hostname"] == mock_speaker.hostname

    def test_get_speaker_not_found(self, client):
        import uuid

        resp = client.get(f"/api/telemetry/speakers/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_speaker_status(self, client, mock_speaker, mock_route_update):
        resp = client.get(f"/api/telemetry/speakers/{mock_speaker.id}/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "CONNECTED"
        assert data["routes_advertised_24h"] >= 1


@pytest.mark.integration
class TestMetricsEndpoint:
    def test_route_stats_returns_structure(self, client, mock_speaker):
        with patch("api.dependencies.InfluxDBConnector") as mock_cls:
            mock_conn = MagicMock()
            mock_conn.query_route_stats.return_value = [
                {
                    "time": "2024-01-01T00:00:00+00:00",
                    "flap_count": 2,
                    "route_count": 100,
                    "path_diversity": 1.5,
                    "convergence_ms": 50.0,
                }
            ]
            mock_cls.return_value = mock_conn

            resp = client.get(
                f"/api/telemetry/metrics/route-stats/{mock_speaker.id}",
                params={"time_range": "24h"},
            )
        assert resp.status_code == 200
        body = resp.json()
        assert body["speaker_id"] == str(mock_speaker.id)
        assert body["time_range"] == "24h"
        assert len(body["data_points"]) == 1


@pytest.mark.integration
class TestBMPIngestion:
    def test_ingest_bmp_update(self, client):
        client.post("/api/telemetry/speakers", json=SPEAKER_PAYLOAD)
        bmp = MockBGPTelemetryGenerator().generate_update("10.0.0.0/24", 65000)
        resp = client.post("/api/telemetry/bmp/ingest", content=bmp)
        assert resp.status_code == 202
        assert resp.json()["status"] == "accepted"

        events = client.get("/api/telemetry/route-events").json()
        assert len(events) >= 1
        assert events[0]["event_type"] == "UPDATE"

    def test_ingest_bmp_withdraw(self, client):
        client.post("/api/telemetry/speakers", json=SPEAKER_PAYLOAD)
        bmp = MockBGPTelemetryGenerator().generate_withdraw("10.0.0.0/24", 65000)
        resp = client.post("/api/telemetry/bmp/ingest", content=bmp)
        assert resp.status_code == 202

        events = client.get(
            "/api/telemetry/route-events", params={"event_type": "WITHDRAW"}
        ).json()
        assert len(events) >= 1
        assert events[0]["event_type"] == "WITHDRAW"

    def test_ingest_invalid_bmp_rejected(self, client):
        client.post("/api/telemetry/speakers", json=SPEAKER_PAYLOAD)
        resp = client.post("/api/telemetry/bmp/ingest", content=b"")
        assert resp.status_code == 400

    def test_ingest_stores_path_attributes(self, client):
        client.post("/api/telemetry/speakers", json=SPEAKER_PAYLOAD)
        bmp = MockBGPTelemetryGenerator().generate_update(
            "10.0.0.0/24", 65000, as_path=[65000, 65001, 65002]
        )
        client.post("/api/telemetry/bmp/ingest", content=bmp)

        events = client.get("/api/telemetry/route-events").json()
        assert events[0]["path_attributes"]["as_path"] == [65000, 65001, 65002]

    def test_flap_simulation_creates_multiple_events(self, client):
        client.post(
            "/api/telemetry/speakers",
            json={
                **SPEAKER_PAYLOAD,
                "hostname": "router-flap",
            },
        )
        gen = MockBGPTelemetryGenerator()
        for msg in gen.simulate_route_flap("router-flap", "10.0.1.0/24", num_flaps=3):
            client.post("/api/telemetry/bmp/ingest", content=msg)

        events = client.get("/api/telemetry/route-events").json()
        assert len(events) >= 3


@pytest.mark.integration
class TestRouteEventQuery:
    def test_query_by_speaker(self, client, mock_route_update):
        resp = client.get(
            "/api/telemetry/route-events",
            params={"speaker_id": str(mock_route_update.speaker_id)},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["speaker_id"] == str(mock_route_update.speaker_id)

    def test_query_by_prefix(self, client, mock_route_update):
        resp = client.get(
            "/api/telemetry/route-events",
            params={"prefix": "10.0.0.0/24"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert all(e["prefix"] == "10.0.0.0/24" for e in data)

    def test_query_pagination(self, client, mock_speaker, db_session):
        from datetime import datetime, timezone
        from uuid import uuid4

        from api.models import RouteEvent

        for i in range(5):
            db_session.add(
                RouteEvent(
                    id=uuid4(),
                    speaker_id=mock_speaker.id,
                    timestamp=datetime.now(timezone.utc),
                    event_type="UPDATE",
                    prefix=f"10.0.{i}.0/24",
                    neighbor_ip="192.168.1.2",
                    neighbor_asn=65002,
                    sequence_number=i,
                )
            )
        db_session.commit()

        resp = client.get(
            "/api/telemetry/route-events", params={"limit": 2, "offset": 0}
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 2

        resp2 = client.get(
            "/api/telemetry/route-events", params={"limit": 2, "offset": 2}
        )
        assert len(resp2.json()) == 2
