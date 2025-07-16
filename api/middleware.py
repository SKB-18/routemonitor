"""Production middleware: rate limiting, request ID injection, structured logging.

Cursor implements the rate limiter in Phase 5.
"""
from __future__ import annotations

import time
import uuid
from typing import Callable

import structlog
from fastapi import Request, Response
from prometheus_client import Counter, Histogram
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger(__name__)

# ─── Prometheus custom metrics ────────────────────────────────────────────────

REQUEST_COUNT = Counter(
    "routemonitor_http_requests_total",
    "Total HTTP request count",
    ["method", "endpoint", "status_code"],
)

REQUEST_LATENCY = Histogram(
    "routemonitor_http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0],
)

BMP_MESSAGES_INGESTED = Counter(
    "routemonitor_bmp_messages_total",
    "Total BMP messages ingested",
    ["message_type"],
)

ANOMALIES_DETECTED = Counter(
    "routemonitor_anomalies_detected_total",
    "Total anomalies detected",
    ["anomaly_type", "severity"],
)

ALERTS_DISPATCHED = Counter(
    "routemonitor_alerts_dispatched_total",
    "Total alerts dispatched",
    ["alert_type", "delivery_status"],
)

ACTIVE_BGP_SPEAKERS = Counter(
    "routemonitor_bgp_speakers_active",
    "Number of BGP speakers currently connected",
)


# ─── Request ID + logging middleware ──────────────────────────────────────────


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Inject X-Request-ID header and log every request with latency.

    Adds:
      - X-Request-ID response header (UUID)
      - Structured log: method, path, status, duration_ms

    [CURSOR: This middleware is already implemented — just register it in main.py]
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = str(uuid.uuid4())
        start = time.perf_counter()

        # Attach request_id so route handlers can reference it
        request.state.request_id = request_id

        response = await call_next(request)

        duration_ms = (time.perf_counter() - start) * 1000
        path = request.url.path

        # Record Prometheus metrics
        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=path,
            status_code=str(response.status_code),
        ).inc()
        REQUEST_LATENCY.labels(
            method=request.method,
            endpoint=path,
        ).observe(duration_ms / 1000)

        logger.info(
            "http_request",
            request_id=request_id,
            method=request.method,
            path=path,
            status=response.status_code,
            duration_ms=round(duration_ms, 2),
        )

        response.headers["X-Request-ID"] = request_id
        return response


# ─── Rate Limiter middleware ───────────────────────────────────────────────────


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Sliding-window rate limiter backed by Redis.

    Default limits:
      - /api/telemetry/bmp/ingest → 1000 req/min per IP
      - /api/anomalies/           → 100  req/min per IP
      - all other endpoints       → 300  req/min per IP

    [CURSOR TO IMPLEMENT - Phase 5]:

        Uses redis-py to implement a sliding-window counter:

        async def dispatch(self, request: Request, call_next: Callable) -> Response:
            import redis
            from core.config import settings

            client_ip = request.client.host
            path      = request.url.path
            limit     = self._get_limit(path)
            window    = 60   # seconds

            r = redis.from_url(settings.REDIS_URL)
            key = f"rate_limit:{client_ip}:{path}"

            pipe = r.pipeline()
            now  = int(time.time())
            pipe.zremrangebyscore(key, 0, now - window)
            pipe.zcard(key)
            pipe.zadd(key, {str(uuid.uuid4()): now})
            pipe.expire(key, window)
            _, count, _, _ = pipe.execute()

            if count >= limit:
                return Response(
                    content='{"detail":"Rate limit exceeded. Retry after 60 seconds."}',
                    status_code=429,
                    headers={
                        "Content-Type": "application/json",
                        "Retry-After": "60",
                        "X-RateLimit-Limit": str(limit),
                        "X-RateLimit-Remaining": "0",
                    },
                )

            response = await call_next(request)
            response.headers["X-RateLimit-Limit"] = str(limit)
            response.headers["X-RateLimit-Remaining"] = str(max(0, limit - count - 1))
            return response

        def _get_limit(self, path: str) -> int:
            if "/bmp/ingest" in path:
                return 1000
            if "/anomalies" in path:
                return 100
            return 300
    """

    def _get_limit(self, path: str) -> int:
        if "/bmp/ingest" in path:
            return 1000
        if "/anomalies" in path:
            return 100
        return 300

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        import os

        import redis as redis_lib

        from core.config import settings

        if os.getenv("TESTING") == "1":
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        path = request.url.path
        limit = self._get_limit(path)
        window = 60

        r = redis_lib.from_url(settings.REDIS_URL, decode_responses=True)
        key = f"rate_limit:{client_ip}:{path}"
        now = int(time.time())

        pipe = r.pipeline()
        pipe.zremrangebyscore(key, 0, now - window)
        pipe.zcard(key)
        pipe.zadd(key, {str(uuid.uuid4()): now})
        pipe.expire(key, window)
        _, count, _, _ = pipe.execute()

        remaining = max(0, limit - count - 1)

        if count >= limit:
            return Response(
                content='{"detail":"Rate limit exceeded. Retry after 60 seconds."}',
                status_code=429,
                media_type="application/json",
                headers={
                    "Retry-After": "60",
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
