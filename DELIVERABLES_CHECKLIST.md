# RouteMonitor — Complete Deliverables Checklist

Paste this into Cursor and ask it to verify each item. Items marked with a verification
command can be checked automatically. Items marked [MANUAL] require human review.

---

## PHASE 1 — Core Infrastructure

### Database Models (`api/models.py`)
- [ ] `BGPSpeaker` model — fields: id (UUID PK), hostname, router_id, local_asn, bmp_listen_address, status, created_at, last_seen
- [ ] `RouteEvent` model — fields: id, speaker_id (FK→BGPSpeaker), timestamp, event_type (UPDATE/WITHDRAW/STATE_CHANGE), prefix, withdrawn_prefixes (ARRAY), path_attributes (JSONB), neighbor_ip, neighbor_asn, sequence_number
- [ ] `Anomaly` model — fields: id, speaker_id (FK), anomaly_type, severity (INFO/WARNING/CRITICAL), prefix, neighbor_ip, detected_at, resolved_at, acknowledged_at, acknowledged_by, details (JSONB)
- [ ] `Alert` model — fields: id, anomaly_id (FK), alert_type, target_url, payload (JSONB), status (PENDING/DELIVERED/FAILED), sent_at, delivery_status, retry_count, error_message
- [ ] `WebhookSubscription` model — fields: id, target_url, severity_min, event_types (ARRAY), is_active, created_at, headers (JSONB)
- [ ] All models have `__tablename__`, correct relationships, and `__repr__`

### Pydantic Schemas (`api/schemas.py`)
- [ ] `BGPSpeakerCreate`, `BGPSpeakerResponse`, `BGPSpeakerStatus`
- [ ] `RouteEventResponse`, `RouteEventFilter`
- [ ] `AnomalyResponse`, `AnomalyAcknowledgeRequest`
- [ ] `AlertResponse`, `WebhookSubscriptionCreate`, `WebhookSubscriptionResponse`
- [ ] All schemas use Pydantic v2 (`model_config = ConfigDict(from_attributes=True)`)

### Database Setup (`api/database.py`)
- [ ] SQLAlchemy 2.0 engine + `SessionLocal` factory
- [ ] `get_db()` dependency (yields session, closes on exit)
- [ ] `DATABASE_URL` from `core/config.py`

### Configuration (`core/config.py`)
- [ ] `Settings` class with all env vars: DATABASE_URL, REDIS_URL, INFLUXDB_URL/TOKEN/ORG/BUCKET, SECRET_KEY, CELERY_BROKER_URL/RESULT_BACKEND, ANOMALY_Z_SCORE_THRESHOLD, ANOMALY_BASELINE_DAYS, ANOMALY_DEDUP_WINDOW_SECONDS
- [ ] Singleton `settings` instance

### Alembic Migrations
- [ ] `alembic/versions/001_initial_schema.py` — creates all 5 tables (bgp_speakers, route_events, anomalies, alerts, webhook_subscriptions)
- [ ] `alembic/versions/002_add_webhook_subscriptions.py` — adds webhook_subscriptions table (or merged into 001)
- [ ] `alembic upgrade head` runs cleanly with no errors

**Verify:**
```bash
docker compose exec api alembic upgrade head
docker compose exec db psql -U routemonitor -c "\dt"
# → Should list: bgp_speakers, route_events, anomalies, alerts, webhook_subscriptions, alembic_version
```

---

## PHASE 1 — BMP Parser

### `core/bmp_parser.py`
- [ ] `BMPParser.parse_message(data: bytes)` — parses BMP common header (version, length, msg_type)
- [ ] Handles msg_type 0 (Route Monitoring), 1 (Statistics Report), 3 (Peer Down), 4 (Peer Up), 6 (Initiation)
- [ ] `_parse_peer_header(data, offset)` — extracts peer_type, peer_flags, peer_asn, peer_address, timestamp
- [ ] `_parse_bgp_update(data, offset)` — extracts withdrawn_prefixes (list), path_attributes (dict), nlri_prefixes (list)
- [ ] `_parse_path_attributes(data)` — parses AS_PATH, NEXT_HOP, ORIGIN, MED, LOCAL_PREF, COMMUNITIES
- [ ] `_parse_prefix_list(data, offset, length)` — parses NLRI prefix list with correct bit-to-byte rounding
- [ ] `parsed_message_to_dict(parsed)` — converts ParsedBMPMessage to JSON-serializable dict
- [ ] Returns structured dict: `{message_type, peer_header: {peer_asn, peer_address}, bgp_update: {nlri_prefixes, withdrawn_prefixes, path_attributes}}`

