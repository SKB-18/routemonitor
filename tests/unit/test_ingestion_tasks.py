"""Unit tests for Celery ingestion task helpers."""
from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

from api.models import BGPSpeaker
from tasks.ingestion import _resolve_speaker, parse_bmp_message_task
from tests.fixtures.bgp_telemetry_generator import MockBGPTelemetryGenerator


class TestResolveSpeaker:
    def test_resolve_by_local_asn(self, db_session):
        speaker = BGPSpeaker(
            hostname="r-asn",
            router_id="10.0.0.1",
            local_asn=65000,
            bmp_listen_address="10.0.0.1:179",
        )
        db_session.add(speaker)
        db_session.commit()

        found = _resolve_speaker(
            db_session, {"peer_asn": 65000, "peer_address": "10.1.0.1"}
        )
        assert found is not None
        assert found.hostname == "r-asn"

    def test_resolve_by_listen_address(self, db_session):
        speaker = BGPSpeaker(
            hostname="r-addr",
            router_id="10.0.0.2",
            local_asn=65001,
            bmp_listen_address="192.168.5.5:179",
        )
        db_session.add(speaker)
        db_session.commit()

        found = _resolve_speaker(
            db_session, {"peer_asn": 99999, "peer_address": "192.168.5.5"}
        )
        assert found is not None
        assert found.hostname == "r-addr"

    def test_resolve_fallback_first_speaker(self, db_session):
        speaker = BGPSpeaker(
            hostname="r-fallback",
            router_id="10.0.0.3",
            local_asn=65002,
            bmp_listen_address="10.0.0.3:179",
        )
        db_session.add(speaker)
        db_session.commit()

        found = _resolve_speaker(db_session, {"peer_asn": 0, "peer_address": "0.0.0.0"})
        assert found is not None
        assert found.hostname == "r-fallback"


class TestParseBmpMessageTask:
    def test_parse_and_ingest_chain(self, db_session):
        speaker = BGPSpeaker(
            hostname="r-task",
            router_id="10.0.0.1",
            local_asn=65000,
            bmp_listen_address="10.0.0.1:179",
        )
        db_session.add(speaker)
        db_session.commit()

        bmp = MockBGPTelemetryGenerator().generate_update("172.16.0.0/24", 65000)
        with patch("tasks.ingestion.ingest_metrics_task") as mock_ingest:
            mock_ingest.apply.return_value = MagicMock()
            result = parse_bmp_message_task.run(bmp.hex())

        assert result["message_type"] == 0
        assert "172.16.0.0/24" in result["bgp_update"]["nlri_prefixes"]
        mock_ingest.apply.assert_called_once()


class TestDetectAnomaliesTask:
    def test_detect_anomalies_task_returns_count(self, db_session, mock_speaker):
        from tasks.ingestion import detect_anomalies_task

        with (
            patch("tasks.ingestion.InfluxDBConnector") as mock_influx_cls,
            patch("tasks.ingestion.dispatch_alerts_task"),
        ):
            mock_influx = MagicMock()
            mock_influx_cls.return_value = mock_influx
            mock_influx.query_route_stats.side_effect = [
                [
                    {"flap_count": 1, "route_count": 100, "path_diversity": 2.0}
                    for _ in range(50)
                ],
                [{"flap_count": 999, "route_count": 100, "path_diversity": 2.0}],
            ]
            result = detect_anomalies_task.run(str(mock_speaker.id))

        assert result["anomalies_detected"] >= 1


class TestDispatchAlertsTask:
    def test_dispatch_alerts_task_not_found(self, db_session):
        from tasks.ingestion import dispatch_alerts_task

        result = dispatch_alerts_task.run(str(uuid.uuid4()))
        assert result == {"alerts_sent": 0, "alerts_failed": 0}

    def test_dispatch_alerts_task_no_subscriptions(self, db_session, mock_anomaly):
        from tasks.ingestion import dispatch_alerts_task

        result = dispatch_alerts_task.run(str(mock_anomaly.id))
        assert result == {"alerts_sent": 0, "alerts_failed": 0}
