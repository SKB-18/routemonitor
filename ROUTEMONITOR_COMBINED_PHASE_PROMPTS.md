# RouteMonitor: COMPLETE COMBINED PHASE PROMPTS

**Real-Time BGP Telemetry & ML Anomaly Detection Platform**

---

## 📋 PROJECT OVERVIEW

### Problem (From Rohith's Hexagon Experience)
- 10K+ routers with BGP constantly changing
- No real-time visibility into anomalies
- Reactive troubleshooting only (after customer impact)
- Route flaps, link failures, convergence issues hard to detect
- Manual log analysis is too slow

### Solution: RouteMonitor
- **BMP telemetry collection** (RFC 7854) from all routers
- **Real-time metrics** in InfluxDB (time-series)
- **ML anomaly detection** (Z-score + Isolation Forest)
- **Intelligent alerting** (webhook/Slack)
- **Interactive dashboard** (Streamlit)
- **Correlation analysis** (detect link failures → prefix failures)

### Tech Stack
- **Backend:** FastAPI, Celery, Redis, PostgreSQL
- **Time-Series:** InfluxDB 2.0
- **ML/Data:** scikit-learn, numpy, scipy, Prophet
- **Frontend:** Streamlit
- **DevOps:** Docker, Kubernetes, Prometheus, Grafana
- **Testing:** pytest, containerlab, ExaBGP

### Resume Alignment
- **BGP/OSPF expertise** ✅ (BMP is BGP Monitoring Protocol)
- **Python automation** ✅ (FastAPI, Celery, scikit-learn)
- **Large-scale systems** ✅ (1M+ updates/min from 10K routers)
- **Real-time visibility** ✅ (What Hexagon needed)
- **Network protocols** ✅ (BMP RFC 7854 binary parsing)
- **ML engineering** ✅ (Anomaly detection algorithms)

---

## 🏗️ DETAILED ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────────┐
│                        ROUTERS (10K+)                           │
│            Sending BMP UPDATE messages continuously             │
└─────────────────────────────────────────┬───────────────────────┘
                                          │
                                      BMP/TCP
                                          │
                    ┌─────────────────────▼──────────────────────┐
                    │        BMP SERVER (Port 179)                │
                    │  - Accept TCP connections from routers      │
                    │  - Parse BMP binary messages (RFC 7854)     │
                    │  - Queue events to Celery                   │
                    └─────────────────────┬──────────────────────┘
                                          │
                       ┌──────────────────┼──────────────────┐
                       │                  │                  │
                    Celery              Celery            Celery
                    Queue               Queue             Queue
                       │                  │                  │
         ┌─────────────▼────┐  ┌────────▼──────────┐  ┌────▼──────────┐
         │  Parse BMP Task  │  │ Ingest Metrics    │  │ Detect        │
         │ (binary → JSON)  │  │ Task (write InfluxDB)  │ Anomalies Task│
         └─────────────┬────┘  └────────┬──────────┘  └────┬──────────┘
                       │                  │                  │
         ┌─────────────▼────┐  ┌────────▼──────────┐  ┌────▼──────────┐
         │   PostgreSQL     │  │    InfluxDB       │  │  Anomaly DB    │
         │  (RouteEvent)    │  │  (Metrics)        │  │  (PostgreSQL)  │
         │                  │  │  - flap_count     │  │  - Alerts      │
         │ Immutable event  │  │  - path_diversity │  │  - Severity    │
         │ log of all       │  │  - convergence    │  │  - Status      │
         │ route changes    │  │  - route_count    │  │                │
         └──────────────────┘  └───────────────────┘  └────┬──────────┘
                       │                  │                  │
                       └──────────────────┼──────────────────┘
                                          │
                    ┌─────────────────────▼──────────────────┐
                    │      Alerting Engine (Celery)          │
                    │ - Filter by severity                   │
                    │ - Deduplicate (5 min window)           │
                    │ - Send webhook/Slack                   │
                    │ - Retry with backoff                   │
                    └─────────────────────┬──────────────────┘
                                          │
                    ┌─────────────────────▼──────────────────┐
                    │    DASHBOARD (Streamlit)               │
                    │ - Route Timeline (all events)          │
                    │ - Device Health (BGP speakers)         │
                    │ - Anomaly Timeline (detected issues)   │
                    │ - Correlation Matrix (linked failures) │
                    │ - Real-time updates (WebSocket)        │
                    └────────────────────────────────────────┘
```

---

## 📊 DATA MODELS

### PostgreSQL

```python
class BGPSpeaker(Base):
    id: UUID
    hostname: str              # router1
    router_id: IPv4Address     # 10.0.0.1
    local_asn: int             # 65000
    bmp_listen_address: str    # 192.168.1.1:179
    status: str                # CONNECTED, DISCONNECTED
    last_seen: datetime
    created_at: datetime

class RouteEvent(Base):
    """Immutable log of route changes"""
    id: UUID
    speaker_id: UUID (FK)
    timestamp: datetime
    event_type: str            # UPDATE, WITHDRAW
    prefix: CIDR               # 10.0.0.0/24
    path_attributes: JSON      # {as_path, next_hop, med, local_pref}
    neighbor_ip: IPv4Address
    sequence_number: int       # For ordering
    created_at: datetime
    
    Indexes:
    - (speaker_id, timestamp)
    - (prefix, timestamp)
    - (neighbor_ip, timestamp)

class Anomaly(Base):
    id: UUID
    speaker_id: UUID (FK)
    prefix: CIDR (nullable)
    anomaly_type: str          # ROUTE_FLAP, CONVERGENCE_DELAY, PATH_DIVERGENCE
    severity: str              # INFO, WARNING, CRITICAL
    details: JSON              # Detailed info about anomaly
    detected_at: datetime
    acknowledged: bool
    resolved_at: datetime (nullable)
    created_at: datetime

