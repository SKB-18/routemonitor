"""Speaker-level metrics and correlation endpoints."""
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from api.dependencies import get_db, get_influxdb_connector
from api.models import Anomaly, RouteEvent
from core.influxdb_connector import InfluxDBConnector

router = APIRouter(prefix="/api/metrics", tags=["metrics"])

_TIME_RANGE_HOURS = {"1h": 1, "24h": 24, "7d": 168, "30d": 720}


@router.get("/speaker/{speaker_id}")
async def get_speaker_metrics(
    speaker_id: UUID,
    time_range: str = Query("24h", description="1h | 24h | 7d"),
    influx: InfluxDBConnector = Depends(get_influxdb_connector),
    db: Session = Depends(get_db),
) -> dict:
    """Return aggregated performance metrics for a BGP speaker."""
    try:
        hours = _TIME_RANGE_HOURS.get(time_range, 24)
        since = datetime.now(timezone.utc) - timedelta(hours=hours)

        total_prefixes = (
            db.query(func.count(func.distinct(RouteEvent.prefix)))
            .filter(
                RouteEvent.speaker_id == speaker_id,
                RouteEvent.timestamp >= since,
            )
            .scalar()
            or 0
        )
        total_flaps = (
            db.query(func.count(RouteEvent.id))
            .filter(
                RouteEvent.speaker_id == speaker_id,
                RouteEvent.event_type == "WITHDRAW",
                RouteEvent.timestamp >= since,
            )
            .scalar()
            or 0
        )
        anomaly_count = (
            db.query(func.count(Anomaly.id))
            .filter(
                Anomaly.speaker_id == speaker_id,
                Anomaly.detected_at >= since,
            )
            .scalar()
            or 0
        )

        return {
            "speaker_id": str(speaker_id),
            "time_range": time_range,
            "total_prefixes": total_prefixes,
            "total_flaps": total_flaps,
            "avg_convergence_ms": 0.0,
            "uptime_pct": 100.0,
            "anomaly_count": anomaly_count,
        }
    finally:
        influx.close()


@router.get("/correlation")
async def get_correlation(
    time_range: str = Query("7d", description="24h | 7d | 30d"),
    top_n_prefixes: int = Query(50, ge=5, le=200),
    influx: InfluxDBConnector = Depends(get_influxdb_connector),
) -> dict:
    """Return full prefix failure correlation matrix."""
    try:
        matrix = influx.query_correlation_matrix(
            time_range=time_range,
            top_n_prefixes=top_n_prefixes,
        )
        return {"matrix": matrix}
    finally:
        influx.close()