**Verify:**
```bash
TESTING=1 pytest tests/unit/test_bmp_parser.py -v
# → All tests pass, including UPDATE, WITHDRAW, and malformed message tests
```

---

## PHASE 1 — BMP TCP Server

### `api/bmp_server.py`
- [ ] `BMPServer` class with `start(host, port)` and `stop()` methods
- [ ] `BMPConnectionHandler.handle(reader, writer)` — reads BMP stream, extracts complete messages by length field, dispatches `parse_bmp_message_task.delay(hex_data)`
- [ ] Handles partial reads (reads exactly `message_length` bytes)
- [ ] Handles client disconnect gracefully (EOFError, ConnectionResetError)
- [ ] Logs every connection with `structlog`
- [ ] `start_bmp_server()` called from `api/main.py` lifespan

**Verify:**
```bash
TESTING=1 pytest tests/unit/test_bmp_server.py -v
```

---

## PHASE 1 — FastAPI Application

### `api/main.py`
- [ ] FastAPI app with lifespan (starts/stops BMP server on startup/shutdown)
- [ ] Includes all routers: telemetry, anomalies, alerts, metrics, health
- [ ] Includes `auth_router`
- [ ] Adds middlewares: `RequestIDMiddleware`, `RateLimitMiddleware`, `CORSMiddleware`, `TrustedHostMiddleware`
- [ ] `/metrics` endpoint returns Prometheus text format
- [ ] `GET /api/health` returns `{"status":"healthy","version":"0.1.0","services":{...}}`

**Verify:**
```bash
curl http://localhost:8001/api/health
# → {"status":"healthy","version":"0.1.0","services":{"db":"ok","redis":"ok","influxdb":"ok"}}
curl http://localhost:8001/docs
# → 200 (Swagger UI loads)
```

---

## PHASE 1 — Telemetry API (`api/routes/telemetry.py`)

- [ ] `POST /api/telemetry/speakers` — create BGPSpeaker, returns 201
- [ ] `GET /api/telemetry/speakers` — list all speakers
- [ ] `GET /api/telemetry/speakers/{id}` — get one speaker (404 if not found)
- [ ] `GET /api/telemetry/speakers/{id}/status` — returns live status dict with `last_event_time`, `event_count_1h`, `flap_count_1h`
- [ ] `POST /api/telemetry/bmp/ingest` — accepts raw BMP bytes, calls `parse_bmp_message_task.delay()`, returns 202
- [ ] `GET /api/telemetry/route-events` — list route events with filters: speaker_id, prefix, event_type, limit (default 100)
- [ ] `GET /api/telemetry/metrics/route-stats/{speaker_id}` — returns time-series flap/route counts from InfluxDB

**Verify:**
```bash
TESTING=1 pytest tests/integration/test_telemetry_api.py -v
```

---

## PHASE 1 — Infrastructure Files

### Docker
- [ ] `Dockerfile` — multi-stage build, non-root user, uvicorn entrypoint
- [ ] `docker-compose.yml` — 8 services: api, celery-worker, celery-beat, db (postgres), redis, influxdb, prometheus, grafana
- [ ] All services have health checks
- [ ] Port mapping: api→8001, db→5433, redis→6380, influxdb→8086, grafana→3000, prometheus→9090

**Verify:**
```bash
docker compose up -d
docker compose ps
# → All 8 services should be "healthy" or "running"
```

### Dependencies
- [ ] `requirements.txt` — includes: fastapi, uvicorn, sqlalchemy, alembic, psycopg2-binary, influxdb-client, celery[redis], redis, httpx, pydantic-settings, structlog, prometheus-client, python-jose[cryptography], passlib[bcrypt], numpy, scikit-learn, streamlit, plotly, pandas
- [ ] `requirements-dev.txt` — includes: pytest, pytest-asyncio, pytest-cov, httpx, locust, black, ruff, mypy

---

## PHASE 2 — InfluxDB Connector

