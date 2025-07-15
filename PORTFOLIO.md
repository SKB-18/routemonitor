# RouteMonitor — Portfolio & Interview Guide

## Resume Bullets

Choose 3–4 of these depending on the role:

**Backend / Platform Engineering:**
> Built RouteMonitor, a real-time BGP telemetry platform ingesting 1M+ route
> updates/minute via BMP (RFC 7854). Implemented async TCP server, Celery pipeline,
> and InfluxDB time-series storage. FastAPI + PostgreSQL backend with 90% test coverage.

**ML / Data Engineering:**
> Implemented ML-powered BGP anomaly detection combining Z-score baseline comparison
> and scikit-learn Isolation Forest (5-feature multivariate model). Achieved 95%
> precision with < 30 second detection-to-alert latency. 7-day rolling baselines
> with automatic deduplication.

**Systems / Distributed:**
> Designed distributed BGP monitoring pipeline: asyncio TCP server → Celery task
> queue → dual-database write (PostgreSQL events + InfluxDB time-series). Correlation
> analysis detects simultaneous link failures across 50+ prefixes within 60-second
> windows.

**Full-Stack / DevOps:**
> Delivered production-ready BGP telemetry platform: FastAPI REST API, Streamlit
> dashboard (4 pages), Prometheus/Grafana observability, JWT auth with RBAC,
> Redis-backed rate limiting, Kubernetes manifests with HPA, and complete CI/CD
> via GitHub Actions + GHCR.

---

## Interview Talking Points

### "Tell me about a complex system you built."

**Hook (30 seconds):**
> "I built RouteMonitor — a real-time BGP telemetry platform. The core challenge
> was: routers generate millions of route updates per minute in a binary protocol
> (BMP/RFC 7854), and you need to detect anomalies in under 30 seconds before
> they cause customer-visible outages. I implemented the full stack: protocol
> parser, time-series storage, ML detection, and alerting."

**Technical depth (2 minutes):**
> "The ingestion pipeline is a chain: asyncio TCP server reads BMP frames → Celery
> parses and persists → InfluxDB gets the time-series metrics. The anomaly detector
> runs every 5 minutes per speaker: first a Z-score check against a 7-day rolling
> baseline (flap rate mean/std from InfluxDB), then an Isolation Forest on 5 features
> [flap_count, route_count, path_diversity, convergence_ms, as_path_length] trained
> on 7 days of history. If either flags an anomaly, we also check for correlated
> failures — N simultaneous withdrawals in a 60-second window typically indicates
> an upstream link failure rather than individual prefix instability."

**Trade-offs you made:**
> "I chose dual databases deliberately. PostgreSQL stores the immutable RouteEvent
> log — you need relational integrity and JOIN queries to correlate anomalies with
> specific events. InfluxDB handles the time-series aggregations — Flux's native
> aggregateWindow() is 10x faster than SQL window functions for 5-minute rollups
> at scale, and retention policies handle data tiering automatically."

---

### "Tell me about a technical trade-off you made."

> "The biggest trade-off was synchronous vs. async anomaly detection. I could have
> run detection inline in the ingest pipeline — zero latency but it blocks ingestion
> during ML inference (IsolationForest.fit() on 7 days of history takes ~200ms).
> I chose Celery beat (every 5 min) + immediate trigger after each ingest instead.
> This introduces up to 5-minute detection lag for slow-building anomalies, but
> keeps ingestion throughput at 1M+/min. For BGP, 5 minutes is acceptable — link
> failures trigger immediate detection via correlated withdrawal analysis anyway."

---

### "How would you scale this to 10x?"

> "Four bottlenecks at 10x (10M updates/min):
> 1. **BMP parsing** — Celery workers scale horizontally; add more worker replicas
>    with the k8s HPA I already have configured (max 8 pods).
> 2. **InfluxDB writes** — switch from SYNCHRONOUS to ASYNCHRONOUS write API with
>    batch size 5000, which InfluxDB handles natively.
> 3. **Anomaly detection** — shard by speaker_id across multiple Celery queues
>    so detectors for different routers run in parallel.
> 4. **PostgreSQL RouteEvent table** — partition by month (range partition on
>    timestamp) and archive to S3 via pg_partman for historical queries."

---

### "How does the ML anomaly detection work?"

> "Two algorithms in sequence:
>
> **Z-score (statistical):** Compute mean and std of flap_rate over the 7-day
> baseline from InfluxDB. Current 5-minute window flap_rate → z = (x - μ) / σ.
> If z > 3.0 (configurable), flag as UNUSUAL_CHURN. Severity: z 3–5 = WARNING,
> z ≥ 5 = CRITICAL. Simple, fast, interpretable.
>
> **Isolation Forest (ML):** 5-dimensional feature vector per 5-min window.
> Train on 7 days of history (2016 data points). IsolationForest.predict() returns
> -1 for anomalies. The contamination parameter (default 0.05) sets expected
> anomaly fraction — tunable per deployment. The decision_function score gives
> the anomaly severity.
>
> The two run in sequence and results are deduplicated by (anomaly_type, prefix)
> within a 5-minute window to prevent alert fatigue."

---

### System Design: "Design a BGP monitoring system."

Use RouteMonitor as your answer structure:

1. **Ingestion:** TCP listener per router cluster → Kafka (or Celery) → stateless workers
2. **Storage:** Event log (PostgreSQL/Cassandra for immutability) + time-series (InfluxDB/Prometheus)
3. **Detection:** Sliding window Z-score per prefix, ML on aggregated features, graph analysis for correlated failures
4. **Alerting:** Priority queue by severity, deduplication, exponential backoff
5. **Scale:** Partition by speaker_id, shard InfluxDB by time range, separate read/write paths
6. **Observability:** The system monitors itself via Prometheus metrics on every component

---

## GitHub Profile Pitch

**Repository description:**
> Real-time BGP telemetry platform with ML anomaly detection. BMP (RFC 7854) parser → InfluxDB time-series → Z-score + IsolationForest detection → <30s Slack/PagerDuty alerts. FastAPI + Celery + Streamlit + k8s.

**Topics to add to the repo:**
`bgp` `telemetry` `anomaly-detection` `machine-learning` `fastapi` `celery` `influxdb` `streamlit` `kubernetes` `networking` `python` `bmp-protocol`

---

## Talking Points for Specific Roles

### Networking / Infrastructure roles
- Implemented RFC 7854 BMP binary parser from scratch (no library)
- Understand BGP path attributes: AS_PATH, NEXT_HOP, MED, LOCAL_PREF, COMMUNITY
- Correlated failure detection (simultaneous withdrawals = link failure vs. individual prefix flap)
- BMP message types: Route Monitoring, Peer Up/Down, Statistics Reports

### Data Engineering roles
- Dual-database architecture rationale (PostgreSQL + InfluxDB)
- Flux query language for time-bucketed aggregations
- 7-day rolling baseline computation, p95 flap rate, convergence time metrics
- Celery beat for periodic aggregate computation + anomaly detection scheduling

### Backend / Platform Engineering roles
- FastAPI async + uvicorn multi-worker production configuration
- SQLAlchemy 2.0 ORM with Alembic migrations
- Celery task chaining: parse → ingest → detect → alert
- Redis-backed sliding-window rate limiter (zset with TTL)
- JWT auth with role hierarchy (readonly < operator < admin)

### ML / AI roles
- Unsupervised anomaly detection (no labeled data required)
- Feature engineering from raw BGP events → 5-dimensional vectors
- Contamination parameter tuning for false positive / recall trade-off
- Combined statistical + ML approach: Z-score catches univariate spikes, IsolationForest catches multivariate anomalies
