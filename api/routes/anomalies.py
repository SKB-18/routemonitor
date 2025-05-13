"""Anomaly query, acknowledgement, and forecast endpoints."""
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.auth import require_role
from api.dependencies import get_current_user, get_db, get_influxdb_connector
from api.models import Anomaly
from api.schemas import AnomalyAcknowledgeRequest, AnomalyResponse
from core.influxdb_connector import InfluxDBConnector

router = APIRouter(prefix="/api/anomalies", tags=["anomalies"])

_TIME_RANGE_HOURS = {"1h": 1, "24h": 24, "7d": 168, "30d": 720}


@router.get("/", response_model=List[AnomalyResponse])
async def list_anomalies(
    speaker_id: Optional[UUID] = Query(None),
    severity: Optional[str] = Query(None, description="INFO | WARNING | CRITICAL"),
    anomaly_type: Optional[str] = Query(None),
    acknowledged: Optional[bool] = Query(None),
    time_range: str = Query("24h", description="1h | 24h | 7d | 30d"),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> List[AnomalyResponse]:
    """List detected anomalies with optional filters."""
    q = db.query(Anomaly)

    if speaker_id:
        q = q.filter(Anomaly.speaker_id == speaker_id)
    if severity:
        q = q.filter(Anomaly.severity == severity.upper())
    if anomaly_type:
        q = q.filter(Anomaly.anomaly_type == anomaly_type.upper())
    if acknowledged is not None:
        q = q.filter(Anomaly.acknowledged == acknowledged)

    hours = _TIME_RANGE_HOURS.get(time_range, 24)
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    q = q.filter(Anomaly.detected_at >= since)

    return q.order_by(Anomaly.detected_at.desc()).limit(limit).all()


@router.get("/forecast/{speaker_id}")
async def forecast_anomalies(
    speaker_id: UUID,
    horizon_hours: int = Query(1, ge=1, le=24),
    influx: InfluxDBConnector = Depends(get_influxdb_connector),
) -> dict:
    """Forecast likely anomalies using linear extrapolation from recent flap trends."""
    try:
        timeline = influx.query_anomaly_timeline(str(speaker_id), time_range="24h")
        if len(timeline) < 2:
            return {
                "speaker_id": str(speaker_id),
                "forecast_horizon_hours": horizon_hours,
                "predictions": [],
            }

        values = [float(p["flap_count"]) for p in timeline]
        n = len(values)
        slope = (values[-1] - values[0]) / max(n - 1, 1)
        baseline_mean = sum(values) / n
        threshold = baseline_mean * 2

        now = datetime.now(timezone.utc)
        predictions = []
        for h in range(1, horizon_hours + 1):
            predicted = values[-1] + slope * h
            risk = "HIGH" if predicted > threshold else "LOW"
            predictions.append(
                {
                    "time": (now + timedelta(hours=h)).isoformat(),
                    "predicted_flap_rate": round(predicted, 3),
                    "risk": risk,
                }
            )

        return {
            "speaker_id": str(speaker_id),
            "forecast_horizon_hours": horizon_hours,
            "predictions": predictions,
        }
    finally:
        influx.close()


@router.get("/{anomaly_id}", response_model=AnomalyResponse)
async def get_anomaly(
    anomaly_id: UUID,
    db: Session = Depends(get_db),
) -> AnomalyResponse:
    """Get a single anomaly by ID."""
    anomaly = db.query(Anomaly).filter(Anomaly.id == anomaly_id).first()
    if not anomaly:
        raise HTTPException(status_code=404, detail="Anomaly not found")
    return anomaly


@router.post(
    "/{anomaly_id}/acknowledge",
    response_model=AnomalyResponse,
    dependencies=[Depends(require_role("operator"))],
)
async def acknowledge_anomaly(
    anomaly_id: UUID,
    payload: AnomalyAcknowledgeRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> AnomalyResponse:
    """Mark an anomaly as acknowledged."""
    anomaly = db.query(Anomaly).filter(Anomaly.id == anomaly_id).first()
    if not anomaly:
        raise HTTPException(status_code=404, detail="Anomaly not found")
    anomaly.acknowledged = True
    anomaly.acknowledged_by = payload.acknowledged_by
    anomaly.acknowledged_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(anomaly)
    return anomaly


@router.post(
    "/{anomaly_id}/resolve",
    response_model=AnomalyResponse,
    dependencies=[Depends(require_role("operator"))],
)
async def resolve_anomaly(
    anomaly_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
) -> AnomalyResponse:
    """Mark an anomaly as resolved."""
    anomaly = db.query(Anomaly).filter(Anomaly.id == anomaly_id).first()
    if not anomaly:
        raise HTTPException(status_code=404, detail="Anomaly not found")
    anomaly.resolved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(anomaly)
    return anomaly
