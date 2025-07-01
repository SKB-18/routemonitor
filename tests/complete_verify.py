"""Live endpoint sweep — hits every RouteMonitor HTTP route against a running stack.

Run inside Docker:
    docker compose exec api python tests/complete_verify.py

From host:
    python tests/complete_verify.py --host http://localhost:8001
"""
from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from tests.fixtures.bgp_telemetry_generator import MockBGPTelemetryGenerator

PASS = FAIL = 0
API = "http://localhost:8000"
RESULTS: list[tuple[str, str, str]] = []


def check(name: str, fn) -> None:
    global PASS, FAIL
    try:
        fn()
        PASS += 1
        RESULTS.append(("PASS", name, ""))
        print(f"  PASS  {name}")
    except Exception as e:
        FAIL += 1
        RESULTS.append(("FAIL", name, str(e)))
        print(f"  FAIL  {name}: {e}")


def main() -> int:
    global API
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=API)
    args = parser.parse_args()
    API = args.host.rstrip("/")

    print("=" * 60)
    print("RouteMonitor Complete Endpoint Verification")
    print(f"API: {API}")
    print("=" * 60)

    gen = MockBGPTelemetryGenerator()
    speaker_id = None
    anomaly_id = None
    admin_token = None

    with httpx.Client(base_url=API, timeout=60.0, follow_redirects=True) as c:

        def health():
            r = c.get("/health")
            assert r.status_code == 200

        def openapi():
            r = c.get("/openapi.json")
            assert r.status_code == 200
            assert len(r.json()["paths"]) >= 15

        def docs():
            assert c.get("/docs").status_code == 200
            assert c.get("/redoc").status_code == 200

        def metrics_prom():
            c.get("/health")
            r = c.get("/metrics")
            assert r.status_code == 200
            assert "routemonitor_" in r.text

        def auth_token():
            nonlocal admin_token
            r = c.post(
                "/api/auth/token", data={"username": "admin", "password": "admin123"}
            )
            assert r.status_code == 200
            admin_token = r.json()["access_token"]

        def auth_me():
            r = c.get(
                "/api/auth/me", headers={"Authorization": f"Bearer {admin_token}"}
            )
            assert r.status_code == 200

        def register_speaker():
            nonlocal speaker_id
            r = c.post(
                "/api/telemetry/speakers",
                json={
                    "hostname": f"verify-{uuid.uuid4().hex[:6]}",
                    "router_id": "10.66.0.1",
                    "local_asn": 65066,
                    "bmp_listen_address": "10.66.0.1:179",
                },
            )
            assert r.status_code in (200, 201)
            speaker_id = r.json()["id"]

        def list_speakers():
            r = c.get("/api/telemetry/speakers")
            assert r.status_code == 200

        def get_speaker():
            r = c.get(f"/api/telemetry/speakers/{speaker_id}")
            assert r.status_code == 200

        def speaker_status():
            r = c.get(f"/api/telemetry/speakers/{speaker_id}/status")
            assert r.status_code == 200

        def bmp_ingest():
            msg = gen.generate_update("10.66.5.0/24", 65066)
            r = c.post(
                "/api/telemetry/bmp/ingest",
                content=msg,
                headers={"Content-Type": "application/octet-stream"},
            )
            assert r.status_code == 202

        def route_events():
            r = c.get("/api/telemetry/route-events", params={"limit": 5})
            assert r.status_code == 200

        def telemetry_route_stats():
            r = c.get(f"/api/telemetry/metrics/route-stats/{speaker_id}")
            assert r.status_code == 200

        def telemetry_correlation_501():
            r = c.get("/api/telemetry/metrics/correlation")
            assert r.status_code == 501

        def metrics_speaker():
            r = c.get(f"/api/metrics/speaker/{speaker_id}")
            assert r.status_code == 200

        def metrics_correlation():
            r = c.get("/api/metrics/correlation", params={"time_range": "7d"})
            assert r.status_code == 200

        def list_anomalies():
            nonlocal anomaly_id
            r = c.get("/api/anomalies/", params={"time_range": "24h"})
            assert r.status_code == 200
            data = r.json()
            if data:
                anomaly_id = data[0]["id"]

        def forecast():
            r = c.get(f"/api/anomalies/forecast/{speaker_id}")
            assert r.status_code == 200

        def get_anomaly():
            if not anomaly_id:
                return
            r = c.get(f"/api/anomalies/{anomaly_id}")
            assert r.status_code == 200

        def acknowledge_anomaly():
            if not anomaly_id:
                return
            token = c.post(
                "/api/auth/token",
                data={"username": "operator", "password": "operator123"},
            ).json()["access_token"]
            r = c.post(
                f"/api/anomalies/{anomaly_id}/acknowledge",
                json={"acknowledged_by": "verify"},
                headers={"Authorization": f"Bearer {token}"},
            )
            assert r.status_code == 200

        def register_webhook():
            r = c.post(
                "/api/alerts/webhooks",
                json={
                    "target_url": f"https://example.com/hook-{uuid.uuid4().hex[:6]}",
                    "severity_min": "WARNING",
                },
                headers={"Authorization": f"Bearer {admin_token}"},
            )
            assert r.status_code == 201

        def alert_history():
            r = c.get("/api/alerts/history", params={"limit": 10})
            assert r.status_code == 200

        check("GET /health", health)
        check("GET /openapi.json", openapi)
        check("GET /docs + /redoc", docs)
        check("GET /metrics", metrics_prom)
        check("POST /api/auth/token", auth_token)
        check("GET /api/auth/me", auth_me)
        check("POST /api/telemetry/speakers", register_speaker)
        check("GET /api/telemetry/speakers", list_speakers)
        check("GET /api/telemetry/speakers/{id}", get_speaker)
        check("GET /api/telemetry/speakers/{id}/status", speaker_status)
        check("POST /api/telemetry/bmp/ingest", bmp_ingest)
        check("GET /api/telemetry/route-events", route_events)
        check("GET /api/telemetry/metrics/route-stats/{id}", telemetry_route_stats)
        check("GET /api/telemetry/metrics/correlation (501)", telemetry_correlation_501)
        check("GET /api/metrics/speaker/{id}", metrics_speaker)
        check("GET /api/metrics/correlation", metrics_correlation)
        check("GET /api/anomalies/", list_anomalies)
        check("GET /api/anomalies/forecast/{id}", forecast)
        check("GET /api/anomalies/{id}", get_anomaly)
        check("POST /api/anomalies/{id}/acknowledge", acknowledge_anomaly)
        check("POST /api/alerts/webhooks", register_webhook)
        check("GET /api/alerts/history", alert_history)

    print("\n" + "=" * 60)
    print(f"ENDPOINT SWEEP: {PASS} passed, {FAIL} failed")
    print("=" * 60)
    if FAIL:
        for status, name, detail in RESULTS:
            if status == "FAIL":
                print(f"  - {name}: {detail}")
        return 1
    print("\nAll endpoints responding correctly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
