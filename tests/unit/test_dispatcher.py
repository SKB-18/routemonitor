"""Unit tests for the alert dispatcher."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from api.models import Alert, Anomaly, WebhookSubscription
from core.dispatcher import AlertDispatcher


def _anomaly_dict(anomaly: Anomaly) -> dict:
    return {
        "id": str(anomaly.id),
        "anomaly_type": anomaly.anomaly_type,
        "severity": anomaly.severity,
        "prefix": anomaly.prefix,
        "speaker_id": str(anomaly.speaker_id),
        "details": anomaly.details or {},
    }


@pytest.fixture
def mock_http_client():
    client = AsyncMock()
    client.post = AsyncMock(return_value=MagicMock(status_code=200))
    client.aclose = AsyncMock()
    return client


class TestFormatMessage:
    def test_format_message_structure(self, mock_anomaly):
        dispatcher = AlertDispatcher()
        payload = dispatcher._format_message(_anomaly_dict(mock_anomaly))
        assert payload["source"] == "RouteMonitor"
        assert payload["anomaly_type"] == mock_anomaly.anomaly_type
        assert payload["severity"] == mock_anomaly.severity
        assert "dashboard_url" in payload
        assert str(mock_anomaly.id) in payload["dashboard_url"]


class TestSendWebhook:
    @pytest.mark.asyncio
    async def test_send_webhook_success(self, mock_http_client):
        dispatcher = AlertDispatcher(http_client=mock_http_client)
        ok = await dispatcher._send_webhook("https://example.com/hook", {"test": True})
        assert ok is True
        mock_http_client.post.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_send_webhook_failure_status(self, mock_http_client):
        mock_http_client.post.return_value = MagicMock(status_code=500)
        dispatcher = AlertDispatcher(http_client=mock_http_client)
        ok = await dispatcher._send_webhook("https://example.com/hook", {})
        assert ok is False

    @pytest.mark.asyncio
    async def test_send_webhook_exception(self, mock_http_client):
        mock_http_client.post.side_effect = RuntimeError("network down")
        dispatcher = AlertDispatcher(http_client=mock_http_client)
        ok = await dispatcher._send_webhook("https://example.com/hook", {})
        assert ok is False


class TestDispatch:
    @pytest.mark.asyncio
    async def test_dispatch_delivers_to_matching_subscription(
        self, db_session, mock_anomaly, mock_http_client
    ):
        sub = WebhookSubscription(
            target_url="https://example.com/hook",
            severity_min="INFO",
            anomaly_types=["ROUTE_FLAP"],
            active=True,
        )
        db_session.add(sub)
        db_session.commit()

        dispatcher = AlertDispatcher(db=db_session, http_client=mock_http_client)
        results = await dispatcher.dispatch(_anomaly_dict(mock_anomaly))

        assert len(results) == 1
        assert results[0]["delivery_status"] == "DELIVERED"
        alerts = db_session.query(Alert).all()
        assert len(alerts) == 1
        assert alerts[0].delivery_status == "DELIVERED"

    @pytest.mark.asyncio
    async def test_dispatch_skips_severity_below_minimum(
        self, db_session, mock_anomaly, mock_http_client
    ):
        mock_anomaly.severity = "INFO"
        db_session.commit()

        sub = WebhookSubscription(
            target_url="https://example.com/hook",
            severity_min="CRITICAL",
            anomaly_types=["ROUTE_FLAP"],
            active=True,
        )
        db_session.add(sub)
        db_session.commit()

        dispatcher = AlertDispatcher(db=db_session, http_client=mock_http_client)
        results = await dispatcher.dispatch(_anomaly_dict(mock_anomaly))
        assert results == []
        assert db_session.query(Alert).count() == 0

    @pytest.mark.asyncio
    async def test_dispatch_skips_unsubscribed_anomaly_type(
        self, db_session, mock_anomaly, mock_http_client
    ):
        sub = WebhookSubscription(
            target_url="https://example.com/hook",
            severity_min="INFO",
            anomaly_types=["CORRELATED_FAILURE"],
            active=True,
        )
        db_session.add(sub)
        db_session.commit()

        dispatcher = AlertDispatcher(db=db_session, http_client=mock_http_client)
        results = await dispatcher.dispatch(_anomaly_dict(mock_anomaly))
        assert results == []

    @pytest.mark.asyncio
    async def test_dispatch_marks_failed_after_retries(
        self, db_session, mock_anomaly, mock_http_client
    ):
        mock_http_client.post.return_value = MagicMock(status_code=503)
        sub = WebhookSubscription(
            target_url="https://example.com/hook",
            severity_min="INFO",
            anomaly_types=["ROUTE_FLAP"],
            active=True,
        )
        db_session.add(sub)
        db_session.commit()

        dispatcher = AlertDispatcher(db=db_session, http_client=mock_http_client)
        with patch("core.dispatcher.asyncio.sleep", new_callable=AsyncMock):
            results = await dispatcher.dispatch(_anomaly_dict(mock_anomaly))

        assert results[0]["delivery_status"] == "FAILED"
        assert mock_http_client.post.await_count >= 2

    @pytest.mark.asyncio
    async def test_send_slack_formats_payload(self, mock_http_client):
        dispatcher = AlertDispatcher(http_client=mock_http_client)
        anomaly = {
            "anomaly_type": "ROUTE_FLAP",
            "severity": "CRITICAL",
            "prefix": "10.0.0.0/24",
            "speaker_id": str(uuid.uuid4()),
        }
        ok = await dispatcher._send_slack("https://hooks.slack.com/test", anomaly)
        assert ok is True
        call_kwargs = mock_http_client.post.call_args.kwargs
        assert "blocks" in call_kwargs["json"]
