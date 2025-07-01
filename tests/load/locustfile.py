"""Load test for RouteMonitor API using Locust.

Run with:
    pip install locust
    locust -f tests/load/locustfile.py --host=http://localhost:8001

Then open http://localhost:8089 in your browser.

Target metrics:
  - /api/telemetry/bmp/ingest: 1000 req/sec, p99 < 200ms
  - /api/anomalies/:           100 req/sec, p99 < 500ms
  - /api/health:               300 req/sec, p99 < 50ms

429 responses are treated as success (rate limiter working correctly).
"""
from __future__ import annotations

import random

from locust import HttpUser, between, task

from tests.fixtures.bgp_telemetry_generator import MockBGPTelemetryGenerator

_gen = MockBGPTelemetryGenerator()
_UPDATES = [
    _gen.generate_update(f"10.{i//256}.{i%256}.0/24", 65000) for i in range(100)
]
_WITHDRAWS = [
    _gen.generate_withdraw(f"10.{i//256}.{i%256}.0/24", 65000) for i in range(50)
]


def _ok_status(status_code: int) -> bool:
    """Accept success and rate-limit responses."""
    return status_code < 400 or status_code == 429


class BGPTelemetryUser(HttpUser):
    """Simulates a BGP router sending BMP telemetry messages."""

    wait_time = between(0.001, 0.01)

    def on_start(self):
        self.speaker_id = None
        with self.client.post(
            "/api/telemetry/speakers",
            json={
                "hostname": f"load-test-router-{random.randint(1000, 9999)}",
                "router_id": f"10.{random.randint(0, 254)}.0.1",
                "local_asn": random.randint(64512, 65534),
                "bmp_listen_address": f"10.{random.randint(0, 254)}.0.1:179",
            },
            catch_response=True,
            name="/api/telemetry/speakers [register]",
        ) as resp:
            if resp.status_code in (200, 201, 409):
                resp.success()
                if resp.status_code != 409:
                    data = resp.json()
                    self.speaker_id = data.get("id")
            else:
                resp.failure(f"Unexpected {resp.status_code}")

    @task(10)
    def ingest_bmp_update(self):
        msg = random.choice(_UPDATES)
        with self.client.post(
            "/api/telemetry/bmp/ingest",
            data=msg,
            headers={"Content-Type": "application/octet-stream"},
            catch_response=True,
            name="/api/telemetry/bmp/ingest [UPDATE]",
        ) as resp:
            if _ok_status(resp.status_code):
                resp.success()
            else:
                resp.failure(f"Unexpected {resp.status_code}: {resp.text[:100]}")

    @task(3)
    def ingest_bmp_withdraw(self):
        msg = random.choice(_WITHDRAWS)
        with self.client.post(
            "/api/telemetry/bmp/ingest",
            data=msg,
            headers={"Content-Type": "application/octet-stream"},
            catch_response=True,
            name="/api/telemetry/bmp/ingest [WITHDRAW]",
        ) as resp:
            if _ok_status(resp.status_code):
                resp.success()
            else:
                resp.failure(f"Unexpected {resp.status_code}")

    @task(5)
    def list_route_events(self):
        params = {"limit": 100}
        if self.speaker_id:
            params["speaker_id"] = self.speaker_id
        with self.client.get(
            "/api/telemetry/route-events",
            params=params,
            catch_response=True,
            name="/api/telemetry/route-events",
        ) as resp:
            if _ok_status(resp.status_code):
                resp.success()
            else:
                resp.failure(f"Unexpected {resp.status_code}")

    @task(2)
    def list_anomalies(self):
        with self.client.get(
            "/api/anomalies/",
            params={"time_range": "1h", "limit": 50},
            catch_response=True,
            name="/api/anomalies/",
        ) as resp:
            if _ok_status(resp.status_code):
                resp.success()
            else:
                resp.failure(f"Unexpected {resp.status_code}")

    @task(1)
    def health_check(self):
        with self.client.get("/health", catch_response=True, name="/health") as resp:
            if _ok_status(resp.status_code):
                resp.success()
            else:
                resp.failure(f"Unexpected {resp.status_code}")


class DashboardUser(HttpUser):
    """Simulates a human user browsing the dashboard."""

    wait_time = between(2, 10)

    @task(3)
    def view_speakers(self):
        with self.client.get(
            "/api/telemetry/speakers",
            catch_response=True,
            name="/api/telemetry/speakers",
        ) as resp:
            if _ok_status(resp.status_code):
                resp.success()
            else:
                resp.failure(f"Unexpected {resp.status_code}")

    @task(5)
    def view_anomaly_timeline(self):
        with self.client.get(
            "/api/anomalies/",
            params={"time_range": "24h"},
            catch_response=True,
            name="/api/anomalies/ [24h]",
        ) as resp:
            if _ok_status(resp.status_code):
                resp.success()
            else:
                resp.failure(f"Unexpected {resp.status_code}")

    @task(2)
    def view_route_stats(self):
        speakers_resp = self.client.get("/api/telemetry/speakers")
        if not _ok_status(speakers_resp.status_code):
            return
        speakers = speakers_resp.json()
        if speakers:
            sid = speakers[0]["id"]
            with self.client.get(
                f"/api/telemetry/metrics/route-stats/{sid}",
                params={"time_range": "1h"},
                catch_response=True,
                name="/api/telemetry/metrics/route-stats/{id}",
            ) as resp:
                if _ok_status(resp.status_code):
                    resp.success()
                else:
                    resp.failure(f"Unexpected {resp.status_code}")

    @task(1)
    def view_correlation(self):
        with self.client.get(
            "/api/metrics/correlation",
            params={"time_range": "7d"},
            catch_response=True,
            name="/api/metrics/correlation",
        ) as resp:
            if _ok_status(resp.status_code):
                resp.success()
            else:
                resp.failure(f"Unexpected {resp.status_code}")