### `core/influxdb_connector.py`
- [ ] `InfluxDBConnector.__init__(url, token, org, bucket)` — initializes write_api and query_api
- [ ] `write_metrics_batch(points: list[dict])` — writes list of `{measurement, tags, fields}` dicts as InfluxDB Points
- [ ] `query_route_stats(speaker_id, time_range)` → `list[dict]` — Flux query returning flap_count, route_count, path_diversity, convergence_ms, as_path_length per time window
- [ ] `query_correlation_matrix(time_range, top_n_prefixes)` → `dict` — returns `{prefix_a: {prefix_b: pearson_r}}` dict
- [ ] `close()` — closes client connections
- [ ] Handles connection errors gracefully (returns empty list, not exception)

**Verify:**
```bash
TESTING=1 pytest tests/unit/test_influxdb_connector.py -v
```

---

## PHASE 2 — Celery Setup

### `tasks/celery_app.py`
- [ ] Celery app configured with Redis broker and result backend
- [ ] Beat schedule: `compute-aggregates` every 5 min, `detect-anomalies-all` every 5 min
- [ ] `task_serializer = "json"`, `accept_content = ["json"]`

### `tasks/ingestion.py` — All 5 tasks implemented (not stubs)

- [ ] `parse_bmp_message_task(message_bytes_hex)` — decodes hex→bytes, calls `BMPParser().parse_message()`, increments `BMP_MESSAGES_INGESTED` counter, chains to `ingest_metrics_task`
- [ ] `ingest_metrics_task(parsed_message, speaker_id)` — creates `RouteEvent` rows for each NLRI prefix and withdrawn prefix, writes to InfluxDB, chains to `detect_anomalies_task`
- [ ] `compute_aggregates_task()` — Flux query for 5-min rollups, writes aggregated points back to InfluxDB
- [ ] `detect_anomalies_task(speaker_id)` — calls `asyncio.run(AnomalyDetector().detect_anomalies(...))`, increments `ANOMALIES_DETECTED` counter per anomaly
- [ ] `dispatch_alerts_task(anomaly_id)` — fetches Anomaly from DB, calls `asyncio.run(AlertDispatcher().dispatch(...))`, increments `ALERTS_DISPATCHED` counter

**Verify:**
```bash
TESTING=1 pytest tests/unit/test_ingestion_tasks.py -v
```

---

## PHASE 3 — Anomaly Detection

### `core/detector.py` — All 6 methods fully implemented

- [ ] `detect_anomalies(speaker_id, influx, db)` — full pipeline: query historical→baseline→z-score→ML→correlated→deduplicate→persist→dispatch
- [ ] `_compute_baseline(metrics)` — returns dict with mean_flap_rate, std_flap_rate, p95_flap_rate, mean_route_count, std_route_count, mean_path_diversity, std_path_diversity using numpy
- [ ] `_detect_z_score_anomalies(current, baseline)` — computes `z = (current_flap - mean) / std`, returns anomaly if `z > threshold`
- [ ] `_detect_ml_anomalies(historical, current)` — IsolationForest with 5 features (flap_count, route_count, path_diversity, convergence_ms, as_path_length), guards `if len(historical) < 10: return []`
- [ ] `_find_correlated_failures(speaker_id, timestamp, window_seconds, db)` — queries WITHDRAW events in ±60s window, returns CORRELATED_FAILURE anomaly if ≥5 simultaneous withdrawals
- [ ] `_deduplicate(anomalies, existing)` — deduplicates by `(anomaly_type, prefix)` within 300s window
- [ ] `_compute_severity(z_score)` — returns "INFO" if < 3.0, "WARNING" if 3.0–4.9, "CRITICAL" if ≥ 5.0

**Verify:**
```bash
TESTING=1 pytest tests/unit/test_anomaly_detector.py -v
# Key assertions:
# AnomalyDetector._compute_severity(2.9) == "INFO"
# AnomalyDetector._compute_severity(3.0) == "WARNING"
# AnomalyDetector._compute_severity(5.0) == "CRITICAL"
```

---

## PHASE 3 — Alert Dispatcher

### `core/dispatcher.py` — All methods fully implemented

