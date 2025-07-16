"""Integration tests for Phase 5: middleware, metrics, and extended RBAC."""
import uuid

import pytest


def _login(auth_client, username: str, password: str) -> str:
    resp = auth_client.post(
        "/api/auth/token",
        data={"username": username, "password": password},
    )
    assert resp.status_code == 200
    return resp.json()["access_token"]


@pytest.fixture
def admin_token(auth_client) -> str:
    return _login(auth_client, "admin", "admin123")


@pytest.fixture
def operator_token(auth_client) -> str:
    return _login(auth_client, "operator", "operator123")


@pytest.fixture
def readonly_token(auth_client) -> str:
    return _login(auth_client, "readonly", "readonly123")


@pytest.mark.integration
class TestMiddlewareHeaders:
    def test_health_returns_request_id(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert "X-Request-ID" in resp.headers
        uuid.UUID(resp.headers["X-Request-ID"])

    def test_request_ids_are_unique(self, client):
        ids = {client.get("/health").headers["X-Request-ID"] for _ in range(5)}
        assert len(ids) == 5


@pytest.mark.integration
class TestPrometheusEndpoint:
    def test_metrics_endpoint_exposes_routemonitor_counters(self, client):
        client.get("/health")
        resp = client.get("/metrics")
        assert resp.status_code == 200
        body = resp.text
        assert "routemonitor_http_requests_total" in body
        assert "routemonitor_http_request_duration_seconds" in body
        assert "routemonitor_bmp_messages_total" in body
        assert "routemonitor_anomalies_detected_total" in body
        assert "routemonitor_alerts_dispatched_total" in body


@pytest.mark.integration
class TestExtendedRBAC:
    def test_readonly_cannot_acknowledge(
        self, auth_client, mock_anomaly, readonly_token
    ):
        resp = auth_client.post(
            f"/api/anomalies/{mock_anomaly.id}/acknowledge",
            json={"acknowledged_by": "readonly-user"},
            headers={"Authorization": f"Bearer {readonly_token}"},
        )
        assert resp.status_code == 403

    def test_operator_can_acknowledge(self, auth_client, mock_anomaly, operator_token):
        resp = auth_client.post(
            f"/api/anomalies/{mock_anomaly.id}/acknowledge",
            json={"acknowledged_by": "ops"},
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["acknowledged"] is True

    def test_operator_can_retry_failed_alert(
        self, auth_client, db_session, mock_anomaly, operator_token
    ):
        from datetime import datetime, timezone

        from api.models import Alert

        alert = Alert(
            id=uuid.uuid4(),
            anomaly_id=mock_anomaly.id,
            alert_type="WEBHOOK",
            target_url="https://example.com/hook",
            message="test",
            severity="WARNING",
            delivery_status="FAILED",
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(alert)
        db_session.commit()

        resp = auth_client.post(
            f"/api/alerts/{alert.id}/retry",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "retry_queued"

    def test_readonly_cannot_register_webhook(self, auth_client, readonly_token):
        resp = auth_client.post(
            "/api/alerts/webhooks",
            json={"target_url": "https://example.com/hook"},
            headers={"Authorization": f"Bearer {readonly_token}"},
        )
        assert resp.status_code == 403

    def test_invalid_bearer_token_rejected(self, auth_client, mock_anomaly):
        resp = auth_client.post(
            f"/api/anomalies/{mock_anomaly.id}/acknowledge",
            json={"acknowledged_by": "bad"},
            headers={"Authorization": "Bearer not-a-valid-jwt"},
        )
        assert resp.status_code == 401

    def test_public_endpoints_work_without_auth(self, auth_client, mock_anomaly):
        resp = auth_client.get("/api/anomalies/")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

        resp2 = auth_client.get(f"/api/anomalies/{mock_anomaly.id}")
        assert resp2.status_code == 200


@pytest.mark.integration
class TestAuthTokenRoles:
    def test_all_builtin_users_can_login(self, auth_client):
        for user, password in [
            ("admin", "admin123"),
            ("operator", "operator123"),
            ("readonly", "readonly123"),
        ]:
            resp = auth_client.post(
                "/api/auth/token",
                data={"username": user, "password": password},
            )
            assert resp.status_code == 200, user
            assert resp.json()["token_type"] == "bearer"

    def test_token_me_reflects_role(self, auth_client, operator_token):
        resp = auth_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {operator_token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["username"] == "operator"
        assert resp.json()["role"] == "operator"