class Alert(Base):
    id: UUID
    anomaly_id: UUID (FK)
    alert_type: str            # WEBHOOK, SLACK
    target_url: str
    delivery_status: str       # PENDING, SUCCESS, FAILED
    retry_count: int
    last_retry: datetime
    error_message: str (nullable)
    created_at: datetime
```

### InfluxDB (Time-Series)

```
Measurement: route_stats
Tags:
  - speaker_id (router_id)
  - prefix (CIDR)
  - neighbor_ip
  - event_type (UPDATE, WITHDRAW)

Fields:
  - route_count (int)              # Active routes from speaker
  - flap_count (int)               # Flaps in last 5 min
  - path_diversity (float)         # Unique AS paths to prefix
  - convergence_time_ms (float)    # Time to stable state
  - as_path_length (int)           # Length of AS path
  - next_hop_count (int)           # Number of next hops

Time Resolution: 1 second (per route change) + 5 min aggregates
Retention: 7 days raw, 90 days aggregated
```

---

## 🧠 ANOMALY DETECTION ALGORITHMS

### 1. Z-Score Baseline Detection
```
For each (speaker, prefix, neighbor):
  baseline = mean(flap_count, window=7 days)
  stddev = std(flap_count, window=7 days)
  
  if (current - baseline) / stddev > 3:
    ANOMALY: "Route flapping detected"
    severity: WARNING or CRITICAL (based on flap_count)
```

### 2. Isolation Forest (Multivariate)
```
Features (per speaker per 5-min window):
  - flap_count
  - route_count (delta)
  - path_diversity (delta)
  - neighbor churn (how many neighbors changed)
  - convergence time (how long to stable)

Training: 7 days historical data
Scoring: Current window vs learned anomalies
  if anomaly_score > threshold:
    ANOMALY: "Multivariate anomaly detected"
    severity: INFO or WARNING
```

### 3. Correlation Analysis
```
When multiple prefixes show anomalies simultaneously:
  - Check if same AS path affected
  - Check if same link (neighbor) affected
  - Check if same time window affected
  
  if correlation > 0.8:
    ANOMALY: "Link failure detected" (causes all affected prefixes)
    severity: CRITICAL
    affected: [prefix1, prefix2, prefix3, ...]
```

### 4. Convergence Detection
```
When UPDATE seen → Calculate time to convergence:
  convergence_time = time(last_UPDATE) - time(first_UPDATE)
  
  if convergence_time > 60 seconds:
    ANOMALY: "Slow convergence detected"
    severity: WARNING
```

---

# PHASE 1: FOUNDATION (Week 1)

## ARCHITECTURE FOR PHASE 1

**Phase 1 builds the data foundation:**
- BMP message structures (understanding RFC 7854)
- Database models (RouteEvent, BGPSpeaker, Anomaly)
- InfluxDB time-series setup
- API routes (stub)
- Docker setup (InfluxDB added)
- Test fixtures (mock BGP telemetry generator)

---

## STEP 1: Cowork Phase 1 - RouteMonitor Foundation Scaffold

```
I'm building RouteMonitor, a real-time BGP telemetry & ML anomaly detection platform.

Problem: At Hexagon, we managed 10K+ routers with BGP but had zero real-time visibility into anomalies.
Solution: BMP telemetry collection → real-time metrics → ML anomaly detection → alerts.

Duration: 6-8 weeks, 6 phases.

Now starting Phase 1: Foundation.

Please create the COMPLETE Phase 1 repository scaffold for RouteMonitor.

## DIRECTORY STRUCTURE & FILES

### 1. Root-Level Configuration Files
- setup.py (with all dependencies)
- requirements.txt (all packages pinned)
- requirements-dev.txt (pytest, black, flake8, mypy)
- .env.example (sample environment variables)
- .gitignore (Python + virtual env)
- pytest.ini (pytest configuration)
- README.md (project overview)
- ARCHITECTURE.md (ASCII diagrams of BMP flow)
- DEVELOPMENT.md (how to run locally)

### 2. Dockerfile
- Multi-stage build
- Exposes port 8000 (FastAPI)
- Can run as Celery worker
- Has BMP TCP server on port 179

### 3. docker-compose.yml
Services needed:
- api (FastAPI, port 8000)
- celery (Celery worker)
- db (PostgreSQL 15, port 5432)
- redis (Redis 7, port 6379)
- influxdb (InfluxDB 2.0, port 8086)
- prometheus (Prometheus, port 9090)
- grafana (Grafana, port 3000)
- bmp_simulator (ExaBGP mock, generates test BGP data)

All with health checks.

### 4. GitHub Actions CI/CD (.github/workflows/)
- test.yml: pytest + coverage
- lint.yml: black, flake8, mypy
- deploy.yml: (stub)

### 5. ORM Models (api/models.py)
SQLAlchemy models:
- BGPSpeaker (hostname, router_id, asn, bmp_listen_address, status)
- RouteEvent (speaker_id, timestamp, event_type, prefix, path_attributes, neighbor_ip, sequence_number)
  - Indexes: (speaker_id, timestamp), (prefix, timestamp)
- Anomaly (speaker_id, prefix, anomaly_type, severity, details, acknowledged, resolved_at)
- Alert (anomaly_id, alert_type, target_url, delivery_status, retry_count)

All with proper relationships, indexes, timestamps.

### 6. Pydantic Schemas (api/schemas.py)
- BGPSpeakerRequest, BGPSpeakerResponse
- RouteEventResponse, RouteEventQueryResponse
- AnomalyRequest, AnomalyResponse
- AlertRequest, AlertResponse
- TelemetryMetricsResponse

All with validators.

### 7. API Route Skeletons (api/routes/)
- bmp_speakers.py: GET/POST speakers
- route_events.py: Query route events (time range, prefix, neighbor)
- anomalies.py: Query anomalies, acknowledge, resolve
- alerts.py: Manage alert subscriptions
- metrics.py: Query InfluxDB metrics