- [ ] `AlertDispatcher.__init__(db, http_client)` — stores db session and httpx.AsyncClient
- [ ] `dispatch(anomaly_dict)` → `list[dict]` — queries active WebhookSubscriptions matching severity, calls `_send_webhook` for each
- [ ] `_send_webhook(subscription, payload)` — POST to target_url with JSON payload, creates Alert record
- [ ] `_should_notify(subscription, anomaly)` — checks severity_min threshold and event_types filter
- [ ] `_build_payload(anomaly)` — returns standardized dict with `{"event": "anomaly.detected", "data": {...}}`
- [ ] Retry logic: exponential backoff 2s→4s→8s, max 3 attempts
- [ ] Alert deduplication: skip if DELIVERED Alert for same anomaly_id exists within 5 min
- [ ] Updates `Alert.status` to DELIVERED or FAILED, sets `Alert.sent_at`

**Verify:**
```bash
TESTING=1 pytest tests/unit/test_dispatcher.py -v
```

---

## PHASE 3 — Anomaly & Alert API Endpoints

### `api/routes/anomalies.py`
- [ ] `GET /api/anomalies/` — list anomalies, filters: time_range (1h/24h/7d), severity, anomaly_type, acknowledged (bool), speaker_id, limit
- [ ] `GET /api/anomalies/{id}` — get one anomaly (404 if not found)
- [ ] `POST /api/anomalies/{id}/acknowledge` — sets acknowledged_at, acknowledged_by; requires operator role
- [ ] `POST /api/anomalies/{id}/resolve` — sets resolved_at; requires operator role

### `api/routes/alerts.py`
- [ ] `GET /api/alerts/` — list alerts with filters: status, anomaly_id, limit
- [ ] `GET /api/alerts/{id}` — get one alert
- [ ] `POST /api/alerts/{id}/retry` — re-dispatches failed alert; requires operator role
- [ ] `POST /api/alerts/webhooks` — create WebhookSubscription; requires admin role
- [ ] `GET /api/alerts/webhooks` — list subscriptions
- [ ] `DELETE /api/alerts/webhooks/{id}` — deactivate subscription; requires admin role

**Verify:**
```bash
TESTING=1 pytest tests/integration/test_anomaly_api.py -v
```

---

## PHASE 4 — Dashboard API Backend

### `api/routes/metrics.py`
- [ ] `GET /api/metrics/speaker/{speaker_id}` — returns `{speaker_id, time_range, total_prefixes, total_flaps, avg_convergence_ms, uptime_pct, anomaly_count}` from SQLAlchemy queries
- [ ] `GET /api/metrics/correlation` — returns `{"matrix": {...}}` from InfluxDB `query_correlation_matrix()`

**Verify:**
```bash
TESTING=1 pytest tests/integration/test_metrics_api.py -v
```

---

## PHASE 4 — Streamlit Dashboard

### `dashboard/utils/api_client.py`
- [ ] `RouteMonitorClient` base URL = `http://localhost:8001`
- [ ] All 10 methods implemented (not raising NotImplementedError):
  - `list_speakers()` → GET /api/telemetry/speakers
  - `get_speaker(id)` → GET /api/telemetry/speakers/{id}
  - `get_speaker_status(id)` → GET /api/telemetry/speakers/{id}/status
  - `get_speaker_metrics(id, time_range)` → GET /api/metrics/speaker/{id}
  - `get_route_events(speaker_id, prefix, event_type, limit)` → GET /api/telemetry/route-events
  - `get_route_stats(id, time_range, prefix)` → GET /api/telemetry/metrics/route-stats/{id}
  - `list_anomalies(time_range, speaker_id, severity, anomaly_type, acknowledged, limit)` → GET /api/anomalies/
  - `acknowledge_anomaly(id, acknowledged_by)` → POST /api/anomalies/{id}/acknowledge
  - `get_correlation(time_range)` → GET /api/metrics/correlation
  - `health_check()` → GET /api/health

**Verify:**
```bash
TESTING=1 pytest tests/unit/test_api_client.py -v
```

### `dashboard/pages/device_health.py`
- [ ] `render()` function calls `list_speakers()` and `get_speaker_status()`
- [ ] Status icons: CONNECTED=🟢, DEGRADED=🟡, DISCONNECTED=🔴
- [ ] 4 KPI metric cards (total speakers, connected, degraded, disconnected)
- [ ] Per-speaker `st.expander()` with Plotly line chart (`px.line(df, x="time", y="flap_count")`)
- [ ] Auto-refresh checkbox: `time.sleep(30); st.rerun()`

