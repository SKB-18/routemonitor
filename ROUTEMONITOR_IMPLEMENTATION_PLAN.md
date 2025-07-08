# RouteMonitor: Real-Time Network Telemetry & Anomaly Detection
## Standalone Graduate-Level Implementation Plan

**Project:** RouteMonitor  
**Author:** Thandava Sai Rohith Achanta  
**Duration:** 6-8 weeks  
**Division:** Cowork (Architecture/Scaffolding) → Cursor (Implementation/Coding)  
**Repository:** routemonitor (standalone)

---

## I. PROJECT VISION

### Problem Statement
BGP path anomalies, route flaps, and routing convergence issues cause silent failures or suboptimal routing. Network teams lack real-time visibility into routing decisions with:
- No centralized telemetry collection (data scattered across devices)
- No historical baselines (can't detect anomalies)
- Reactive troubleshooting (detect via customer complaints)
- No correlation analysis (which prefixes affected by link failure?)
- Manual log analysis (MTTR hours → days)

### Solution
**RouteMonitor:** A telemetry collection + analytics platform that streams BGP data in real-time, learns normal routing patterns, and detects anomalies automatically.

**Capabilities:**
- Real-time BGP telemetry collection (BMP protocol)
- Time-series metrics storage (route counts, churn rates, convergence time)
- Statistical + ML-based anomaly detection
- Automated alerting (webhooks, Slack, PagerDuty)
- Analytics dashboard (route timeline, device health, correlation analysis)

### Resume Alignment
**Hexagon R&D Experience:**
- Analyzed routing table inconsistencies, debugged BGP path selection issues
- Troubleshot critical outages, MTTR -40%
- Worked with TCP/IP routing, packet forwarding

**RouteMonitor elevates this to:**
- Real-time data collection at scale (millions of updates/min)
- Distributed systems (streaming, time-series, analytics)
- ML/Data engineering (anomaly detection, forecasting)
- Observability + SRE culture (proactive vs reactive)

---

## II. DETAILED SYSTEM ARCHITECTURE

### 2.1 High-Level Flow

```
┌──────────────────────────────────────────────────────────────┐
│              NETWORK INFRASTRUCTURE                           │
│  Router 1 (BGP) --┐                                           │
│  Router 2 (BGP) --├─ Send BMP Telemetry                       │
│  Router 3 (BGP) --┘                                           │
└──────────┬─────────────────────────────────────────────────────┘
           │ BMP Stream (TCP)
           ▼
┌──────────────────────────────────────────────────────────────┐
│           ROUTEMONITOR PLATFORM                               │
├──────────────────────────────────────────────────────────────┤
│                                                                │
│  BMP Server (TCP Listener)                                    │
│  ├── Accept router connections                                │
│  ├── Parse BMP messages (binary)                              │
│  └── Queue route events                                       │
│         │                                                      │
│         ▼                                                      │
│  Message Processor (Celery Tasks)                             │
│  ├── Parse BMP message                                        │
│  ├── Extract route events (UPDATE, WITHDRAWAL)                │
│  ├── Store to PostgreSQL (RouteEvent table)                   │
│  └── Write metrics to InfluxDB                                │
│         │                                                      │
│         ▼                                                      │
│  Time-Series Database (InfluxDB)                              │
│  ├── Metric: route_count per prefix                           │
│  ├── Metric: flap_count (route churn)                         │
│  ├── Metric: path_diversity (# of alternate paths)            │
│  └── Metric: convergence_time                                 │
│         │                                                      │
│         ▼                                                      │
│  Anomaly Detector (Async Tasks)                               │
│  ├── Baseline learning (first 7 days)                         │
│  ├── Statistical anomalies (Z-score)                          │
│  ├── ML anomalies (Isolation Forest)                          │
│  ├── Correlation analysis (linked failures)                   │
│  └── Deduplication (avoid alert spam)                         │
│         │                                                      │
│         ▼                                                      │
│  Alert Dispatcher                                             │
│  ├── Webhook notifications                                    │
│  ├── Retry logic (exponential backoff)                        │
│  ├── Severity-based filtering                                 │
│  └── Deduplication (same alert within 5 min)                  │
│         │                                                      │
│         ▼                                                      │
│  API Gateway (FastAPI)                                        │
│  ├── POST /telemetry/bmp (ingest BMP data)                    │
│  ├── GET  /routes (query route events)                        │
│  ├── GET  /anomalies (list detected anomalies)                │
│  ├── GET  /metrics/speaker/{id} (telemetry metrics)           │
│  ├── GET  /correlation (linked failures)                      │
│  └── POST /alerts/config (webhook subscriptions)              │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │ Analytics Dashboard (Streamlit/React)                     │ │
│  │ - Route timeline (when did prefix stabilize?)             │ │
│  │ - Device health (uptime, update rate, errors)             │ │
│  │ - Anomaly timeline (when did deviations occur?)           │ │
│  │ - Correlation matrix (which prefixes fail together?)      │ │
│  │ - Alert history                                           │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 Data Models

```python
BGPSpeaker
├── id (UUID)
├── hostname (string)
├── router_id (IPv4)
├── local_asn (int)
├── bmp_listen_address (IPv4) [where speaker sends telemetry]
├── last_update (datetime)
├── status (enum: UP, DOWN, DEGRADED)
└── created_at (datetime)

RouteEvent (Immutable Event Log)
├── id (UUID)
├── speaker_id (FK → BGPSpeaker)
├── timestamp (datetime, UTC)
├── event_type (enum: UPDATE, WITHDRAW, STATE_CHANGE)
├── prefix (CIDR string)
├── path_attributes (JSON) [AS_PATH, NEXT_HOP, ORIGIN, LOCAL_PREF, etc.]
├── withdrawn_prefixes (JSON, nullable)
├── neighbor_ip (IPv4)
├── neighbor_asn (int)
├── sequence_number (int) [ordering within speaker]
└── created_at (datetime)

RouteMetrics (Time-Series in InfluxDB)
├── timestamp (datetime)
├── measurement: "route_stats"
├── tags:
│   ├── speaker_id
│   ├── prefix (CIDR)
│   └── neighbor_ip
├── fields:
│   ├── route_count (int)
│   ├── best_path_length (int) [AS hops]
│   ├── path_diversity (int) [# of competing paths]
│   ├── flap_count (int) [route churn in interval]
│   ├── last_update_seconds_ago (float)
│   └── convergence_time_ms (float)

Anomaly
├── id (UUID)
├── speaker_id (FK)
├── prefix (CIDR, nullable) [null = system-wide anomaly]
├── neighbor_ip (IPv4, nullable)
├── anomaly_type (enum: ROUTE_FLAP, PATH_INSTABILITY, CONVERGENCE_DELAY, UNUSUAL_CHURN, CORRELATED_FAILURE)
├── detected_at (datetime)
├── resolved_at (datetime, nullable)
├── severity (enum: INFO, WARNING, CRITICAL)
├── details (JSON) [metric values, Z-score, affected_prefixes, etc.]
├── acknowledged (bool)
├── acknowledged_by (string, nullable)
├── acknowledged_at (datetime, nullable)
└── created_at (datetime)

Alert
├── id (UUID)
├── anomaly_id (FK → Anomaly)
├── alert_type (enum: WEBHOOK, EMAIL, SLACK, PAGERDUTY)
├── target_url (string) [webhook URL]
├── message (string)
├── severity (enum)
├── sent_at (datetime)
├── delivery_status (enum: PENDING, DELIVERED, FAILED)
├── retry_count (int)
└── last_retry_at (datetime, nullable)

BGPSpeakerMetrics (Summary Stats)
├── speaker_id (FK)
├── measurement_date (date)
├── total_prefixes (int)
├── unique_neighbors (int)
├── total_flaps (int)
├── avg_convergence_time_ms (float)
├── uptime_percent (float)
└── anomaly_count (int)
```

### 2.3 Core Components

#### BMP Protocol Parser
**Purpose:** Parse binary BGP Monitoring Protocol (RFC 7854) messages

**Message Types:**
- Route Monitoring (Routes + Path Attributes)
- Route Mirroring (BGP messages received by router)
- Peer Down / Peer Up (Session state changes)
- Statistics Report (Per-peer statistics)

**Outputs:** RouteEvent objects (prefix, AS_PATH, NEXT_HOP, etc.)

#### Telemetry Ingester
**Purpose:** Consume BMP messages, normalize, store

**Flow:**
1. BMP server receives TCP connection from router
2. Parse binary BMP message
3. Extract route event
4. Create RouteEvent record (PostgreSQL)
5. Write metrics to InfluxDB
6. Emit to event stream (Kafka/Redis)

#### AnomalyDetector
**Purpose:** Detect routing anomalies using statistical + ML methods

**Algorithms:**
- **Z-score:** Detect unusual route churn (>3 sigma from baseline)
- **Isolation Forest:** Multivariate anomaly detection on route count, path diversity, flap rate
- **Correlation Analysis:** Find prefixes failing together (indicator of link failure)
- **Forecasting:** ARIMA/Prophet predict next hour's churn

**Baseline:** First 7 days of data = "normal"

#### AlertDispatcher
**Purpose:** Send notifications for detected anomalies

**Channels:**
- Webhooks (generic)
- Slack
- PagerDuty
- Email

**Logic:**
- Fetch alert subscriptions
- Filter by anomaly type + severity
- Dedup (same anomaly within 5 min window)
- Retry with exponential backoff

#### Analytics Dashboard
**Purpose:** Visualize routing health + anomalies

**Pages:**
- Route Timeline: When did prefix stabilize after event?
- Device Health: Uptime, update rate, error stats
- Anomaly Timeline: When did deviations occur?
- Correlation Matrix: Which prefixes fail together?

---

## III. TECHNOLOGY STACK

| Component | Technology | Why | Cost |
|-----------|-----------|-----|------|
| **Language** | Python 3.9+ | Your strength, data science libs (sklearn, pandas) | Free |
| **Framework** | FastAPI | Async, modern, auto-docs | Free |
| **BMP Protocol** | Custom binary parser | No standard library; RFC 7854 | Free |
| **Event Queue** | Kafka or Redis | Streaming messages for processing | Free (OSS) |
| **Time-Series DB** | InfluxDB | Optimized for metrics, fast writes | Free (OSS) |
| **SQL DB** | PostgreSQL | Audit trail + event log | Free (OSS) |
| **ML/Stats** | scikit-learn, numpy | Z-score, Isolation Forest, stats | Free |
| **Forecasting** | Prophet or ARIMA | Time-series prediction | Free |
| **Frontend** | Streamlit or React | Dashboard | Free |
| **Async Jobs** | Celery + Redis | Anomaly detection async | Free (OSS) |
| **Testing** | pytest | Unit + integration tests | Free |
| **Network Sim** | Containerlab + Exabgp | Test with real BGP routers | Free (OSS) |
| **Containerization** | Docker | Dev + prod consistency | Free |
| **Orchestration** | Docker Compose (dev) / k8s (prod) | Local testing, scaling | Free |
| **CI/CD** | GitHub Actions | Automated testing | Free |
| **Monitoring** | Prometheus + Grafana | Metrics + dashboards | Free (OSS) |

---

## IV. IMPLEMENTATION PHASES (6-8 Weeks)

### Phase 1: Foundation (Week 1)

**Duration:** 1 week  
**Cowork Output:** Repository scaffold + all infrastructure  
**Cursor Output:** Database + event simulator + app setup

#### Cowork Deliverables

**1.1 Repository Structure**
```
routemonitor/
├── api/
│   ├── __init__.py
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── telemetry.py (BMP ingestion, route queries)
│   │   ├── anomalies.py (list, acknowledge, forecast)
│   │   ├── metrics.py (speaker metrics, correlation)
│   │   ├── alerts.py (webhook config, history)
│   │   └── health.py (health check)
│   ├── schemas.py (Pydantic models)
│   ├── models.py (SQLAlchemy ORM stubs)
│   ├── dependencies.py (auth, db, logging)
│   └── main.py (FastAPI app)
├── core/
│   ├── __init__.py
│   ├── bmp_parser.py (BMP protocol parser skeleton)
│   ├── detector.py (AnomalyDetector skeleton)
│   ├── dispatcher.py (AlertDispatcher skeleton)
│   ├── influxdb_client.py (InfluxDB connector skeleton)
│   └── config.py (Settings, env vars)
├── tasks/
│   ├── __init__.py
│   ├── celery_app.py (Celery initialization)
│   └── telemetry.py (Celery task definitions)
├── tests/
│   ├── __init__.py
│   ├── conftest.py (pytest fixtures)
│   ├── unit/
│   │   ├── test_bmp_parser.py
│   │   ├── test_detector.py
│   │   ├── test_dispatcher.py
│   │   └── test_influxdb_client.py
│   ├── integration/
│   │   ├── test_telemetry_flow.py
│   │   ├── test_anomaly_detection.py
│   │   └── test_alert_dispatch.py
│   └── fixtures/
│       ├── bgp_telemetry.py (mock BMP data generator)
│       ├── bmp_messages.bin (sample BMP packets)
│       └── exabgp_config.conf (BGP simulator config)
├── dashboard/
│   ├── app.py (Streamlit app skeleton)
│   ├── pages/
│   │   ├── routes.py (route timeline)
│   │   ├── devices.py (device health)
│   │   ├── anomalies.py (anomaly timeline)
│   │   └── correlation.py (correlation analysis)
│   └── utils/
│       ├── api_client.py
│       └── formatting.py
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── requirements-dev.txt
├── .env.example
├── .gitignore
├── setup.py
├── pytest.ini
├── .github/workflows/
│   ├── test.yml
│   ├── lint.yml
│   └── deploy.yml
├── README.md
├── ARCHITECTURE.md
└── DEVELOPMENT.md
```

**Deliverable:** Commit to GitHub with all structure.

---

**1.2 ORM Models + Pydantic Schemas**

```python
# Complete SQLAlchemy model definitions provided (not stubs)

from sqlalchemy import Column, String, Integer, UUID, Enum, JSON, DateTime, Text, ForeignKey, Float, Boolean
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
from uuid import uuid4

Base = declarative_base()

class BGPSpeaker(Base):
    __tablename__ = "bgp_speakers"
    id = Column(UUID, primary_key=True, default=uuid4)
    hostname = Column(String(255), unique=True, nullable=False)
    router_id = Column(String(15), nullable=False)  # IPv4
    local_asn = Column(Integer, nullable=False)
    bmp_listen_address = Column(String(15), nullable=False)
    last_update = Column(DateTime, nullable=True)
    status = Column(String(20), default="UP")  # UP, DOWN, DEGRADED
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_speakers_hostname', 'hostname'),
        Index('idx_speakers_router_id', 'router_id'),
    )

class RouteEvent(Base):
    __tablename__ = "route_events"
    id = Column(UUID, primary_key=True, default=uuid4)
    speaker_id = Column(UUID, ForeignKey("bgp_speakers.id"), nullable=False)
    timestamp = Column(DateTime, nullable=False)  # UTC
    event_type = Column(String(20), nullable=False)  # UPDATE, WITHDRAW, STATE_CHANGE
    prefix = Column(String(50), nullable=True)  # CIDR
    path_attributes = Column(JSON, nullable=True)
    withdrawn_prefixes = Column(JSON, nullable=True)
    neighbor_ip = Column(String(15), nullable=False)
    neighbor_asn = Column(Integer, nullable=False)
    sequence_number = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_route_events_speaker_timestamp', 'speaker_id', 'timestamp'),
        Index('idx_route_events_prefix', 'prefix'),
    )