Each route with docstrings, [CURSOR TO IMPLEMENT] markers.

### 8. Core Modules (Skeletons with docstrings)
- core/bmp_parser.py: BMPParser class (binary parsing, RFC 7854)
- core/anomaly_detector.py: AnomalyDetector class (Z-score, Isolation Forest, correlation)
- core/alert_dispatcher.py: AlertDispatcher class (send alerts, retry logic)
- core/influxdb_connector.py: InfluxDBConnector class (write/query metrics)
- core/config.py: Settings (load from .env)

### 9. Celery Setup
- tasks/celery_app.py: Celery initialization with Redis
- tasks/ingestion.py: Celery tasks
  - parse_bmp_message_task()
  - ingest_metrics_task()
  - detect_anomalies_task()
  - send_alerts_task()

### 10. FastAPI App (api/main.py)
- FastAPI app with title, description
- CORS middleware
- Error handlers
- Include all routers
- Health check: GET /health
- Swagger UI: GET /docs

### 11. Dependencies (api/dependencies.py)
- get_db(): SQLAlchemy session
- get_current_user(): Auth stub
- get_logger(): Logging

### 12. Database Setup (api/database.py)
- SQLAlchemy engine (PostgreSQL)
- SessionLocal factory

### 13. Test Infrastructure (tests/)
conftest.py with fixtures:
- test_db_engine (in-memory SQLite)
- db_session (transactional)
- client (FastAPI TestClient)
- mock_bmp_speaker (creates test speaker)
- mock_route_update (creates test route event)
- mock_anomaly (creates test anomaly)
- mock_bgp_telemetry_generator (generates fake BGP data)

Test files:
- tests/unit/test_schemas.py (empty)
- tests/unit/test_bmp_parser.py (empty)
- tests/unit/test_anomaly_detector.py (empty)
- tests/integration/test_telemetry_api.py (empty)
- tests/integration/test_anomaly_api.py (empty)

### 14. BMP Message Fixtures (tests/fixtures/)
- bmp_messages.py: Sample BMP binary messages (RFC 7854 compliant)
- bgp_telemetry_generator.py: Mock BGP telemetry generator (ExaBGP simulator)
- sample_route_events.json: Test route event data

### 15. Dashboard Skeleton (dashboard/)
- app.py: Streamlit entry point
- pages/route_timeline.py: Timeline of route changes
- pages/device_health.py: BGP speaker health
- pages/anomaly_timeline.py: Anomaly history
- pages/correlation_matrix.py: Link failure correlation
- utils/api_client.py: API client
- utils/formatting.py: Formatting helpers

### 16. InfluxDB Setup
- docker-compose includes InfluxDB 2.0
- Initial bucket: "bgp_metrics"
- Retention: 7 days raw, 90 days aggregated
- Access token configured

### 17. Prometheus Setup
- prometheus.yml: Scrape configs for API, Celery, system
- Configured to scrape app metrics

## DELIVERABLES

After creating all of this, please:

1. Complete, ready-to-run project structure
2. Verify all imports are correct (no circular imports)
3. Verify docker-compose.yml parses correctly
4. List all files created
5. Provide setup guide for local testing

## LOCAL TESTING CHECKLIST (YOU WILL RUN AFTER RECEIVING OUTPUT)

After I receive this:

1. Run: docker compose build
2. Run: docker compose up
3. Verify all services healthy:
   - curl http://localhost:8000/health (FastAPI)
   - curl http://localhost:8000/docs (Swagger)
   - curl http://localhost:8086/health (InfluxDB)
   - psql postgres://localhost/routemonitor -c "\dt" (PostgreSQL)
   - redis-cli -p 6379 ping (Redis)
4. Run: pytest tests/ (should pass)
5. Verify imports: python -c "import api; from api.models import *"
6. If all pass: git init && git add . && git commit && git push

## IMPORTANT NOTES

- Phase 1 is foundation only (stubs for Cursor)
- All ORM models, schemas, docker-compose should be fully implemented
- All routes should have proper FastAPI structure
- Core modules can be skeletons (Cursor implements)
- BMP message structures need RFC 7854 comments
- InfluxDB setup must be correct (2.0 syntax)
- Everything must work locally with docker compose up before GitHub push
```

---

## STEP 2: Local Testing After Cowork

```bash
# Build and start services
docker build -t routemonitor .
docker compose up

# Wait for all services to show "healthy"
# (Check docker compose output, should see 8 services with health checks)

# Test 1: FastAPI health
curl http://localhost:8000/health
# Expected: {"status": "healthy"}

# Test 2: Swagger UI
curl http://localhost:8000/docs
# Expected: HTML (Swagger UI)

# Test 3: InfluxDB health
curl http://localhost:8086/health
# Expected: HTTP 200

# Test 4: PostgreSQL tables
docker compose exec db psql -U postgres -d routemonitor -c "\dt"
# Expected: Empty (migrations not run yet)

# Test 5: Redis
docker compose exec redis redis-cli ping
# Expected: PONG

# Test 6: Python imports
docker compose exec api python -c "
import api
from api.models import BGPSpeaker, RouteEvent, Anomaly, Alert
from api.schemas import BGPSpeakerRequest, RouteEventResponse
from core.bmp_parser import BMPParser
print('All imports successful!')
"
# Expected: All imports successful!

# Test 7: Pytest finds tests
docker compose exec api pytest --collect-only
# Expected: Lists all test files

# If all pass:
git add -A
git commit -m "Phase 1: RouteMonitor foundation scaffold"
git push
```

If any test fails, fix locally before pushing. ✅

---

## STEP 3: Cursor Phase 1 - RouteMonitor Foundation Implementation

```
I received Phase 1 scaffold from Cowork. Now implementing Phase 1 locally.

