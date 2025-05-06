"""Unit tests for the health check endpoint."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.dependencies import get_db
from api.main import app


@pytest.fixture
def health_client():
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


def _override_db(mock_db: MagicMock):
    def _get_db():
        try:
            yield mock_db
        finally:
            pass

    app.dependency_overrides[get_db] = _get_db


class TestHealthCheck:
    def test_all_services_healthy(self, health_client):
        mock_db = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        _override_db(mock_db)

        with (
            patch("api.routes.health.celery_app") as mock_celery,
            patch("api.routes.health.httpx.get", return_value=mock_response),
        ):
            mock_celery.control.ping.return_value = [{"worker": "pong"}]
            response = health_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["services"] == {"db": "ok", "redis": "ok", "influxdb": "ok"}
        mock_db.execute.assert_called_once()

    def test_db_failure_marks_unhealthy(self, health_client):
        mock_db = MagicMock()
        mock_db.execute.side_effect = Exception("connection refused")
        mock_response = MagicMock()
        mock_response.status_code = 200
        _override_db(mock_db)

        with (
            patch("api.routes.health.celery_app") as mock_celery,
            patch("api.routes.health.httpx.get", return_value=mock_response),
        ):
            mock_celery.control.ping.return_value = [{"worker": "pong"}]
            response = health_client.get("/health")

        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["services"]["db"] == "error"

    def test_redis_failure_marks_unhealthy(self, health_client):
        mock_db = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 200
        _override_db(mock_db)

        with (
            patch("api.routes.health.celery_app") as mock_celery,
            patch("api.routes.health.httpx.get", return_value=mock_response),
        ):
            mock_celery.control.ping.return_value = []
            response = health_client.get("/health")

        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["services"]["redis"] == "error"

    def test_influxdb_failure_marks_unhealthy(self, health_client):
        mock_db = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 503
        _override_db(mock_db)

        with (
            patch("api.routes.health.celery_app") as mock_celery,
            patch("api.routes.health.httpx.get", return_value=mock_response),
        ):
            mock_celery.control.ping.return_value = [{"worker": "pong"}]
            response = health_client.get("/health")

        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["services"]["influxdb"] == "error"