class Anomaly(Base):
    __tablename__ = "anomalies"
    id = Column(UUID, primary_key=True, default=uuid4)
    speaker_id = Column(UUID, ForeignKey("bgp_speakers.id"), nullable=False)
    prefix = Column(String(50), nullable=True)
    neighbor_ip = Column(String(15), nullable=True)
    anomaly_type = Column(String(50), nullable=False)  # ROUTE_FLAP, etc.
    detected_at = Column(DateTime, nullable=False)
    resolved_at = Column(DateTime, nullable=True)
    severity = Column(String(20), nullable=False)  # INFO, WARNING, CRITICAL
    details = Column(JSON, nullable=True)
    acknowledged = Column(Boolean, default=False)
    acknowledged_by = Column(String(100), nullable=True)
    acknowledged_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index('idx_anomalies_speaker_timestamp', 'speaker_id', 'detected_at'),
    )

class Alert(Base):
    __tablename__ = "alerts"
    id = Column(UUID, primary_key=True, default=uuid4)
    anomaly_id = Column(UUID, ForeignKey("anomalies.id"), nullable=False)
    alert_type = Column(String(20), nullable=False)  # WEBHOOK, SLACK, etc.
    target_url = Column(String(500), nullable=False)
    message = Column(Text, nullable=False)
    severity = Column(String(20), nullable=False)
    sent_at = Column(DateTime, nullable=False)
    delivery_status = Column(String(20), default="PENDING")  # PENDING, DELIVERED, FAILED
    retry_count = Column(Integer, default=0)
    last_retry_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