I have:
- Full repository structure
- ORM model stubs
- Pydantic schema stubs
- API route stubs
- Celery setup stubs
- docker-compose.yml with InfluxDB
- Test fixtures

## WHAT I NEED TO IMPLEMENT

### 1. Implement All SQLAlchemy ORM Models (api/models.py)

Complete implementations:
- BGPSpeaker: All fields, relationships, indexes
- RouteEvent: Immutable event log with proper indexes
- Anomaly: Anomaly tracking
- Alert: Alert delivery tracking

**Key implementation details:**
- RouteEvent.prefix should be CIDR type (validate with ipaddress.IPv4Network)
- RouteEvent.path_attributes is JSON (stores AS path, next hop, etc)
- Indexes on (speaker_id, timestamp), (prefix, timestamp) for query performance
- BGPSpeaker.status should be enum (CONNECTED, DISCONNECTED, IDLE)
- Anomaly.severity should be enum (INFO, WARNING, CRITICAL)

**Testing after implementation:**
```bash
docker compose up
docker compose exec api python -c "
from api.models import BGPSpeaker, RouteEvent, Anomaly, Alert
from sqlalchemy import inspect

# Verify all columns exist
mapper = inspect(RouteEvent)
print('RouteEvent columns:', [c.name for c in mapper.columns])
# Should include: id, speaker_id, timestamp, event_type, prefix, path_attributes, neighbor_ip

# Verify indexes
print('RouteEvent indexes:', mapper.indexes)
# Should have indexes on (speaker_id, timestamp) and (prefix, timestamp)
"
```

### 2. Implement Pydantic Schemas (api/schemas.py)

Complete implementations with validators:
- BGPSpeakerRequest: Validate IPv4Address for router_id, bmp_listen_address
- RouteEventResponse: Serialize RouteEvent, format timestamp, validate prefix is CIDR
- AnomalyResponse: Include all anomaly details
- All with proper validators

**Testing:**
```bash
docker compose exec api pytest tests/unit/test_schemas.py -v
# Should pass all schema validation tests
```

### 3. Implement InfluxDB Setup (core/influxdb_connector.py)

Create InfluxDBConnector class:
```python
class InfluxDBConnector:
    def __init__(self, url: str, token: str, org: str, bucket: str):
        # Initialize InfluxDB 2.0 client
        pass
    
    def write_metric(self, point: dict):
        # Write point to InfluxDB
        # point format: {measurement, tags, fields, time}
        pass
    
    def query_metrics(self, query: str) -> List[dict]:
        # Execute Flux query
        # Return results as list of dicts
        pass
    
    def query_route_stats(
        self,
        speaker_id: str,
        prefix: str,
        time_range: str  # "1h", "24h", "7d"
    ) -> dict:
        # Query route statistics for (speaker, prefix)
        # Return: {flap_count, path_diversity, convergence_time, etc}
        pass
```

**Testing:**
```bash
docker compose exec api python -c "
from core.influxdb_connector import InfluxDBConnector
import os

connector = InfluxDBConnector(
    url=os.getenv('INFLUXDB_URL', 'http://influxdb:8086'),
    token=os.getenv('INFLUXDB_TOKEN'),
    org=os.getenv('INFLUXDB_ORG'),
    bucket=os.getenv('INFLUXDB_BUCKET')
)

# Write test metric
connector.write_metric({
    'measurement': 'route_stats',
    'tags': {'speaker_id': 'router1', 'prefix': '10.0.0.0/24'},
    'fields': {'flap_count': 5, 'route_count': 1000},
    'time': None  # Use current time
})

print('InfluxDB write successful!')
"
```

### 4. Implement FastAPI App (api/main.py)

Complete implementation with all routers, middleware, error handlers.

**Testing:**
```bash
curl http://localhost:8000/health
curl http://localhost:8000/docs
```

### 5. Implement BMP Parser Skeleton (core/bmp_parser.py)

Create BMPParser class with method signatures and docstrings:
```python
class BMPParser:
    \"\"\"Parse BMP (BGP Monitoring Protocol) binary messages (RFC 7854).\"\"\"
    
    def parse_message(self, data: bytes) -> dict:
        \"\"\"Parse complete BMP message.\"\"\"
        # 1. Parse common header (4 bytes version + 2 bytes message length)
        # 2. Route to appropriate parser based on message type
        # Return: {message_type, timestamp, peer_header, message_body}
        pass
    
    def _parse_per_peer_header(self, data: bytes) -> dict:
        \"\"\"Parse BMP per-peer header (RFC 7854 section 4.2).\"\"\"
        # Extract: peer_type, peer_flags, peer_distinguisher, peer_address, peer_asn, timestamp
        pass
    
    def _parse_route_monitoring(self, data: bytes) -> dict:
        \"\"\"Parse BMP route monitoring message (UPDATE/WITHDRAW).\"\"\"
        # Parse BGP UPDATE message embedded in BMP
        pass
    
    def _parse_path_attributes(self, data: bytes) -> dict:
        \"\"\"Parse BGP path attributes (AS_PATH, NEXT_HOP, MED, LOCAL_PREF).\"\"\"
        pass
    
    def _parse_nlri(self, data: bytes) -> List[str]:
        \"\"\"Parse NLRI (Network Layer Reachability Information) - prefixes.\"\"\"
        pass
```

Docstrings should reference RFC 7854 sections and include binary format notes.

**Testing:**
```bash
docker compose exec api pytest tests/unit/test_bmp_parser.py -v
# Should parse sample BMP messages correctly
```

### 6. Implement Mock BGP Telemetry Generator (tests/fixtures/bgp_telemetry_generator.py)

