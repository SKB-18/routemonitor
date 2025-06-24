"""Phase 6 end-to-end smoke test: BMP ingest → flap storm → anomaly detection.

Run inside Docker:
    docker compose exec api python tests/phase6_e2e_smoke.py

Run from host (API on 8001):
    python tests/phase6_e2e_smoke.py --host http://localhost:8001
"""
from __future__ import annotations

import argparse
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from tests.fixtures.bgp_telemetry_generator import MockBGPTelemetryGenerator

PASS = FAIL = 0
API = "http://localhost:8000"


def check(name: str, fn) -> None:
    global PASS, FAIL
    try:
        fn()
        PASS += 1
        print(f"  PASS  {name}")
    except Exception as e:
        FAIL += 1
        print(f"  FAIL  {name}: {e}")


def main() -> int:
    global API
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=API)
    args = parser.parse_args()
    API = args.host.rstrip("/")

    print("=" * 60)
    print("Phase 6 E2E Smoke Test")
    print(f"API: {API}")
    print("=" * 60)

    gen = MockBGPTelemetryGenerator()
    speaker_hostname = f"e2e-router-{uuid.uuid4().hex[:6]}"

    with httpx.Client(base_url=API, timeout=60.0, follow_redirects=True) as client:

        def health():
            r = client.get("/health")
            assert r.status_code == 200
            assert r.json()["status"] == "healthy"

        def register_speaker():
            nonlocal speaker_id
            r = client.post(
                "/api/telemetry/speakers",
                json={
                    "hostname": speaker_hostname,
                    "router_id": "10.99.0.1",
                    "local_asn": 65099,
                    "bmp_listen_address": "10.99.0.1:179",
                },
            )
            assert r.status_code in (200, 201), r.text
            speaker_id = r.json()["id"]

        def ingest_updates():
            for i in range(50):
                msg = gen.generate_update(f"10.{i // 256}.{i % 256}.0/24", 65099)
                r = client.post(
                    "/api/telemetry/bmp/ingest",
                    content=msg,
                    headers={"Content-Type": "application/octet-stream"},
                )
                assert r.status_code == 202, f"update {i}: {r.status_code} {r.text}"

        def verify_route_events():
            r = client.get("/api/telemetry/route-events", params={"limit": 5})
            assert r.status_code == 200
            events = r.json()
            assert len(events) >= 1, "Expected route events after BMP ingest"

        def flap_storm():
            for msg in gen.simulate_route_flap("e2e", "192.168.0.0/24", num_flaps=25):
                r = client.post(
                    "/api/telemetry/bmp/ingest",
                    content=msg,
                    headers={"Content-Type": "application/octet-stream"},
                )
                assert r.status_code == 202, r.text

        def trigger_detection():
            """Queue anomaly detection for our speaker (don't wait for Celery beat)."""
            import subprocess

            subprocess.run(
                [
                    sys.executable,
                    "-c",
                    f"""
from tasks.ingestion import detect_anomalies_task
detect_anomalies_task.apply(args=["{speaker_id}"])
""",
                ],
                cwd=str(Path(__file__).resolve().parent.parent),
                check=True,
            )

        def verify_anomalies():
            time.sleep(5)
            r = client.get("/api/anomalies/", params={"time_range": "1h", "limit": 50})
            assert r.status_code == 200
            anomalies = r.json()
            assert (
                len(anomalies) >= 1
            ), "No anomalies after flap storm — check celery logs"
            types = {a["anomaly_type"] for a in anomalies}
            print(f"       Anomaly types detected: {types}")
            assert any(
                t in types
                for t in ("ROUTE_FLAP", "UNUSUAL_CHURN", "CORRELATED_FAILURE")
            ), f"Unexpected anomaly types: {types}"

        speaker_id = None
        check("GET /health", health)
        check("Register speaker", register_speaker)
        check("Ingest 50 BMP updates", ingest_updates)
        check("Route events stored", verify_route_events)
        check("Flap storm simulation", flap_storm)
        check("Trigger detect_anomalies_task", trigger_detection)
        check("Anomaly detected", verify_anomalies)

    print("\n" + "=" * 60)
    print(f"RESULTS: {PASS} passed, {FAIL} failed")
    print("=" * 60)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