# Pydantic schemas
from pydantic import BaseModel, Field, IPv4Address
from typing import Optional, List, Dict, Any
from uuid import UUID as PyUUID

class BGPSpeakerRequest(BaseModel):
    hostname: str = Field(..., min_length=1)
    router_id: IPv4Address
    local_asn: int = Field(..., ge=1, le=4294967295)
    bmp_listen_address: IPv4Address

class RouteEventRequest(BaseModel):
    speaker_id: PyUUID
    timestamp: datetime
    event_type: str  # UPDATE, WITHDRAW
    prefix: Optional[str]
    path_attributes: Optional[Dict[str, Any]]
    withdrawn_prefixes: Optional[List[str]]
    neighbor_ip: IPv4Address
    neighbor_asn: int

class AnomalyResponse(BaseModel):
    id: PyUUID
    speaker_id: PyUUID
    prefix: Optional[str]
    anomaly_type: str
    severity: str
    detected_at: datetime
    details: Optional[dict]
    acknowledged: bool

class AlertWebhookRequest(BaseModel):
    target_url: str
    severity_min: str = "WARNING"
    anomaly_types: List[str] = ["ROUTE_FLAP", "UNUSUAL_CHURN"]
```

**Deliverable:** All models + schemas (fully defined).

---

**1.3 Docker Compose + Services**

```yaml
version: '3.8'

