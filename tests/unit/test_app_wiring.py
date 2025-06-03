"""Verify FastAPI application wiring for Phases 1–5."""
import pytest
from starlette.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from api.main import app
from api.middleware import RateLimitMiddleware, RequestIDMiddleware


@pytest.mark.unit
class TestAppMetadata:
    def test_app_title_and_version(self):
        assert app.title == "RouteMonitor"
        assert app.version == "0.1.0"

    def test_docs_endpoints_enabled(self):
        assert app.docs_url == "/docs"
        assert app.redoc_url == "/redoc"


@pytest.mark.unit
class TestRoutersRegistered:
    @pytest.fixture
    def route_paths(self):
        return {getattr(r, "path", None) for r in app.routes}

    def test_health_route(self, route_paths):
        assert "/health" in route_paths

    def test_auth_routes(self, route_paths):
        assert "/api/auth/token" in route_paths
        assert "/api/auth/me" in route_paths

    def test_telemetry_routes(self, route_paths):
        assert "/api/telemetry/speakers" in route_paths
        assert "/api/telemetry/bmp/ingest" in route_paths

    def test_anomaly_routes(self, route_paths):
        assert "/api/anomalies/" in route_paths

    def test_alert_routes(self, route_paths):
        assert "/api/alerts/webhooks" in route_paths
        assert "/api/alerts/history" in route_paths

    def test_metrics_routes(self, route_paths):
        paths = {getattr(r, "path", "") for r in app.routes}
        assert any("/api/metrics/correlation" in p for p in paths)


@pytest.mark.unit
class TestMiddlewareStack:
    def test_request_id_middleware_present(self):
        classes = [m.cls for m in app.user_middleware]
        assert RequestIDMiddleware in classes

    def test_rate_limit_middleware_present(self):
        classes = [m.cls for m in app.user_middleware]
        assert RateLimitMiddleware in classes

    def test_cors_middleware_present(self):
        classes = [m.cls for m in app.user_middleware]
        assert CORSMiddleware in classes

    def test_trusted_host_middleware_present(self):
        classes = [m.cls for m in app.user_middleware]
        assert TrustedHostMiddleware in classes

    def test_metrics_mount_exists(self):
        mount_paths = [
            getattr(r, "path", None) for r in app.routes if hasattr(r, "app")
        ]
        assert "/metrics" in mount_paths