Create generator to simulate real BGP speakers sending telemetry:
```python
class MockBGPTelemetryGenerator:
    \"\"\"Generate realistic mock BGP telemetry for testing.\"\"\"
    
    def __init__(self, num_speakers: int = 5, prefixes_per_speaker: int = 1000):
        pass
    
    def generate_update(self) -> bytes:
        \"\"\"Generate a random BGP UPDATE message.\"\"\"
        # Return binary BMP message with UPDATE
        pass
    
    def generate_withdraw(self) -> bytes:
        \"\"\"Generate a random BGP WITHDRAW message.\"\"\"
        # Return binary BMP message with WITHDRAW
        pass
    
    def simulate_route_flap(self, speaker_id: str, prefix: str) -> List[bytes]:
        \"\"\"Simulate a route flap (multiple UPDATEs/WITHDRAWs).\"\"\"
        # Return list of BMP messages representing flap
        pass
    
    def simulate_link_failure(self, affected_prefixes: int = 100) -> List[bytes]:
        \"\"\"Simulate link failure (many prefixes withdrawn simultaneously).\"\"\"
        pass
```

**Testing:**
```bash
docker compose exec api python -c "
from tests.fixtures.bgp_telemetry_generator import MockBGPTelemetryGenerator

gen = MockBGPTelemetryGenerator()
msg = gen.generate_update()
assert isinstance(msg, bytes), 'Should return bytes'
assert len(msg) > 0, 'Message should not be empty'
print('BGP telemetry generator works!')
"
```

### 7. Run Alembic Migrations

```bash
docker compose exec api alembic init alembic
docker compose exec api alembic revision --autogenerate -m "Initial schema"
docker compose exec api alembic upgrade head
```

### 8. Verify All Imports

```bash
docker compose exec api python -c "
from api.models import BGPSpeaker, RouteEvent, Anomaly, Alert
from api.schemas import BGPSpeakerRequest, RouteEventResponse, AnomalyResponse
from api.database import engine, SessionLocal
from api.main import app
from core.bmp_parser import BMPParser
from core.influxdb_connector import InfluxDBConnector
from tests.fixtures.bgp_telemetry_generator import MockBGPTelemetryGenerator
print('All imports successful!')
"
```

### 9. Run Test Suite

```bash
docker compose exec api pytest tests/ -v
# Should pass all tests

docker compose exec api pytest tests/ --cov=api --cov=core
# Expected: 85%+ coverage
```

### 10. Verify Database

```bash
docker compose exec db psql -U postgres -d routemonitor -c "\dt"
# Should show: bgp_speakers, route_events, anomalies, alerts tables

# Insert test speaker
docker compose exec api python -c "
from api.models import BGPSpeaker
from api.database import SessionLocal
from ipaddress import IPv4Address

session = SessionLocal()
speaker = BGPSpeaker(
    hostname='router1',
    router_id=IPv4Address('10.0.0.1'),
    local_asn=65000,
    bmp_listen_address='192.168.1.1:179'
)
session.add(speaker)
session.commit()
print('Test speaker created!')
"
```

### 11. Verify InfluxDB

```bash
# Create bucket
docker compose exec influxdb influx bucket create -n bgp_metrics -o myorg -r 7d

# Write test metric
docker compose exec api python -c "
from core.influxdb_connector import InfluxDBConnector
import os

connector = InfluxDBConnector(
    url='http://influxdb:8086',
    token=os.getenv('INFLUXDB_TOKEN'),
    org='myorg',
    bucket='bgp_metrics'
)

connector.write_metric({
    'measurement': 'route_stats',
    'tags': {'speaker_id': 'router1'},
    'fields': {'flap_count': 1}
})

print('InfluxDB metric written!')
"
```

## LOCAL VERIFICATION CHECKLIST

1. ✅ docker compose up (all services healthy)
2. ✅ curl http://localhost:8000/health (200)
3. ✅ curl http://localhost:8000/docs (HTML)
4. ✅ pytest tests/ -v (all tests pass)
5. ✅ pytest tests/ --cov (85%+ coverage)
6. ✅ All models import: python -c "from api.models import *"
7. ✅ All schemas import: python -c "from api.schemas import *"
8. ✅ BMP parser works: pytest tests/unit/test_bmp_parser.py -v
9. ✅ InfluxDB write works: tested above
10. ✅ Database tables exist: psql shows all tables
11. ✅ Mock telemetry generator works: pytest tests/fixtures/test_bgp_telemetry_generator.py -v

After all pass:
- git add .
- git commit -m "Phase 1: RouteMonitor foundation implementation"
- git push
```

---

## STEP 4: Local Testing After Cursor

```bash
# Test 1: Run all tests
docker compose up
docker compose exec api pytest tests/ -v

# Expected output:
# tests/unit/test_schemas.py::test_bgp_speaker_schema PASSED
# tests/unit/test_bmp_parser.py::test_parse_valid_update PASSED
# tests/unit/test_bmp_parser.py::test_parse_withdraw PASSED
# ... (all tests PASSED)

# Test 2: Coverage
docker compose exec api pytest tests/ --cov=api --cov=core --cov-report=term-missing
# Expected: 85%+ coverage

# Test 3: API health
curl http://localhost:8000/health
# Expected: {"status": "healthy"}

# Test 4: Models
docker compose exec api python -c "
from api.models import BGPSpeaker, RouteEvent, Anomaly, Alert
from api.database import SessionLocal

session = SessionLocal()
# Create test speaker
from ipaddress import IPv4Address
speaker = BGPSpeaker(
    hostname='router1',
    router_id=IPv4Address('10.0.0.1'),
    local_asn=65000
)
session.add(speaker)
session.commit()

# Query back
result = session.query(BGPSpeaker).filter_by(hostname='router1').first()
assert result is not None
print('ORM models work!')
"

# Test 5: InfluxDB
docker compose exec api python -c "
from core.influxdb_connector import InfluxDBConnector
import os

