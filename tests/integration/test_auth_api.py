"""Integration tests for JWT auth endpoints."""
import pytest


@pytest.mark.integration
class TestAuth:
    def test_login_valid_credentials(self, auth_client):
        resp = auth_client.post(
            "/api/auth/token",
            data={"username": "operator", "password": "operator123"},
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()
        assert resp.json()["token_type"] == "bearer"

    def test_login_invalid_credentials(self, auth_client):
        resp = auth_client.post(
            "/api/auth/token",
            data={"username": "operator", "password": "wrong"},
        )
        assert resp.status_code == 401

    def test_whoami_with_valid_token(self, auth_client):
        token_resp = auth_client.post(
            "/api/auth/token",
            data={"username": "admin", "password": "admin123"},
        )
        token = token_resp.json()["access_token"]
        resp = auth_client.get(
            "/api/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["username"] == "admin"
        assert resp.json()["role"] == "admin"

    def test_protected_endpoint_without_token(self, auth_client, mock_anomaly):
        resp = auth_client.post(
            f"/api/anomalies/{mock_anomaly.id}/acknowledge",
            json={"acknowledged_by": "test"},
        )
        assert resp.status_code == 401

    def test_operator_cannot_manage_webhooks(self, auth_client):
        token_resp = auth_client.post(
            "/api/auth/token",
            data={"username": "operator", "password": "operator123"},
        )
        token = token_resp.json()["access_token"]
        resp = auth_client.post(
            "/api/alerts/webhooks",
            json={"target_url": "https://example.com/hook"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 403

    def test_admin_can_manage_webhooks(self, auth_client):
        token_resp = auth_client.post(
            "/api/auth/token",
            data={"username": "admin", "password": "admin123"},
        )
        token = token_resp.json()["access_token"]
        resp = auth_client.post(
            "/api/alerts/webhooks",
            json={
                "target_url": "https://example.com/hook",
                "severity_min": "WARNING",
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201

    def test_readonly_login_succeeds(self, auth_client):
        resp = auth_client.post(
            "/api/auth/token",
            data={"username": "readonly", "password": "readonly123"},
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_missing_auth_header_on_me_returns_401(self, auth_client):
        resp = auth_client.get("/api/auth/me")
        assert resp.status_code == 401

    def test_operator_can_resolve_anomaly(self, auth_client, mock_anomaly):
        token_resp = auth_client.post(
            "/api/auth/token",
            data={"username": "operator", "password": "operator123"},
        )
        token = token_resp.json()["access_token"]
        resp = auth_client.post(
            f"/api/anomalies/{mock_anomaly.id}/resolve",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        assert resp.json()["resolved_at"] is not None
