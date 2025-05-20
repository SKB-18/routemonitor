"""Unit tests for the full AnomalyDetector.detect_anomalies pipeline."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from api.models import Anomaly, RouteEvent
from core.detector import AnomalyDetector


def _stable_history(n: int = 50) -> list:
    return [
        {
            "time": f"2024-01-01T00:{i:02d}:00Z",
            "flap_count": 1 + (i % 2),
            "route_count": 100,
            "path_diversity": 2.0,
            "convergence_ms": 10.0,
        }
        for i in range(n)
    ]


@pytest.mark.asyncio
async def test_detect_anomalies_creates_zscore_record(db_session, mock_speaker):
    mock_influx = MagicMock()
    mock_influx.query_route_stats.side_effect = [
        _stable_history(),
        [{"flap_count": 500, "route_count": 100, "path_diversity": 2.0}],
    ]

    with patch("tasks.ingestion.dispatch_alerts_task") as mock_dispatch:
        detector = AnomalyDetector(z_score_threshold=3.0)
        result = await detector.detect_anomalies(
            str(mock_speaker.id), influx=mock_influx, db=db_session
        )

    assert len(result) >= 1
    assert result[0]["anomaly_type"] == "UNUSUAL_CHURN"
    mock_dispatch.delay.assert_called()

    stored = (
        db_session.query(Anomaly).filter(Anomaly.speaker_id == mock_speaker.id).all()
    )
    assert len(stored) >= 1


@pytest.mark.asyncio
async def test_detect_anomalies_empty_history_returns_empty(db_session, mock_speaker):
    mock_influx = MagicMock()
    mock_influx.query_route_stats.return_value = []

    detector = AnomalyDetector()
    result = await detector.detect_anomalies(
        str(mock_speaker.id), influx=mock_influx, db=db_session
    )
    assert result == []


@pytest.mark.asyncio
async def test_detect_anomalies_correlated_failure(db_session, mock_speaker):
    now = datetime.now(timezone.utc)
    for i in range(6):
        db_session.add(
            RouteEvent(
                speaker_id=mock_speaker.id,
                timestamp=now,
                event_type="WITHDRAW",
                prefix=f"10.0.{i}.0/24",
                neighbor_ip="192.168.1.2",
                neighbor_asn=65002,
                sequence_number=i,
            )
        )
    db_session.commit()

    mock_influx = MagicMock()
    mock_influx.query_route_stats.side_effect = [
        _stable_history(),
        [{"flap_count": 1, "route_count": 100, "path_diversity": 2.0}],
    ]

    with patch("tasks.ingestion.dispatch_alerts_task"):
        detector = AnomalyDetector(z_score_threshold=100.0)
        result = await detector.detect_anomalies(
            str(mock_speaker.id), influx=mock_influx, db=db_session
        )

    types = {r["anomaly_type"] for r in result}
    assert "CORRELATED_FAILURE" in types


@pytest.mark.asyncio
async def test_detect_anomalies_dedup_skips_existing(db_session, mock_speaker):
    mock_influx = MagicMock()
    mock_influx.query_route_stats.side_effect = [
        _stable_history(),
        [{"flap_count": 500, "route_count": 100, "path_diversity": 2.0}],
    ]

    existing = Anomaly(
        speaker_id=mock_speaker.id,
        prefix=None,
        anomaly_type="UNUSUAL_CHURN",
        severity="WARNING",
        detected_at=datetime.now(timezone.utc),
        details={"model": "z_score"},
    )
    db_session.add(existing)
    db_session.commit()

    with patch("tasks.ingestion.dispatch_alerts_task") as mock_dispatch:
        detector = AnomalyDetector(z_score_threshold=3.0, dedup_window_seconds=300)
        result = await detector.detect_anomalies(
            str(mock_speaker.id), influx=mock_influx, db=db_session
        )

    assert result == []
    mock_dispatch.delay.assert_not_called()