try:
    connector = InfluxDBConnector(
        url='http://influxdb:8086',
        token=os.getenv('INFLUXDB_TOKEN'),
        org='myorg',
        bucket='bgp_metrics'
    )
    print('InfluxDB connection works!')
except Exception as e:
    print(f'InfluxDB error: {e}')
"

# Test 6: BMP Parser
docker compose exec api pytest tests/unit/test_bmp_parser.py -v
# Expected: All BMP parser tests pass

# Test 7: No import errors
docker compose exec api python -c "import api; import core"
# Expected: No errors

# Test 8: Celery tasks
docker compose exec api python -c "
from tasks.celery_app import app
from tasks.ingestion import parse_bmp_message_task
print('Celery tasks import successfully!')
"

# If all pass:
git add .
git commit -m "Phase 1: RouteMonitor foundation implementation complete"
git push
```

---

# PHASE 2: TELEMETRY INGESTION (Weeks 2-3)

## ARCHITECTURE FOR PHASE 2

**Phase 2 builds the telemetry pipeline:**
- Complete BMP parser (binary protocol)
- InfluxDB metrics ingestion
- Celery ingestion pipeline
- API endpoints for querying telemetry
- Streaming BMP server (TCP listener)

---

## STEP 1: Cowork Phase 2 - RouteMonitor Telemetry Scaffold

```
I'm continuing Phase 2 of RouteMonitor: Telemetry Ingestion.

I already have Phase 1. Now building the complete telemetry pipeline.

**IMPORTANT:** Everything must be testable locally with docker compose + pytest before GitHub.

Please create:

## 1. Enhanced core/bmp_parser.py

Complete BMPParser class with full binary parsing:

```python
class BMPParser:
    \"\"\"RFC 7854 compliant BMP message parser.\"\"\"
    
    VERSION = 3
    MSG_TYPE_ROUTE_MONITORING = 0
    MSG_TYPE_STATISTICS_REPORT = 1
    MSG_TYPE_PEER_DOWN = 2
    MSG_TYPE_PEER_UP = 3
    
    # Implement all methods with actual binary parsing logic:
    
    def parse_message(self, data: bytes) -> dict:
        # 1. Verify version = 3
        # 2. Extract message length (bytes 1-4)
        # 3. Extract message type (byte 5)
        # 4. Parse per-peer header (26 bytes minimum)
        # 5. Route to type-specific parser
        # Return: {type, timestamp, peer, message_body}
        pass
    
    def _parse_per_peer_header(self, data: bytes, offset: int = 0) -> Tuple[dict, int]:
        # Extract:
        # - Peer type (1 byte): Global Instance (0) or RD Instance (1)
        # - Peer flags (1 byte): V (IPv6), L (adj-rib-in), A (adj-rib-out), O (post-policy)
        # - Peer distinguisher (8 bytes): Route distinguisher if RD instance
        # - Peer address (4 or 16 bytes): IPv4 or IPv6
        # - Peer AS (4 bytes)
        # - BGP ID (4 bytes)
        # - Timestamp (4 bytes seconds + 4 bytes microseconds)
        pass
    
    def _parse_route_monitoring(self, data: bytes, offset: int = 0) -> dict:
        # Contains BGP UPDATE message
        # Extract BGP UPDATE and parse it
        # Return: {updates: [...], withdraws: [...]}
        pass
    
    def _parse_bgp_update(self, data: bytes, offset: int = 0) -> dict:
        # BGP UPDATE format:
        # - Withdrawn Routes Length (2 bytes)
        # - Withdrawn Routes (variable)
        # - Total Path Attribute Length (2 bytes)
        # - Path Attributes (variable)
        # - NLRI (variable)
        pass
    
    def _parse_path_attributes(self, data: bytes, offset: int = 0) -> Tuple[dict, int]:
        # Path attributes include:
        # - AS_PATH (type 2): Sequence of ASNs
        # - NEXT_HOP (type 3): Next hop IP
        # - MULTI_EXIT_DISC (type 4): MED value
        # - LOCAL_PREF (type 5): Local preference
        # - COMMUNITY (type 8): Community values
        # Return: {as_path, next_hop, med, local_pref, ...}
        pass
    
    def _parse_nlri(self, data: bytes, offset: int = 0) -> List[str]:
        # NLRI format (prefixes):
        # - Length (1 byte): Prefix length in bits (0-32)
        # - Prefix (1-4 bytes): The IP prefix
        # Return: List of CIDR prefixes (e.g., ['10.0.0.0/24', '192.168.0.0/16'])
        pass
```

## 2. Enhanced core/influxdb_connector.py

Complete InfluxDBConnector with actual queries:

```python
class InfluxDBConnector:
    def __init__(self, url: str, token: str, org: str, bucket: str):
        from influxdb_client import InfluxDBClient
        self.client = InfluxDBClient(url=url, token=token, org=org)
        self.bucket = bucket
        self.org = org
    
    def write_metric(self, point: Point):
        # Write point to InfluxDB
        # point: from influxdb_client.client.write_api import Point
        pass
    
    def query_metrics(self, query: str) -> List[dict]:
        # Execute Flux query
        # Return list of dicts with results
        pass
    
    def query_route_stats(
        self,
        speaker_id: str,
        prefix: str = None,
        time_range: str = '7d'
    ) -> List[dict]:
        # Query: SELECT flap_count, route_count, path_diversity
        # WHERE speaker_id = ? AND prefix = ? AND time > now() - ?
        # ORDER BY time DESC
        pass
    
    def query_anomaly_timeline(
        self,
        time_range: str = '24h'
    ) -> List[dict]:
        # Query all anomalies in time range
        pass
    
    def query_correlation_matrix(
        self,
        time_range: str = '7d'
    ) -> dict:
        # Compute correlation matrix for prefixes
        # Return: {prefix1: {prefix2: 0.85, prefix3: 0.92, ...}, ...}
        pass
```