services:
  api:
    build: .
    container_name: routemonitor-api
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://routemonitor:password@db:5432/routemonitor
      REDIS_URL: redis://redis:6379/0
      INFLUXDB_URL: http://influxdb:8086
    depends_on:
      - db
      - redis
      - influxdb
    volumes:
      - .:/app
    command: uvicorn api.main:app --host 0.0.0.0 --reload

  celery:
    build: .
    container_name: routemonitor-celery
    command: celery -A tasks.celery_app worker --loglevel=info
    environment:
      DATABASE_URL: postgresql://routemonitor:password@db:5432/routemonitor
      REDIS_URL: redis://redis:6379/0
      INFLUXDB_URL: http://influxdb:8086
    depends_on:
      - db
      - redis
      - influxdb

  db:
    image: postgres:15-alpine
    container_name: routemonitor-postgres
    environment:
      POSTGRES_USER: routemonitor
      POSTGRES_PASSWORD: password
      POSTGRES_DB: routemonitor
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  redis:
    image: redis:7-alpine
    container_name: routemonitor-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  influxdb:
    image: influxdb:2-alpine
    container_name: routemonitor-influxdb
    ports:
      - "8086:8086"
    environment:
      INFLUXDB_DB: routemonitor
      INFLUXDB_ADMIN_USER: admin
      INFLUXDB_ADMIN_PASSWORD: admin
    volumes:
      - influxdb_data:/var/lib/influxdb2

  prometheus:
    image: prom/prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml

  grafana:
    image: grafana/grafana
    ports:
      - "3000:3000"
    environment:
      GF_SECURITY_ADMIN_PASSWORD: admin

volumes:
  postgres_data:
  redis_data:
  influxdb_data:
```

**Deliverable:** docker-compose.yml with all services.

---

**1.4 CI/CD Pipelines**

```yaml
# .github/workflows/test.yml
name: Unit & Integration Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: password
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
    
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.9'
      
      - name: Install dependencies
        run: pip install -r requirements-dev.txt
      
      - name: Run pytest
        run: pytest tests/ --cov=api --cov=core
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

**Deliverable:** CI/CD pipelines.

---

**1.5 Test Fixtures & BGP Simulator**

```python
# tests/conftest.py - Complete fixtures

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from api.models import Base
from fastapi.testclient import TestClient
from api.main import app

@pytest.fixture
def db_session():
    """Test database session."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    yield session
    session.close()

@pytest.fixture
def client(db_session):
    """FastAPI test client."""
    from api.dependencies import get_db
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)

@pytest.fixture
def mock_speaker(db_session):
    """Mock BGP speaker."""
    from api.models import BGPSpeaker
    speaker = BGPSpeaker(
        hostname="test-router-1",
        router_id="192.168.1.1",
        local_asn=65001,
        bmp_listen_address="192.168.1.1"
    )
    db_session.add(speaker)
    db_session.commit()
    return speaker

# tests/fixtures/bgp_telemetry.py
class BGPTelemetryGenerator:
    """Generate realistic BGP telemetry data for testing."""
    
    @staticmethod
    def generate_route_update(prefix: str, asn: int) -> dict:
        """Generate BGP UPDATE event."""
        return {
            "event_type": "UPDATE",
            "prefix": prefix,
            "path_attributes": {
                "AS_PATH": [65001, 65002, 65003],
                "NEXT_HOP": "192.168.1.2",
                "ORIGIN": "IGP",
                "LOCAL_PREF": 100,
                "MED": 0
            }
        }
    
    @staticmethod
    def generate_route_withdraw(prefix: str) -> dict:
        """Generate BGP WITHDRAW event."""
        return {
            "event_type": "WITHDRAW",
            "withdrawn_prefixes": [prefix]
        }
    
    @staticmethod
    def generate_flapping_routes(num_flaps: int = 50) -> list:
        """Generate flapping route (withdraw + update repeatedly)."""
        events = []
        for i in range(num_flaps):
            if i % 2 == 0:
                events.append(BGPTelemetryGenerator.generate_route_update("10.0.0.0/8", 65001))
            else:
                events.append(BGPTelemetryGenerator.generate_route_withdraw("10.0.0.0/8"))
        return events
```

**Deliverable:** Full test infrastructure.

---

#### Cursor Deliverables (Week 1)

**1.1 Implement SQLAlchemy Models**
- [ ] All model classes: BGPSpeaker, RouteEvent, Anomaly, Alert
- [ ] Migrations: `alembic upgrade head`
- [ ] Verify schema in PostgreSQL

**1.2 Pydantic Schemas**
- [ ] All request/response schemas
- [ ] Custom validators (IPv4, ASN, CIDR)
- [ ] Unit tests: `pytest tests/unit/test_schemas.py`

**1.3 FastAPI App Setup**
- [ ] app initialization
- [ ] Middleware + error handlers
- [ ] Health check endpoint
- [ ] Swagger UI: `curl http://localhost:8000/docs`

**1.4 BGP Telemetry Generator**
- [ ] Generate realistic BMP data
- [ ] Simulate normal routing behavior
- [ ] Simulate flapping routes

**1.5 Docker Build**
- [ ] `docker compose up`
- [ ] Verify all services healthy
- [ ] `curl http://localhost:8000/health`

**Cursor Checklist (Week 1):**
- [ ] All ORM models + migrations applied
- [ ] Pydantic schemas with validators
- [ ] FastAPI app boots
- [ ] Docker Compose stack healthy
- [ ] Mock telemetry generator works
- [ ] CI/CD pipelines green

**Output:** Runnable empty API with database infrastructure.

---

### Phase 2: BMP Protocol Parser & Telemetry Ingestion (Weeks 2-3)

