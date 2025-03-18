"""Alert dispatcher — sends anomaly notifications to configured channels."""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from api.models import Alert, WebhookSubscription


class AlertDispatcher:
    """Dispatch alert notifications for detected anomalies."""

    MAX_RETRIES = 3
    BASE_BACKOFF_SECONDS = 2

    def __init__(self, db=None, http_client=None) -> None:
        self.db = db
        self.http_client = http_client or httpx.AsyncClient(timeout=10.0)

    async def dispatch(self, anomaly: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Dispatch alerts for an anomaly to all matching subscriptions."""
        subscriptions = (
            self.db.query(WebhookSubscription)
            .filter(WebhookSubscription.active == True)  # noqa: E712
            .all()
        )

        results = []
        payload = self._format_message(anomaly)
        severity_order = {"INFO": 0, "WARNING": 1, "CRITICAL": 2}

        for sub in subscriptions:
            anomaly_severity = severity_order.get(anomaly.get("severity", "INFO"), 0)
            min_severity = severity_order.get(sub.severity_min, 0)
            if anomaly_severity < min_severity:
                continue
            if (
                sub.anomaly_types
                and anomaly.get("anomaly_type") not in sub.anomaly_types
            ):
                continue

            alert = Alert(
                anomaly_id=uuid.UUID(str(anomaly["id"])),
                alert_type="WEBHOOK",
                target_url=sub.target_url,
                message=str(payload),
                severity=anomaly.get("severity", "INFO"),
                delivery_status="PENDING",
                created_at=datetime.now(timezone.utc),
            )
            self.db.add(alert)
            self.db.flush()

            success = await self._send_webhook(sub.target_url, payload)
            if not success:
                success = await self._retry_with_backoff(
                    sub.target_url, payload, attempt=0
                )

            alert.delivery_status = "DELIVERED" if success else "FAILED"
            alert.sent_at = datetime.now(timezone.utc)
            results.append(
                {
                    "alert_id": str(alert.id),
                    "target_url": sub.target_url,
                    "delivery_status": alert.delivery_status,
                }
            )

        self.db.commit()
        return results

    async def _send_webhook(self, url: str, payload: Dict[str, Any]) -> bool:
        """POST JSON payload to a webhook URL."""
        try:
            response = await self.http_client.post(
                url,
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            return 200 <= response.status_code < 300
        except Exception:
            return False

    async def _retry_with_backoff(
        self,
        url: str,
        payload: Dict[str, Any],
        attempt: int = 0,
    ) -> bool:
        """Retry a failed webhook with exponential backoff."""
        if attempt >= self.MAX_RETRIES:
            return False
        wait = self.BASE_BACKOFF_SECONDS * (2**attempt)
        await asyncio.sleep(wait)
        success = await self._send_webhook(url, payload)
        if not success:
            return await self._retry_with_backoff(url, payload, attempt + 1)
        return True

    async def _send_slack(self, webhook_url: str, anomaly: Dict[str, Any]) -> bool:
        """Format and send a Slack message for an anomaly."""
        severity_emoji = {"CRITICAL": "🔴", "WARNING": "🟡", "INFO": "🟢"}.get(
            anomaly.get("severity", "INFO"), "⚪"
        )
        payload = {
            "text": (
                f"{severity_emoji} RouteMonitor Alert: "
                f"{anomaly.get('anomaly_type')} on {anomaly.get('prefix', 'system')}"
            ),
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"*{anomaly.get('anomaly_type')}* — "
                            f"severity: *{anomaly.get('severity')}*"
                        ),
                    },
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"Prefix: `{anomaly.get('prefix') or 'system-wide'}`\n"
                            f"Speaker: `{anomaly.get('speaker_id')}`"
                        ),
                    },
                },
            ],
        }
        return await self._send_webhook(webhook_url, payload)

    async def _send_pagerduty(self, routing_key: str, anomaly: Dict[str, Any]) -> bool:
        """Send a PagerDuty Events API v2 trigger."""
        payload = {
            "routing_key": routing_key,
            "event_action": "trigger",
            "payload": {
                "summary": (
                    f"RouteMonitor {anomaly.get('anomaly_type')} "
                    f"on {anomaly.get('prefix', 'system')}"
                ),
                "severity": anomaly.get("severity", "info").lower(),
                "source": "RouteMonitor",
                "custom_details": anomaly.get("details", {}),
            },
        }
        return await self._send_webhook(
            "https://events.pagerduty.com/v2/enqueue", payload
        )

    def _format_message(self, anomaly: Dict[str, Any]) -> Dict[str, Any]:
        """Format an anomaly dict as a webhook JSON payload."""
        return {
            "source": "RouteMonitor",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "anomaly_type": anomaly.get("anomaly_type"),
            "severity": anomaly.get("severity"),
            "prefix": anomaly.get("prefix"),
            "speaker_id": str(anomaly.get("speaker_id", "")),
            "details": anomaly.get("details", {}),
            "dashboard_url": f"http://localhost:3000/anomalies/{anomaly.get('id', '')}",
        }

    async def close(self) -> None:
        """Close the HTTP client."""
        if self.http_client:
            await self.http_client.aclose()