## 3. Enhanced API Routes (api/routes/)

### api/routes/telemetry.py

```python
@router.post("/bmp/ingest")
async def ingest_bmp_message(
    message: bytes,
    db: Session = Depends(get_db)
):
    \"\"\"
    Receive BMP message from router.
    
    Process:
    1. Parse binary BMP message
    2. Extract speaker, prefix, path attributes
    3. Create RouteEvent record
    4. Write metrics to InfluxDB
    5. Return success
    \"\"\"
    pass

@router.get("/speakers")
async def list_speakers(
    db: Session = Depends(get_db)
) -> List[BGPSpeakerResponse]:
    # Query all BGP speakers
    # Return: [{id, hostname, router_id, asn, status, last_seen}, ...]
    pass

@router.get("/speakers/{speaker_id}")
async def get_speaker(
    speaker_id: str,
    db: Session = Depends(get_db)
) -> BGPSpeakerResponse:
    # Get single speaker
    pass

@router.get("/speakers/{speaker_id}/status")
async def speaker_status(
    speaker_id: str,
    db: Session = Depends(get_db)
) -> dict:
    # Return: {status, last_seen, connected_for, routes_advertised, routes_withdrawn}
    pass

@router.get("/route-events")
async def query_route_events(
    speaker_id: str = None,
    prefix: str = None,
    neighbor_ip: str = None,
    event_type: str = None,  # UPDATE or WITHDRAW
    limit: int = 100,
    db: Session = Depends(get_db)
) -> List[RouteEventResponse]:
    # Query route events with filters
    # Return: [{timestamp, prefix, neighbor_ip, path_attributes, event_type}, ...]
    pass

@router.get("/metrics/route-stats/{speaker_id}")
async def get_route_stats(
    speaker_id: str,
    prefix: str = None,
    time_range: str = '7d',  # 1h, 24h, 7d
    influx: InfluxDBConnector = Depends(get_influxdb_connector)
) -> dict:
    # Query metrics from InfluxDB
    # Return: {speaker_id, prefix, flap_count, route_count, path_diversity, ...}
    pass

@router.get("/metrics/correlation")
async def get_correlation_matrix(
    time_range: str = '7d',
    influx: InfluxDBConnector = Depends(get_influxdb_connector)
) -> dict:
    # Return correlation matrix showing which prefixes fail together
    # Use for detecting link failures
    pass
```

## 4. Enhanced Celery Tasks (tasks/ingestion.py)

```python
@shared_task
def parse_bmp_message(message_bytes: bytes) -> dict:
    \"\"\"Parse incoming BMP message.\"\"\"
    pass

@shared_task
def ingest_metrics(parsed_message: dict, db_session=None):
    \"\"\"
    Ingest metrics to InfluxDB.
    
    Steps:
    1. Extract route event from parsed message
    2. Write to PostgreSQL (RouteEvent table)
    3. Write metrics to InfluxDB:
       - flap_count (increment if already seen in 5-min window)
       - route_count (sum of advertised routes)
       - path_diversity (unique AS paths)
    4. Return metrics written
    \"\"\"
    pass

@shared_task
def compute_aggregates():
    \"\"\"
    Compute 5-minute aggregates from 1-second metrics.
    
    Run every 5 minutes via celery beat.
    \"\"\"
    pass
```

## 5. BMP Server (api/bmp_server.py)

```python
class BMPServer:
    \"\"\"TCP server that listens for BMP messages from routers.\"\"\"
    
    def __init__(self, host: str = '0.0.0.0', port: int = 179):
        pass
    
    async def start(self):
        # Start TCP server on port 179
        # Accept connections from routers
        # Parse each message with BMPParser
        # Queue to Celery for processing
        pass
    
    async def handle_connection(self, reader, writer):
        # Read BMP messages from router
        # Parse each message
        # Queue parse_bmp_message_task
        pass
```

## 6. Enhanced docker-compose.yml

Add:
- celery beat scheduler
- BMP server service
- InfluxDB bucket initialization
- Environment variables for InfluxDB

## 7. Enhanced Tests (tests/)

Create test files:
- tests/unit/test_bmp_parser.py: Test parsing various BMP messages
- tests/unit/test_influxdb_connector.py: Test InfluxDB operations
- tests/integration/test_telemetry_ingestion.py: End-to-end ingestion

## LOCAL TESTING CHECKLIST

After implementation:

1. ✅ docker compose up (all services healthy)
2. ✅ pytest tests/unit/test_bmp_parser.py -v (all parser tests pass)
3. ✅ pytest tests/unit/test_influxdb_connector.py -v (InfluxDB tests pass)
4. ✅ Test API routes:
   - curl http://localhost:8000/api/speakers
   - curl http://localhost:8000/api/route-events
5. ✅ pytest tests/ -v --cov (85%+ coverage)

After all pass:
- git add .
- git commit -m "Phase 2: Telemetry ingestion implementation"
- git push
```

---

## STEP 2: Local Testing After Cowork

(Same pattern as Phase 1 - verify scaffold with docker, pytest, curl)

---

## STEP 3: Cursor Phase 2 - RouteMonitor Telemetry Implementation

```
I received Phase 2 scaffold. Now implementing telemetry pipeline.

[Same pattern as NetDeploy Cursor prompts - implement all methods, run tests, verify]

## WHAT I NEED TO IMPLEMENT

### 1. Complete BMP Parser (core/bmp_parser.py)

Implement full RFC 7854 binary parsing:
- parse_message(): Read header, route to handler
- _parse_per_peer_header(): Extract peer info
- _parse_route_monitoring(): Parse UPDATE/WITHDRAW
- _parse_bgp_update(): Parse BGP UPDATE structure
- _parse_path_attributes(): Parse AS_PATH, NEXT_HOP, MED, LOCAL_PREF
- _parse_nlri(): Parse CIDR prefixes