### `dashboard/pages/route_timeline.py`
- [ ] Plotly scatter chart: event_type mapped to numeric Y (UPDATE=1, WITHDRAW=0, STATE_CHANGE=0.5)
- [ ] Color by `neighbor_ip`, symbol by `event_type`
- [ ] 1-minute resampled withdrawal rate bar chart: `pd.resample("1min")`
- [ ] Sidebar filters: speaker, prefix text input, event type multiselect

### `dashboard/pages/anomaly_timeline.py`
- [ ] Severity icons: CRITICAL=🔴, WARNING=🟡, INFO=🔵
- [ ] 4 KPI cards: total, critical, warning, unacknowledged
- [ ] Hourly bar chart: `df.set_index("detected_at").resample("1h").size()`
- [ ] Per-anomaly `st.expander()` with z_score/IF_score details
- [ ] Acknowledge button → `client.acknowledge_anomaly()` → `st.rerun()`

### `dashboard/pages/correlation_matrix.py`
- [ ] `px.imshow(df, color_continuous_scale="RdBu_r", zmin=-1, zmax=1)`
- [ ] Top-20 correlated pairs table sorted by `abs(correlation)`
- [ ] Risk label: "⚠️ Shared link?" if `abs(r) > 0.8`
- [ ] Graceful empty state: `st.warning("No correlation data yet...")` if matrix is empty

### `dashboard/app.py`
- [ ] Sidebar health indicator showing API status + per-service icons (✅/❌)
- [ ] Navigation to all 4 pages

**Verify:**
```bash
streamlit run dashboard/app.py
# → Opens at http://localhost:8501 without ImportError
# → Sidebar shows 🟢 or 🔴 API status
# → All 4 page links work
```

---

## PHASE 5 — Auth & Security

### `api/auth.py` — All fully implemented (no NotImplementedError)
- [ ] `create_access_token(username, role, expires_minutes)` — `jose.jwt.encode({sub, role, exp, iat}, SECRET_KEY, "HS256")`
- [ ] `decode_token(token)` — `jose.jwt.decode(...)`, raises HTTP 401 on JWTError
- [ ] `get_current_user(token)` — FastAPI dependency, returns `{username, role}`
- [ ] `require_role(minimum_role)` — factory returning dependency; ROLE_LEVELS = {readonly:0, operator:1, admin:2}; raises 403 if insufficient
- [ ] `_USERS` dict with admin/operator/readonly (hardcoded for demo)
- [ ] `POST /api/auth/token` — validates credentials, returns `{access_token, token_type: "bearer"}`
- [ ] `GET /api/auth/me` — returns current user info

**Verify:**
```bash
curl -X POST http://localhost:8001/api/auth/token -d "username=admin&password=admin123"
# → {"access_token": "eyJ...", "token_type": "bearer"}

TOKEN=$(curl -s -X POST http://localhost:8001/api/auth/token -d "username=admin&password=admin123" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
curl http://localhost:8001/api/auth/me -H "Authorization: Bearer $TOKEN"
# → {"username": "admin", "role": "admin"}
```

### `api/middleware.py`
- [ ] `RequestIDMiddleware` — adds `X-Request-ID` header, logs every request with structlog, records Prometheus counter
- [ ] `RateLimitMiddleware` — Redis sliding-window zset, per-IP per-path limits (BMP:1000/min, anomalies:100/min, default:300/min), returns 429 with `Retry-After: 60` header
- [ ] Rate limiter bypassed when `TESTING=1` env var set
- [ ] 6 Prometheus metrics defined: REQUEST_COUNT, REQUEST_LATENCY, BMP_MESSAGES_INGESTED, ANOMALIES_DETECTED, ALERTS_DISPATCHED, ACTIVE_BGP_SPEAKERS

**Verify:**
```bash
# Rate limiter fires at 301st request
for i in $(seq 1 310); do curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8001/api/anomalies/; done | sort | uniq -c
# → ~300x 200, ~10x 429

# Prometheus metrics populated
curl http://localhost:8001/metrics | grep "routemonitor_"
# → routemonitor_http_requests_total, routemonitor_bmp_messages_total, etc.
```