**Duration:** 1.5 weeks  
**Cowork Output:** BMP parser skeleton + InfluxDB client  
**Cursor Output:** Full parser + ingestion + tests

#### Cowork Deliverables

**2.1 BMP Protocol Parser Skeleton**

```python
# core/bmp_parser.py - Cowork provides structure

import struct
from typing import Dict, List, Tuple
from dataclasses import dataclass

@dataclass
class BMPMessage:
    """BMP Message structure (RFC 7854)."""
    version: int
    message_length: int
    message_type: int
    payload: bytes

class BMPParser:
    """Parse BGP Monitoring Protocol messages."""
    
    # Message types
    ROUTE_MONITORING = 0
    STATS_REPORT = 1
    PEER_DOWN = 2
    PEER_UP = 3
    ROUTE_MIRRORING = 4
    
    @staticmethod
    def parse_bmp_message(data: bytes) -> BMPMessage:
        """
        Parse BMP header (Cowork provides structure, Cursor implements):
        
        BMP Header (6 bytes):
        - Version (1 byte): Always 3
        - Message Length (4 bytes, big-endian): Total message size
        - Message Type (1 byte)
        
        Returns: BMPMessage object with parsed header + payload
        """
        pass
    
    @staticmethod
    def parse_per_peer_header(data: bytes) -> dict:
        """
        Parse Per-Peer Header (Cowork provides structure):
        
        Per-Peer Header (12 bytes):
        - Peer Type (1 byte): 0=Global Unicast, 1=RD Admin, etc.
        - Peer Flags (1 byte): V, L, A, O flags
        - Peer Distinguisher (8 bytes): For RD peers
        - Peer Address (4 or 16 bytes): IPv4 or IPv6
        - Peer AS (4 bytes): ASN of peer
        - Peer BGP ID (4 bytes): BGP router ID
        - Timestamp (4+4 bytes): Seconds and microseconds
        
        Returns: Dict with parsed fields
        """
        pass
    
    @staticmethod
    def parse_route_monitoring(payload: bytes) -> dict:
        """
        Parse Route Monitoring message (Cowork provides structure):
        
        Contains BGP UPDATE message (RFC 4271):
        - Withdrawn Routes Length (2 bytes)
        - Withdrawn Routes (variable)
        - Total Path Attribute Length (2 bytes)
        - Path Attributes (variable)
        - NLRI (Network Layer Reachability Information)
        
        Cursor implements: Extract and parse BGP UPDATE
        Returns: RouteEvent data (prefix, AS_PATH, NEXT_HOP, etc.)
        """
        pass
    
    @staticmethod
    def parse_path_attributes(data: bytes) -> dict:
        """
        Parse BGP Path Attributes (Cowork provides structure):
        
        Each path attribute:
        - Flags (1 byte): Optional, Transitive, etc.
        - Type Code (1 byte): AS_PATH=2, NEXT_HOP=3, etc.
        - Length (1-2 bytes)
        - Value (variable)
        
        Cursor implements: Parse each attribute type
        Returns: Dict of path attributes
        """
        pass
    
    @staticmethod
    def parse_as_path(data: bytes) -> list:
        """Parse AS_PATH attribute. [CURSOR IMPLEMENTS]"""
        pass
    
    @staticmethod
    def parse_nlri(data: bytes) -> List[str]:
        """Parse NLRI (prefixes). [CURSOR IMPLEMENTS]"""
        pass
```

**Deliverable:** BMP parser skeleton with detailed method signatures.

---

**2.2 InfluxDB Client Skeleton**

```python
# core/influxdb_client.py

from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

class InfluxDBConnector:
    """Write time-series metrics to InfluxDB."""
    
    def __init__(self, url: str, token: str, org: str, bucket: str):
        self.client = InfluxDBClient(url=url, token=token, org=org)
        self.org = org
        self.bucket = bucket
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
    
    async def write_metric(
        self,
        speaker_id: str,
        prefix: str,
        metrics: dict
    ):
        """
        Write routing metric to InfluxDB.
        
        Point format:
        - measurement: "route_stats"
        - tags: speaker_id, prefix, neighbor_ip
        - fields: route_count, flap_count, path_diversity, ...
        - timestamp: UTC
        
        Cursor implements: Create Point object, write to InfluxDB
        """
        pass
    
    async def query_metrics(
        self,
        speaker_id: str,
        time_range: str = "24h"
    ) -> List[dict]:
        """
        Query routing metrics for time range.
        
        time_range: "1h", "24h", "7d"
        
        Cursor implements: Flux query to InfluxDB, parse results
        Returns: List of metric points
        """
        pass
    
    async def query_anomaly_timeline(
        self,
        speaker_id: str,
        time_range: str = "24h"
    ) -> dict:
        """
        Query anomalies + metrics timeline for visualization.
        
        Cursor implements: Combine anomaly events + metrics
        """
        pass
    
    def close(self):
        """Close InfluxDB connection."""
        self.client.close()
```

**Deliverable:** InfluxDB client skeleton.

---

**2.3 Telemetry Ingestion API**

```python
# api/routes/telemetry.py - Cowork provides route stubs

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from api.dependencies import get_db
from core.bmp_parser import BMPParser

router = APIRouter(prefix="/api/telemetry", tags=["telemetry"])

@router.post("/bmp/messages")
async def ingest_bmp_messages(
    request: bytes,
    db: Session = Depends(get_db)
):
    """
    Ingest BMP messages from router.
    
    Request: Binary BMP stream
    
    Logic (Cursor implements):
    1. Parse BMP message
    2. Extract route event
    3. Create RouteEvent record
    4. Write to InfluxDB
    5. Enqueue anomaly detection task
    6. Return acknowledgement
    """
    pass

@router.get("/routes")
async def get_routes(
    speaker_id: str,
    prefix: str = None,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """
    Query route events.
    
    Returns: Recent route events, optionally filtered by prefix
    """
    pass

@router.get("/speakers")
async def list_speakers(db: Session = Depends(get_db)):
    """List all BGP speakers connected."""
    pass

@router.get("/speakers/{speaker_id}/status")
async def speaker_status(speaker_id: str, db: Session = Depends(get_db)):
    """Get speaker health status."""
    pass
```

