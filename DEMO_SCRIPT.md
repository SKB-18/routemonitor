# RouteMonitor — Demo Script

Use this for interview demos, video recordings, and live presentations.
Total runtime: ~3 minutes for the short version, ~8 minutes for the full version.

---

## Pre-Demo Setup (5 min before)

```bash
# Start the full stack
docker compose up -d

# Wait for healthy
docker compose ps   # all should show "healthy"

# Run migrations (first time only)
docker compose exec api alembic upgrade head

# Start the BGP simulator in the background
docker compose --profile simulation up bmp-simulator -d

# Open browser tabs:
# Tab 1: http://localhost:8001/docs      (Swagger UI)
# Tab 2: http://localhost:8501           (Streamlit dashboard)
# Tab 3: http://localhost:3000           (Grafana)
```

---

## Short Version (3 minutes)

### 1. Architecture (30s)
Open `ARCHITECTURE.md` or draw on whiteboard:
> "RouteMonitor has four layers: ingestion via BMP TCP, processing via Celery,
> detection via ML, and visualization via Streamlit."

### 2. Show the running system (30s)
```bash
curl http://localhost:8001/health
```
> "Everything is live — FastAPI, PostgreSQL, InfluxDB, Redis."

### 3. Ingest a BGP update (30s)
```bash
python - << 'EOF'
from tests.fixtures.bgp_telemetry_generator import MockBGPTelemetryGenerator
import httpx
gen = MockBGPTelemetryGenerator()
msg = gen.generate_update("10.0.0.0/24", 65001, as_path=[65001, 65002, 65003])
resp = httpx.post("http://localhost:8001/api/telemetry/bmp/ingest", content=msg)
print(f"Status: {resp.status_code}, Task: {resp.json()}")
EOF
```
> "202 Accepted — the BMP message is queued to Celery for async processing."

### 4. Show the stored event (15s)
```bash
curl "http://localhost:8001/api/telemetry/route-events?limit=1"
```
> "The route update is parsed and stored with full path attributes — AS path, next hop, communities."

### 5. Show the dashboard (45s)
Switch to Streamlit tab.
- Route Timeline: select a speaker, fetch events, show the scatter chart
- Anomaly Timeline: show any detected anomalies

### 6. Trigger an anomaly (30s)
```bash
python - << 'EOF'
from tests.fixtures.bgp_telemetry_generator import MockBGPTelemetryGenerator
import httpx
gen = MockBGPTelemetryGenerator()
# Simulate 20 rapid flaps
for msg in gen.simulate_route_flap("demo-router", "10.0.0.0/24", num_flaps=20):
    httpx.post("http://localhost:8001/api/telemetry/bmp/ingest", content=msg)
print("Flap simulation complete — check /api/anomalies/ in ~30 seconds")
EOF
```

---

## Full Version (8 minutes)

### Scene 1: The Problem (1 min)

> "BGP is the routing protocol of the internet. When a link goes down or a route
> flaps, every router in the affected AS needs to converge — re-learn the best path.
> At scale, networks see millions of updates per minute. Detecting whether those
> updates represent normal churn or a real problem requires both statistical baselines
> and ML."

### Scene 2: BMP Protocol (1 min)

```bash
# Show the raw binary parser
cat core/bmp_parser.py | head -50
```

> "BMP is a binary protocol defined in RFC 7854. Each message has a 6-byte header:
> version (1), total length (4), message type (1). I implemented the full parser
> including path attribute decoding — AS_PATH, NEXT_HOP, COMMUNITY strings."

```bash
python - << 'EOF'
from core.bmp_parser import BMPParser
from tests.fixtures.bgp_telemetry_generator import MockBGPTelemetryGenerator
gen = MockBGPTelemetryGenerator()
msg = gen.generate_update("192.168.0.0/24", 65100, as_path=[65100, 65200, 65300], next_hop="10.0.0.1")
parsed = BMPParser().parse_message(msg)
import json
print(json.dumps({
    "message_type": parsed.message_type,
    "peer_asn": parsed.peer_header.peer_asn,
    "prefixes": parsed.bgp_update.nlri_prefixes,
    "as_path": parsed.bgp_update.path_attributes.get("as_path"),
}, indent=2))
EOF
```

### Scene 3: Ingestion Pipeline (1 min)