Test with sample BMP messages (provided in fixtures).

### 2. Complete InfluxDB Connector (core/influxdb_connector.py)

Implement all query methods using Flux queries:
- write_metric(): Write Point to InfluxDB
- query_metrics(): Execute Flux query
- query_route_stats(): Query flap_count, route_count, path_diversity
- query_anomaly_timeline(): Get timeline of anomalies

### 3. Implement API Routes (api/routes/telemetry.py)

Implement all endpoints:
- POST /api/bmp/ingest: Receive and process BMP message
- GET /api/speakers: List all speakers
- GET /api/speakers/{id}: Get speaker details
- GET /api/route-events: Query route events
- GET /api/metrics/route-stats: Query metrics from InfluxDB

### 4. Implement Celery Tasks (tasks/ingestion.py)

Implement:
- parse_bmp_message(): Parse binary → JSON
- ingest_metrics(): Write to PostgreSQL + InfluxDB
- compute_aggregates(): 5-min aggregation

### 5. Run Full Test Suite

```bash
docker compose up
docker compose exec api pytest tests/ -v --cov=api --cov=core --cov-report=term-missing

# Expected:
# - All tests PASSED
# - 85%+ coverage
# - No import errors
```

## LOCAL VERIFICATION

After implementation:

1. ✅ Parse BMP message: pytest tests/unit/test_bmp_parser.py -v
2. ✅ Write to InfluxDB: pytest tests/unit/test_influxdb_connector.py -v
3. ✅ API ingestion:
   - curl -X POST http://localhost:8000/api/bmp/ingest -d [binary]
4. ✅ Query routes:
   - curl http://localhost:8000/api/route-events
5. ✅ Query metrics:
   - curl http://localhost:8000/api/metrics/route-stats/router1
6. ✅ pytest tests/ -v --cov (85%+ coverage)

After all pass:
- git add .
- git commit -m "Phase 2: Telemetry ingestion implementation"
- git push
```

---

# PHASE 3: ANOMALY DETECTION (Weeks 3-5)

[Similar structure: Cowork scaffold → test → Cursor implementation → test]

**Key implementations:**
- Z-score baseline detection
- Isolation Forest multivariate detection
- Correlation analysis for link failures
- Alert dispatcher with retry logic
- Celery tasks for detection pipeline

---

# PHASE 4: DASHBOARD (Week 5-6)

[Similar structure]

**Key implementations:**
- Streamlit pages: Route Timeline, Device Health, Anomaly Timeline, Correlation Matrix
- Real-time WebSocket updates
- API client for fetching data
- Interactive charts (Plotly)

---

# PHASE 5: PRODUCTION READINESS (Week 6-7)

[Similar structure]

**Key implementations:**
- Kubernetes manifests
- Helm charts
- Prometheus monitoring
- Load testing
- Security scanning

---

# PHASE 6: PORTFOLIO POLISH (Week 7-8)

[Similar structure]

**Key deliverables:**
- Professional README.md
- Detailed ARCHITECTURE.md
- Blog post outline
- Interview talking points
- Demo scenarios

---

## COMPLETE EXECUTION WORKFLOW

For each phase (1-6):

### Step 1: Cowork Scaffold (30 min)
```bash
# Copy Cowork Phase N prompt
# Paste into Claude Cowork
# Download files
# Commit to new branch: git checkout -b phase-N
```

### Step 2: Local Test (10 min)
```bash
docker compose up
pytest tests/ -v
curl http://localhost:8000/health
# Verify everything works
```

### Step 3: Cursor Implementation (60-90 min)
```bash
# Copy Cursor Phase N prompt
# Paste into Cursor
# Implement all code
# Run tests locally
```

### Step 4: Local Test (20 min)
```bash
docker compose up
pytest tests/ -v --cov
# Verify 85%+ coverage
# Verify all API endpoints
```

### Step 5: Git Push (5 min)
```bash
git add .
git commit -m "Phase N: [description]"
git push origin phase-N
# Create PR, review, merge to main
```

---

## TIME ESTIMATE

| Phase | Cowork | Test | Cursor | Test | Total |
|-------|--------|------|--------|------|-------|
| 1 | 30 min | 10 min | 60 min | 20 min | 2 hours |
| 2 | 25 min | 10 min | 75 min | 20 min | 2h 10 min |
| 3 | 35 min | 15 min | 120 min | 30 min | 3h 40 min |
| 4 | 20 min | 10 min | 60 min | 20 min | 1h 50 min |
| 5 | 20 min | 15 min | 45 min | 20 min | 1h 40 min |
| 6 | 15 min | 10 min | 45 min | 20 min | 1h 30 min |
| **TOTAL** | **2h 25 min** | **1h 10 min** | **6h 45 min** | **2h 30 min** | **~13 hours** |

**Spread across 8-10 weeks for high quality.**

---

## RESUME ALIGNMENT

### Rohith's Experience
- 10K+ routers with BGP/OSPF
- Manual deployment → error-prone
- No real-time visibility

### RouteMonitor Solution
✅ Automates BGP telemetry collection (BMP protocol)
✅ Real-time anomaly detection (ML algorithms)
✅ Handles 10K+ device scale (1M+ updates/min)
✅ Demonstrates data systems depth (time-series, ML, streaming)
✅ Solves Hexagon's exact problem

### Interview Angle
> "At Hexagon, we managed 10K+ routers but had zero visibility into BGP anomalies until customers complained. RouteMonitor solves this: continuous BMP telemetry from every router, ML-based anomaly detection (Z-score + Isolation Forest), real-time alerts. Detects route flaps, link failures, convergence issues in <30 seconds. Built to handle Hexagon-scale traffic."

---

Ready to start? Copy the appropriate phase prompt based on where you are! 🚀