**Deliverable:** API route stubs.

---

**2.4 Celery Tasks for Telemetry**

```python
# tasks/telemetry.py

@shared_task
def ingest_bmp_message(bmp_data: bytes):
    """
    Celery task: Parse BMP message + store.
    
    Steps:
    1. Parse BMP
    2. Create RouteEvent
    3. Write to InfluxDB
    4. Emit to Redis pub/sub
    """
    pass

@shared_task
def sync_speaker_state(speaker_id: str):
    """Celery task: Sync BGP speaker state."""
    pass
```

**Deliverable:** Task definitions.

---

#### Cursor Deliverables (Weeks 2-3)

**2.1 BMP Protocol Parser Full Implementation**

```python
# Implement:
# - parse_bmp_message(): Extract header + payload
# - parse_per_peer_header(): Extract peer details
# - parse_route_monitoring(): Extract UPDATE message
# - parse_path_attributes(): Parse all BGP path attributes
# - parse_as_path(): Extract AS_PATH
# - parse_nlri(): Parse prefixes

# Reference: RFC 7854 (BMP), RFC 4271 (BGP)

# Test targets:
# - pytest tests/unit/test_bmp_parser.py::test_parse_valid_update
# - pytest tests/unit/test_bmp_parser.py::test_parse_withdrawal
# - pytest tests/unit/test_bmp_parser.py::test_parse_as_path
```

**2.2 InfluxDB Client Implementation**

```python
# Implement:
# - write_metric(): Create Point + write
# - query_metrics(): Flux query for time-series data
# - query_anomaly_timeline(): Combine anomaly + metrics

# Test: pytest tests/unit/test_influxdb_client.py
```

**2.3 Telemetry Ingestion API**

```python
# Implement endpoints:
# - POST /telemetry/bmp/messages → parse + store
# - GET  /telemetry/routes → query route events
# - GET  /telemetry/speakers → list speakers
# - GET  /telemetry/speakers/{id}/status → health

# Test: pytest tests/integration/test_telemetry_ingestion.py
```

**2.4 Unit + Integration Tests**

```python
# tests/unit/test_bmp_parser.py
def test_parse_valid_update_message():
    """Parse valid BGP UPDATE message."""
    bmp_data = load_test_bmp_update()
    result = BMPParser.parse_bmp_message(bmp_data)
    assert result.message_type == BMPParser.ROUTE_MONITORING
    assert result.payload is not None

def test_parse_as_path():
    """Extract AS_PATH from UPDATE."""
    as_path_data = load_test_as_path()
    result = BMPParser.parse_as_path(as_path_data)
    assert result == [65001, 65002, 65003]

# tests/integration/test_telemetry_ingestion.py
@pytest.mark.asyncio
async def test_bmp_ingestion():
    """Full ingestion: BMP → RouteEvent → InfluxDB."""
    bmp_data = load_test_bmp_message()
    response = client.post("/api/telemetry/bmp/messages", content=bmp_data)
    assert response.status_code == 200
    
    # Verify RouteEvent created
    route_events = db_session.query(RouteEvent).all()
    assert len(route_events) > 0
    
    # Verify InfluxDB metrics written
    # (query InfluxDB directly)
```

**Cursor Checklist (Weeks 2-3):**
- [ ] BMP parser handles UPDATE + WITHDRAWAL messages
- [ ] AS_PATH, NEXT_HOP, prefixes extracted correctly
- [ ] RouteEvent records created in PostgreSQL
- [ ] Metrics written to InfluxDB
- [ ] All ingestion tests pass
- [ ] Coverage 85%+

**Output:** Fully working telemetry ingestion pipeline.

---

### Phase 3: Anomaly Detection (Weeks 3-4)

**Duration:** 1 week  
**Cowork Output:** AnomalyDetector skeleton + detection algorithms  
**Cursor Output:** Full implementation + tests

#### Cowork Deliverables

**3.1 AnomalyDetector Skeleton**

```python
# core/detector.py

from sklearn.ensemble import IsolationForest
import numpy as np
from scipy import stats

class AnomalyDetector:
    """Detect routing anomalies using statistical + ML methods."""
    
    def __init__(self, lookback_window: int = 7 * 24 * 3600):
        self.lookback = lookback_window  # 7 days
        self.z_score_threshold = 3.0  # 3-sigma
        self.isolation_forest = IsolationForest(contamination=0.05)
    
    async def detect_anomalies(self, speaker_id: str) -> List[Anomaly]:
        """
        Main detection pipeline (Cursor implements each step):
        
        1. Fetch historical metrics (7-day window from InfluxDB)
        2. Calculate baseline (first 7 days = "normal")
        3. Z-score anomalies (route churn > 3 sigma)
        4. ML anomalies (Isolation Forest on multivariate metrics)
        5. Correlation analysis (prefixes failing together)
        6. Deduplicate + filter
        7. Return Anomaly records
        """
        pass
    
    def _compute_baseline(self, metrics: List[dict]) -> dict:
        """
        Calculate baseline statistics (Cowork provides structure).
        
        Returns:
        {
            'avg_flap_rate': float,
            'std_flap_rate': float,
            'avg_route_count': float,
            'std_route_count': float,
            ...
        }
        
        Cursor implements: numpy calculations
        """
        pass
    
    def _detect_z_score_anomalies(
        self,
        metrics: List[dict],
        baseline: dict
    ) -> List[dict]:
        """
        Detect statistical anomalies (Cursor implements):
        
        For each metric point:
        - Calculate Z-score = (value - mean) / std
        - If Z-score > threshold (3.0): anomaly
        
        Returns: List of anomaly dicts
        """
        pass
    
    def _detect_ml_anomalies(
        self,
        metrics: List[dict]
    ) -> List[dict]:
        """
        Detect ML-based anomalies (Cursor implements):
        
        1. Prepare feature matrix:
           X = [flap_count, route_count, path_diversity, ...]
        2. Fit Isolation Forest
        3. Predict: -1 = anomaly, 1 = normal
        4. Extract anomalies
        
        Returns: Anomaly dicts
        """
        pass
    
    def _find_correlated_failures(
        self,
        speaker_id: str,
        timestamp: datetime
    ) -> List[str]:
        """
        Find prefixes failing together (Cursor implements):
        
        Indicator: Multiple prefixes withdraw at same time
        = likely link failure impact
        
        Returns: List of affected prefixes
        """
        pass
    
    def _deduplicate(
        self,
        anomalies: List[dict],
        window_seconds: int = 60
    ) -> List[dict]:
        """
        Avoid alert spam (Cursor implements):
        
        Same anomaly type + prefix within window = 1 alert
        
        Returns: Deduplicated anomalies
        """
        pass
```

