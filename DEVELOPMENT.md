# Development Guide

## Prerequisites

- Docker Desktop (for docker compose)
- Python 3.11+
- `git`

## Phase-by-Phase Workflow

This project uses a **Cowork → Cursor** workflow for each phase:

1. **Cowork** provides the scaffold (structure, docstrings, type signatures)
2. **Cursor** implements all the `[CURSOR TO IMPLEMENT]` sections
3. Test locally with `docker compose + pytest`
4. Commit to GitHub

---

## Phase 1: Foundation (Current)

### Cowork already delivered:
- Complete directory structure
- `api/models.py` — full SQLAlchemy models with indexes
- `api/schemas.py` — full Pydantic schemas with validators
- `api/main.py` — FastAPI app with all routers
- `core/bmp_parser.py` — skeleton with RFC 7854 comments
- `core/detector.py` — skeleton with algorithm outlines
- `core/dispatcher.py` — skeleton with retry logic outline
- `core/influxdb_connector.py` — skeleton with Flux query outlines
- `tasks/celery_app.py` — Celery initialization + beat schedule
- `tasks/ingestion.py` — all task stubs
- `tests/conftest.py` — all pytest fixtures
- `tests/fixtures/bgp_telemetry_generator.py` — mock BMP generator
- `dashboard/` — Streamlit app skeleton
- `docker-compose.yml` — all 8 services
- `.github/workflows/` — CI/CD

### Cursor must implement (Phase 1):

1. **Run Alembic migrations**
   ```bash
   docker compose up db
   docker compose exec api alembic init alembic
   docker compose exec api alembic revision --autogenerate -m "initial"
   docker compose exec api alembic upgrade head
   ```

2. **Implement InfluxDB connector** (`core/influxdb_connector.py`)
   - `__init__`: Initialize `InfluxDBClient`, `write_api`, `query_api`
   - `write_metric()`: Build `Point`, call `write_api.write()`
   - `close()`: Close the client

3. **Health check** (`api/routes/health.py`)
   - Query `db.execute("SELECT 1")`
   - Ping Redis with `celery.control.ping()`
   - Ping InfluxDB with `GET /health`

4. **Implement BMP telemetry generator** (`tests/fixtures/bgp_telemetry_generator.py`)
   - `generate_update()`: Build valid BMP Route Monitoring bytes
   - `generate_withdraw()`: Build valid BMP Withdraw bytes

5. **Test schemas** (`tests/unit/test_schemas.py`)
   - Fill in all `pass` stubs with actual assertions

6. **Docker build + smoke test**:
   ```bash
   docker compose build
   docker compose up
   curl http://localhost:8000/health
   curl http://localhost:8000/docs
   docker compose exec api pytest tests/unit/test_schemas.py -v
   ```

### Phase 1 checklist:
- [ ] `docker compose up` — all 7 services healthy
- [ ] `curl http://localhost:8000/health` → `{"status": "healthy"}`
- [ ] `curl http://localhost:8000/docs` → Swagger UI loads
- [ ] `pytest tests/unit/test_schemas.py` — all pass
- [ ] `python -c "from api.models import *; from core.bmp_parser import *"` — no errors
- [ ] Alembic migrations applied (4 tables exist in PostgreSQL)

---

## Phase 2: BMP Parser + Telemetry (Weeks 2-3)

Cursor implements:
- `core/bmp_parser.py` — all `[CURSOR TO IMPLEMENT]` methods
- `core/influxdb_connector.py` — `write_metric`, `query_route_stats`
- `api/routes/telemetry.py` — all endpoint implementations
- `tasks/ingestion.py` — `parse_bmp_message_task`, `ingest_metrics_task`

Test targets: `pytest tests/unit/test_bmp_parser.py -v`

---

## Phase 3: Anomaly Detection (Weeks 3-4)

Cursor implements:
- `core/detector.py` — all anomaly detection methods
- `core/dispatcher.py` — webhook dispatch + retry
- `api/routes/anomalies.py` — all endpoints
- `tasks/ingestion.py` — `detect_anomalies_task`, `dispatch_alerts_task`

Test targets: `pytest tests/unit/test_anomaly_detector.py -v`

---

## Phase 4: Dashboard (Weeks 4-5)

Cursor implements:
- `dashboard/utils/api_client.py` — all HTTP methods
- `dashboard/pages/*.py` — all Streamlit pages with Plotly charts

Run: `streamlit run dashboard/app.py`

---

## Running Tests

```bash
# Unit tests only (no Docker needed)
pytest tests/unit/ -v

# All tests (requires docker compose up)
pytest tests/ -v

# With coverage
pytest tests/ --cov=api --cov=core --cov-report=term-missing

# Specific test file
pytest tests/unit/test_bmp_parser.py -v -k "test_parse_valid"
```

## Code Style

```bash
# Format
black .
isort .

# Lint
flake8 api/ core/ tasks/ --max-line-length=100

# Types
mypy api/ core/ tasks/ --ignore-missing-imports
```

## Environment Variables

Copy `.env.example` to `.env` and edit:

```bash
cp .env.example .env
```

Key variables:
- `DATABASE_URL` — PostgreSQL connection string
- `REDIS_URL` — Redis URL
- `INFLUXDB_TOKEN` — InfluxDB admin token (set in docker-compose)
- `INFLUXDB_ORG` — InfluxDB org (default: `myorg`)
- `INFLUXDB_BUCKET` — InfluxDB bucket (default: `bgp_metrics`)