```bash
# Register a BGP speaker
curl -s -X POST http://localhost:8001/api/telemetry/speakers \
  -H "Content-Type: application/json" \
  -d '{"hostname":"demo-router","router_id":"10.1.0.1","local_asn":65001,"bmp_listen_address":"10.1.0.1:179"}' | python3 -m json.tool

# Ingest 100 BMP messages
python - << 'EOF'
import httpx, time
from tests.fixtures.bgp_telemetry_generator import MockBGPTelemetryGenerator
gen = MockBGPTelemetryGenerator()
start = time.time()
for i in range(100):
    msg = gen.generate_update(f"10.{i//100}.{i%100}.0/24", 65001)
    httpx.post("http://localhost:8001/api/telemetry/bmp/ingest", content=msg)
elapsed = time.time() - start
print(f"100 messages in {elapsed:.2f}s = {100/elapsed:.0f} msg/sec")
EOF
```

> "100 messages in under a second. Each goes through: parse → RouteEvent record →
> InfluxDB write. Celery distributes across workers."

### Scene 4: ML Anomaly Detection (2 min)

```bash
# Show the detector code
cat core/detector.py | head -60
```

> "The detector runs two algorithms. Z-score: compute mean and std of flap_rate
> over the 7-day baseline. Any current window that's 3+ standard deviations above
> normal gets flagged. Isolation Forest: 5-feature multivariate model trained on
> 7 days of history. IsolationForest.predict() returns -1 for anomalies."

```bash
# Simulate a route flap storm (triggers anomaly)
python - << 'EOF'
import httpx
from tests.fixtures.bgp_telemetry_generator import MockBGPTelemetryGenerator
gen = MockBGPTelemetryGenerator()

# Register speaker
httpx.post("http://localhost:8001/api/telemetry/speakers", json={
    "hostname": "flap-router", "router_id": "10.2.0.1",
    "local_asn": 65002, "bmp_listen_address": "10.2.0.1:179"
})

# Simulate 30 rapid flaps
for msg in gen.simulate_route_flap("flap-router", "172.16.0.0/12", num_flaps=30):
    httpx.post("http://localhost:8001/api/telemetry/bmp/ingest", content=msg)

print("Flap simulation done — polling for anomalies...")
import time; time.sleep(35)

resp = httpx.get("http://localhost:8001/api/anomalies/", params={"time_range": "1h"})
for a in resp.json():
    print(f"  {a['severity']} {a['anomaly_type']} on {a.get('prefix')} — z_score: {a.get('details', {}).get('z_score')}")
EOF
```

### Scene 5: Dashboard (2 min)

Switch to Streamlit tab. Walk through each page:

**Route Timeline:**
> "Select the flap-router, fetch the last hour. The scatter chart shows UPDATE events
> at y=1 and WITHDRAW events at y=0, colored by neighbor IP. You can see the 30-event
> flap pattern clearly."

**Anomaly Timeline:**
> "The anomaly we just triggered is here — UNUSUAL_CHURN, WARNING severity,
> z_score of 4.2. Click to expand: current flap rate, baseline mean, the isolation
> forest score. Click Acknowledge to mark it as reviewed."

**Device Health:**
> "Each speaker shows: connection status, routes advertised in 24h, current flap rate,
> and the time-series flap rate chart."

### Scene 6: Observability (1 min)

Switch to Grafana tab.
> "Prometheus scrapes the /metrics endpoint every 15 seconds. The Grafana dashboard
> shows: HTTP request rate, p99 latency, BMP ingestion rate, anomalies by severity,
> alert delivery success rate. I defined custom Prometheus counters for every
> meaningful event in the pipeline."

---

## Q&A Prep

**"Why not just use an existing tool like Grafana Loki or OpenTelemetry?"**
> "Existing APM tools work great for infrastructure monitoring, but BGP anomaly
> detection requires domain knowledge: BMP protocol parsing, AS path analysis,
> baseline computation specific to routing behavior. I built the protocol layer
> from scratch to have full control over the feature engineering for the ML model."

**"What would you do differently?"**
> "Three things: (1) Replace Prophet for forecasting with a simpler ARIMA model —
> Prophet has a heavy Pystan dependency that's painful in containers. (2) Add
> ClickHouse as an OLAP layer for historical queries over months of data —
> PostgreSQL partitioning works but ClickHouse columnar storage is 10-100x faster
> for aggregation queries. (3) Use Kafka instead of Celery for ingestion at true
> production scale — Kafka's consumer group semantics handle backpressure better
> than Redis queues."

**"How do you know the ML model is accurate?"**
> "I don't have labeled BGP anomaly data, so I can't compute precision/recall
> in the traditional sense. Instead I measure: (1) alert fatigue — are operators
> acknowledging or ignoring alerts? (2) false negative rate — did any real outages
> not get detected? (3) I can tune the IsolationForest contamination parameter
> per-deployment based on observed false positive rate. In a real production
> deployment I'd build a feedback loop where operator acknowledgements train
> a supervised model over time."