**Deliverable:** Detector skeleton with algorithm outlines.

---

**3.2 AlertDispatcher Skeleton**

```python
# core/dispatcher.py

class AlertDispatcher:
    """Send notifications for detected anomalies."""
    
    async def dispatch(self, anomaly: Anomaly):
        """
        Dispatch alert (Cursor implements):
        
        1. Fetch alert subscriptions for speaker
        2. Filter by anomaly type + severity
        3. Dedup (don't send same alert twice in 5 min)
        4. Format message
        5. Send via webhook
        6. Retry with exponential backoff (max 3 retries)
        """
        pass
    
    async def _send_webhook(self, url: str, data: dict) -> bool:
        """Send POST to webhook. [CURSOR IMPLEMENTS]"""
        pass
    
    async def _retry_with_backoff(self, url: str, data: dict, attempt: int):
        """Exponential backoff retry. [CURSOR IMPLEMENTS]"""
        pass
    
    def _format_message(self, anomaly: Anomaly) -> dict:
        """Format anomaly as alert JSON. [CURSOR IMPLEMENTS]"""
        pass
```

**Deliverable:** Dispatcher skeleton.

---

**3.3 API Endpoints for Anomalies**

```python
# api/routes/anomalies.py - Cowork provides route stubs

@router.get("/")
async def list_anomalies(
    speaker_id: str = None,
    severity: str = None,
    time_range: str = "24h",
    db: Session = Depends(get_db)
):
    """
    List detected anomalies (Cursor implements):
    - Query Anomaly table
    - Filter by speaker, severity, time
    - Return sorted by timestamp
    """
    pass

@router.post("/{anomaly_id}/acknowledge")
async def acknowledge_anomaly(
    anomaly_id: str,
    db: Session = Depends(get_db),
    user = Depends(get_current_user)
):
    """Mark anomaly as acknowledged."""
    pass

@router.get("/forecast")
async def forecast_anomalies(
    speaker_id: str,
    db: Session = Depends(get_db)
):
    """
    Forecast anomalies (Cursor implements):
    - ARIMA/Prophet on historical metrics
    - Predict flaps/churn for next hour
    """
    pass
```

**Deliverable:** Route stubs.

---

**3.4 Celery Tasks for Detection**

```python
# tasks/telemetry.py - Cowork adds detection tasks

@shared_task
def detect_anomalies_task(speaker_id: str):
    """
    Celery task: Run anomaly detection.
    
    Runs every 5 minutes.
    Cursor implements: Call AnomalyDetector, save results
    """
    pass

@shared_task
def dispatch_alerts_task(anomaly_id: str):
    """
    Celery task: Send alert notifications.
    
    Cursor implements: Call AlertDispatcher
    """
    pass
```

**Deliverable:** Task definitions.

---

#### Cursor Deliverables (Weeks 3-4)

**3.1 AnomalyDetector Full Implementation**

```python
# Implement:
# - detect_anomalies(): Full pipeline
# - _compute_baseline(): Baseline statistics
# - _detect_z_score_anomalies(): Statistical detection
# - _detect_ml_anomalies(): Isolation Forest
# - _find_correlated_failures(): Link failure detection
# - _deduplicate(): Alert spam prevention

# Test targets:
# - pytest tests/unit/test_detector.py::test_detect_z_score
# - pytest tests/unit/test_detector.py::test_detect_isolation_forest
# - pytest tests/unit/test_detector.py::test_correlated_failures
```

**3.2 AlertDispatcher Full Implementation**

```python
# Implement:
# - dispatch(): Fetch subscriptions + send alerts
# - _send_webhook(): POST to webhook URL
# - _retry_with_backoff(): Retry logic
# - _format_message(): JSON formatting

# Test: pytest tests/unit/test_dispatcher.py
```

**3.3 API Endpoints**

```python
# Implement all anomaly endpoints:
# - list_anomalies()
# - acknowledge_anomaly()
# - forecast_anomalies()

# Test: pytest tests/integration/test_anomaly_api.py
```

**3.4 Unit + Integration Tests**

```python
# tests/unit/test_detector.py
def test_detect_z_score_anomalies():
    """Z-score detection on flapping routes."""
    metrics = generate_test_metrics_with_spike()
    detector = AnomalyDetector()
    anomalies = detector._detect_z_score_anomalies(metrics, baseline)
    assert len(anomalies) > 0
    assert anomalies[0]['type'] == 'ROUTE_FLAP'

def test_detect_isolation_forest():
    """ML-based anomaly detection."""
    metrics = generate_test_metrics_with_ml_anomaly()
    detector = AnomalyDetector()
    anomalies = detector._detect_ml_anomalies(metrics)
    assert len(anomalies) > 0

# tests/integration/test_anomaly_detection.py
@pytest.mark.asyncio
async def test_detect_flapping_routes():
    """Detect flapping route anomaly."""
    # Ingest flapping route telemetry
    # Wait for anomaly detection task
    # Verify Anomaly record created
    pass

@pytest.mark.asyncio
async def test_anomaly_webhook_dispatch():
    """Anomaly triggers webhook alert."""
    # Create anomaly
    # Configure webhook subscription
    # Verify POST sent to webhook
    pass
```

**Cursor Checklist (Weeks 3-4):**
- [ ] Z-score detection working (statistical anomalies)
- [ ] Isolation Forest working (ML anomalies)
- [ ] Correlation analysis identifies link failures
- [ ] AlertDispatcher sends webhooks
- [ ] Retry logic working (exponential backoff)
- [ ] Deduplication prevents alert spam
- [ ] All tests passing
- [ ] Coverage 85%+