### RBAC applied to endpoints
- [ ] `POST /api/anomalies/{id}/acknowledge` — requires operator+
- [ ] `POST /api/anomalies/{id}/resolve` — requires operator+
- [ ] `POST /api/alerts/webhooks` — requires admin
- [ ] `POST /api/alerts/{id}/retry` — requires operator+
- [ ] `DELETE /api/alerts/webhooks/{id}` — requires admin

**Verify:**
```bash
# Unauthenticated request to protected endpoint returns 401
curl -X POST http://localhost:8001/api/alerts/webhooks -H "Content-Type: application/json" -d '{"target_url":"http://x.com"}'
# → 401

# Operator cannot access admin endpoint
OP_TOKEN=$(curl -s -X POST http://localhost:8001/api/auth/token -d "username=operator&password=operator123" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")
curl -X POST http://localhost:8001/api/alerts/webhooks -H "Authorization: Bearer $OP_TOKEN" -H "Content-Type: application/json" -d '{"target_url":"http://x.com"}'
# → 403
```

---

## PHASE 5 — Production Infrastructure

### `docker-compose.prod.yml`
- [ ] Uses `${IMAGE_TAG:-latest}` (no `:latest` hardcoded)
- [ ] No bind mounts (no `./:/app` volume)
- [ ] `uvicorn --workers 4 --no-access-log`
- [ ] `deploy.resources.limits` on every service (api: 1 CPU/1GB RAM, celery: 0.5 CPU/512MB, db: 1 CPU/2GB, etc.)
- [ ] Redis `maxmemory 512mb`, `maxmemory-policy allkeys-lru`
- [ ] Prometheus `--storage.tsdb.retention.time=30d`

### Kubernetes (`k8s/`)
- [ ] `k8s/namespace.yaml` — `routemonitor` namespace
- [ ] `k8s/configmap.yaml` — INFLUXDB_URL, INFLUXDB_ORG, INFLUXDB_BUCKET, BMP port, anomaly thresholds
- [ ] `k8s/secret.yaml` — DATABASE_URL, REDIS_URL, INFLUXDB_TOKEN, SECRET_KEY (base64 placeholders)
- [ ] `k8s/api-deployment.yaml` — Deployment (2 replicas), Service (ClusterIP, ports 80+9179), HPA (min=2 max=8, CPU 70% / memory 80%)
- [ ] `k8s/celery-deployment.yaml` — Worker Deployment (2 replicas) + Beat Deployment (1 replica, singleton)
- [ ] `k8s/ingress.yaml` — nginx Ingress with TLS (cert-manager annotation), rate-limit annotations, `/api`, `/docs`, `/metrics` paths

### Monitoring
- [ ] `monitoring/grafana/dashboards/routemonitor.json` — 9-panel Grafana dashboard (HTTP rate, p99 latency, BMP ingest rate, anomalies by severity, alert success gauge, rate-limit rejections, anomaly timeline, Celery task rate, PostgreSQL connections)
- [ ] `prometheus.yml` — scrape configs for api (/metrics), node_exporter, postgres_exporter

### CI/CD (`.github/workflows/`)
- [ ] `test.yml` — runs `pytest tests/unit/` with postgres+redis services
- [ ] `lint.yml` — runs black, ruff, mypy
- [ ] `deploy.yml` — build+push to GHCR with `docker/build-push-action` and `metadata-action` tags, integration-test job, deploy-staging (on push to main), deploy-production (on semver tag)

---

## PHASE 5 — Load Test

### `tests/load/locustfile.py`
- [ ] `BGPTelemetryUser` — wait_time=between(0.001, 0.01), tasks: ingest_bmp_update (weight 10), ingest_bmp_withdraw (3), list_route_events (5), list_anomalies (2), health_check (1)
- [ ] Pre-generates 100 BMP UPDATE + 50 WITHDRAW messages at module load
- [ ] `DashboardUser` — wait_time=between(2, 10), tasks: view_speakers (3), view_anomaly_timeline (5), view_route_stats (2), view_correlation (1)

**Verify:**
```bash
locust -f tests/load/locustfile.py --host=http://localhost:8001 \
       --users=50 --spawn-rate=5 --run-time=60s --headless --csv=tests/load/results
cat tests/load/results_stats.csv
# Pass criteria: p99 < 200ms for /bmp/ingest, error rate < 1%
```

---

