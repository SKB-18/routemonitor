"""Alert subscription management endpoints."""
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from api.auth import require_role
from api.dependencies import get_db
from api.models import Alert, WebhookSubscription
from api.schemas import AlertResponse, AlertWebhookRequest
from tasks.ingestion import dispatch_alerts_task

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.post(
    "/webhooks",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role("admin"))],
)
async def register_webhook(
    payload: AlertWebhookRequest,
    db: Session = Depends(get_db),
) -> dict:
    """Register a webhook URL to receive anomaly alerts."""
    sub = WebhookSubscription(
        target_url=payload.target_url,
        severity_min=payload.severity_min,
        anomaly_types=payload.anomaly_types,
        active=True,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return {
        "subscription_id": str(sub.id),
        "target_url": sub.target_url,
        "status": "active",
    }


@router.get("/history", response_model=List[AlertResponse])
async def alert_history(
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
) -> List[AlertResponse]:
    """Fetch recent alert delivery records."""
    return db.query(Alert).order_by(Alert.created_at.desc()).limit(limit).all()


@router.post("/{alert_id}/retry", dependencies=[Depends(require_role("operator"))])
async def retry_alert(
    alert_id: UUID,
    db: Session = Depends(get_db),
) -> dict:
    """Manually retry a failed alert."""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.delivery_status != "FAILED":
        raise HTTPException(status_code=400, detail="Only FAILED alerts can be retried")

    dispatch_alerts_task.delay(str(alert.anomaly_id))
    return {"status": "retry_queued", "alert_id": str(alert_id)}