**Output:** Fully working anomaly detection + alerting.

---

### Phase 4: Dashboard & Analytics (Week 4-5)

**Duration:** 1 week  
**Cowork Output:** Dashboard layout + API client skeleton  
**Cursor Output:** Complete UI + real-time updates

#### Cowork Deliverables

**4.1 Streamlit Dashboard Skeleton**

Similar structure to NetDeploy, but RouteMonitor-specific:

```python
# dashboard/pages/routes.py - Route timeline page
def routes_page():
    """Show route convergence timeline."""
    st.title("Route Timeline")
    
    col1, col2 = st.columns(2)
    with col1:
        speaker_id = st.selectbox("BGP Speaker", [...])
    with col2:
        prefix = st.text_input("Prefix (e.g., 10.0.0.0/8)")
    
    # Cursor: Fetch route events + plot timeline
    # Show: when prefix stabilized, flap count, etc.

# dashboard/pages/anomalies.py - Anomaly timeline
def anomalies_page():
    """Show detected anomalies."""
    st.title("Anomalies")
    
    # Cursor: Display anomaly timeline
    # Show: severity, type, affected prefixes, timestamp
    # Allow: acknowledge anomaly

# dashboard/pages/correlation.py - Correlation analysis
def correlation_page():
    """Show correlated failures."""
    st.title("Correlation Analysis")
    
    # Cursor: Show correlation matrix
    # Which prefixes fail together?
```

**Deliverable:** Dashboard layout.

---

**4.2 API Client**

```python
# dashboard/utils/api_client.py

class RouteMonitorClient:
    """API client for RouteMonitor."""
    
    def list_speakers(self) -> List[dict]:
        """GET /api/telemetry/speakers"""
        pass
    
    def get_route_events(
        self,
        speaker_id: str,
        prefix: str = None
    ) -> List[dict]:
        """GET /api/telemetry/routes"""
        pass
    
    def list_anomalies(
        self,
        speaker_id: str = None,
        time_range: str = "24h"
    ) -> List[dict]:
        """GET /api/anomalies"""
        pass
    
    def get_speaker_metrics(self, speaker_id: str) -> dict:
        """GET /api/metrics/speaker/{id}"""
        pass
    
    def get_correlation(self, prefix1: str, prefix2: str) -> dict:
        """GET /api/correlation"""
        pass
```

**Deliverable:** API client skeleton.

---

#### Cursor Deliverables (Week 4-5)

**4.1 Dashboard Pages**

- Route timeline page (when did prefix stabilize?)
- Device health page (uptime, update rate, errors)
- Anomaly timeline (when did deviations occur?)
- Correlation matrix (which prefixes fail together?)

**4.2 Real-Time Updates**

- WebSocket for live anomaly alerts
- Auto-refresh metrics every 5 seconds
- Streaming route events

**Cursor Checklist (Week 4-5):**
- [ ] All dashboard pages load
- [ ] API client fetches data correctly
- [ ] Route timeline visualization working
- [ ] Anomaly timeline showing real anomalies
- [ ] Correlation matrix calculated + displayed
- [ ] Real-time updates (WebSocket or polling)

**Output:** Working analytics dashboard.

---

### Phase 5: Production Readiness (Week 5-6)

**Duration:** 1 week  
**Cowork Output:** k8s manifests, monitoring setup  
**Cursor Output:** Load testing, security audit

**Deliverables:** Production-grade system.

---

### Phase 6: Portfolio Polish (Weeks 6-8)

**Duration:** 2 weeks  
**Cowork Output:** Documentation, talking points  
**Cursor Output:** Demo, metrics

**Output:** GitHub repo + blog + video.

---

## V. COMPLETE PHASE SUMMARY

| Phase | Week | Duration | Cowork | Cursor | Deliverable |
|-------|------|----------|--------|--------|-------------|
| **1: Foundation** | 1 | 1 week | Scaffold, Docker | Models, mocks | Runnable API |
| **2: Telemetry** | 2-3 | 1.5 weeks | BMP parser skeleton | Full parser impl | Ingestion working |
| **3: Detection** | 3-4 | 1 week | Detector skeleton | ML + alerts impl | Anomaly detection |
| **4: Dashboard** | 4-5 | 1 week | Layout, client | UI + real-time | Analytics dashboard |
| **5: Production** | 5-6 | 1 week | k8s, monitoring | Load test, audit | Production-ready |
| **6: Portfolio** | 6-8 | 2 weeks | Docs | Demo, metrics | GitHub repo + video |

**Total: 6-8 weeks, 100+ hours development**

---

## VI. SUCCESS METRICS

| Metric | Target | Measurement |
|--------|--------|-------------|
| BMP ingestion throughput | 1M updates/min | Celery task rate |
| Anomaly detection accuracy | 95% precision | False positive rate |
| Alert latency | <30 seconds | Time from detection to webhook |
| Dashboard load time | <2 seconds | Time to render metrics |
| Test coverage | 85%+ | pytest --cov |

---

## VII. NEXT STEPS

1. Review this plan
2. Start Cowork Phase 1
3. Run locally + verify Docker
4. Cursor Phase 1: Implement models + mocks
5. Each phase builds on previous

---

## VIII. PORTFOLIO POSITIONING

### GitHub README Hook
> "RouteMonitor: Real-time BGP telemetry platform with ML-powered anomaly detection. Ingest millions of route updates/min, detect routing anomalies (flaps, convergence delays, correlated failures), and alert in <30 seconds."

### Resume Addition
> "Built RouteMonitor, a telemetry collection + analytics platform for routing health. Implements BMP protocol parser, time-series metrics collection (InfluxDB), and ML-based anomaly detection (Isolation Forest). Achieves 95% precision anomaly detection with <30s alert latency."

### Interview Setup
- "Tell me about a data-driven system you've built"
- Answer with RouteMonitor + telemetry context
- Demonstrate: BMP protocol (network), ML anomaly detection, time-series databases, real-time alerting

---

**Ready to build?** Start with Cowork Phase 1. 🚀