## PHASE 6 — Portfolio Polish

### Documentation
- [ ] `README.md` — has all of: badges (tests/lint/codecov/python/MIT), ASCII architecture diagram, performance table with real measured numbers, tech stack table with "Why" column, quick-start commands, services table, API overview, project structure tree, 3 ADRs (BMP choice, IsolationForest, dual-DB)
- [ ] `PORTFOLIO.md` — 4 resume bullet variants, interview talking points for "complex system" / "trade-off" / "scale to 10x" / "how does ML work", system design BGP framework
- [ ] `DEMO_SCRIPT.md` — 3-min and 8-min demo walkthroughs with commands
- [ ] `BLOG_POST.md` — technical blog post with real performance numbers filled in
- [ ] `CONTRIBUTING.md` — dev setup, code style, branch naming, commit message format
- [ ] `.github/PULL_REQUEST_TEMPLATE.md` — PR checklist
- [ ] `ARCHITECTURE.md` — system architecture narrative

### End-to-End Verification (all must pass)
- [ ] `docker compose up -d && docker compose ps` → all 8 services healthy
- [ ] `alembic upgrade head` → no errors, all 5 tables exist
- [ ] `POST /api/telemetry/bmp/ingest` with real BMP bytes → 202
- [ ] Route events appear in `GET /api/telemetry/route-events`
- [ ] Flap simulation triggers anomaly detection → anomaly appears in `GET /api/anomalies/`
- [ ] `POST /api/auth/token` returns valid JWT
- [ ] Protected endpoints return 401 without token, 403 with insufficient role
- [ ] Rate limiter returns 429 after limit exceeded
- [ ] `GET /metrics` returns Prometheus counters with `routemonitor_` prefix
- [ ] Streamlit dashboard renders all 4 pages without error

### Test Coverage
- [ ] `TESTING=1 pytest tests/unit/ --cov=api --cov=core --cov=tasks` → **≥ 85% total coverage**
- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] Load test: p99 < 200ms at 50 users, error rate < 1%

### Screenshots / Assets [MANUAL]
- [ ] `docs/dashboard_screenshot.png` — screenshot of Streamlit dashboard (best-looking page)
- [ ] `docs/route_timeline.png` — route timeline with data
- [ ] `docs/device_health.png` — device health with speaker data
- [ ] `docs/anomaly_timeline.png` — anomaly timeline showing at least one anomaly
- [ ] `docs/correlation_matrix.png` — correlation matrix (can be empty with caption)
- [ ] README references `docs/dashboard_screenshot.png`

### GitHub [MANUAL]
- [ ] All `your-username` placeholders replaced with real GitHub username
- [ ] Repo description set: "Real-time BGP telemetry & ML anomaly detection platform"
- [ ] Topics set: bgp, networking, anomaly-detection, machine-learning, fastapi, streamlit, python, celery, influxdb, prometheus
- [ ] `CURSOR_PHASE*.md` files added to `.gitignore` (not pushed to public repo)
- [ ] `v1.0.0` tag created and pushed

---

## Quick All-in-One Verification Script

Run this to check the most critical items automatically:

```bash
cd routemonitor

echo "=== 1. Docker stack ==="
docker compose ps --format "table {{.Name}}\t{{.Status}}"

echo "=== 2. API health ==="
curl -sf http://localhost:8001/api/health | python3 -m json.tool

echo "=== 3. Auth ==="
curl -sf -X POST http://localhost:8001/api/auth/token -d "username=admin&password=admin123"

echo "=== 4. Unit tests ==="
TESTING=1 pytest tests/unit/ -q

echo "=== 5. Coverage ==="
TESTING=1 pytest tests/unit/ --cov=api --cov=core --cov=tasks --cov-report=term -q 2>&1 | tail -3

echo "=== 6. Prometheus metrics ==="
curl -sf http://localhost:8001/metrics | grep "^routemonitor_" | head -10

echo "=== 7. Rate limiter ==="
for i in $(seq 1 5); do curl -s -o /dev/null -w "%{http_code} " http://localhost:8001/api/anomalies/; done; echo ""

echo "=== 8. Database tables ==="
docker compose exec -T db psql -U routemonitor -c "\dt" 2>/dev/null | grep -E "bgp_speakers|route_events|anomalies|alerts|webhook"
```
