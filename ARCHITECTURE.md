# RouteMonitor — Architecture

## High-Level Data Flow

```
┌──────────────────────────────────────────────────────────────┐
│              NETWORK INFRASTRUCTURE                           │
│  Router 1 (BGP) ──┐                                          │
│  Router 2 (BGP) ──├─ BMP Telemetry (TCP port 9179)          │
│  Router 3 (BGP) ──┘                                          │
└──────────────────────────┬───────────────────────────────────┘
                           │ BMP binary stream (RFC 7854)
                           ▼
┌──────────────────────────────────────────────────────────────┐
│                  ROUTEMONITOR PLATFORM                        │
│                                                              │
│  api/bmp_server.py (asyncio TCP listener)                    │
│  ├── Accept router connections                               │
│  ├── Read BMP messages                                       │
│  └── Enqueue parse_bmp_message_task (Celery)                 │
│                           │                                  │
│                           ▼                                  │
│  Celery Worker (tasks/ingestion.py)                          │
│  ├── parse_bmp_message_task                                  │
│  │     └── BMPParser.parse_message() → JSON                  │
│  │                        │                                  │
│  ├── ingest_metrics_task  │                                  │
│  │   ├── Create RouteEvent record (PostgreSQL)               │
│  │   └── Write metrics point (InfluxDB)                      │
│  │                        │                                  │
│  └── detect_anomalies_task (every 5 min)                     │
│      ├── Z-score check vs 7-day baseline                     │
│      ├── Isolation Forest multivariate detection             │
│      ├── Correlated failure analysis                         │
│      └── dispatch_alerts_task → webhook/Slack/PagerDuty      │
│                                                              │
│  FastAPI (api/main.py)                                       │
│  ├── GET  /api/telemetry/speakers                            │
│  ├── GET  /api/telemetry/route-events                        │
│  ├── GET  /api/anomalies/                                    │
│  ├── POST /api/anomalies/{id}/acknowledge                    │
│  ├── GET  /api/metrics/speaker/{id}                          │
│  ├── GET  /api/metrics/correlation                           │
│  └── POST /api/alerts/webhooks                               │
│                                                              │
│  Dashboard (Streamlit)                                       │
│  ├── Route Timeline (prefix convergence)                     │
│  ├── Device Health (speaker status)                          │
│  ├── Anomaly Timeline                                        │
│  └── Correlation Matrix                                      │
└──────────────────────────────────────────────────────────────┘
```

## Database Schema

### PostgreSQL

```
bgp_speakers
  id UUID PK
  hostname VARCHAR(255) UNIQUE
  router_id VARCHAR(15)       -- IPv4
  local_asn INTEGER
  status VARCHAR(20)          -- CONNECTED / DISCONNECTED / DEGRADED
  last_seen TIMESTAMP
  created_at, updated_at TIMESTAMP

route_events (append-only)
  id UUID PK
  speaker_id UUID FK → bgp_speakers
  timestamp TIMESTAMP         -- UTC, from BMP message
  event_type VARCHAR(20)      -- UPDATE / WITHDRAW / STATE_CHANGE
  prefix VARCHAR(50)          -- CIDR
  path_attributes JSON        -- {as_path, next_hop, origin, local_pref, med}
  withdrawn_prefixes JSON     -- [cidr, ...]
  neighbor_ip VARCHAR(45)
  neighbor_asn INTEGER
  sequence_number INTEGER
  INDEX (speaker_id, timestamp)
  INDEX (prefix, timestamp)

anomalies
  id UUID PK
  speaker_id UUID FK
  prefix VARCHAR(50)
  anomaly_type VARCHAR(50)    -- ROUTE_FLAP / CONVERGENCE_DELAY / CORRELATED_FAILURE / ...
  severity VARCHAR(20)        -- INFO / WARNING / CRITICAL
  detected_at TIMESTAMP
  resolved_at TIMESTAMP NULL
  details JSON                -- {z_score, affected_prefixes, model, ...}
  acknowledged BOOLEAN
  acknowledged_by, acknowledged_at

alerts
  id UUID PK
  anomaly_id UUID FK → anomalies
  alert_type VARCHAR(20)      -- WEBHOOK / SLACK / PAGERDUTY
  target_url VARCHAR(500)
  delivery_status VARCHAR(20) -- PENDING / DELIVERED / FAILED
  retry_count INTEGER
  sent_at TIMESTAMP
```

### InfluxDB 2.0

```
Measurement: route_stats
Tags:
  speaker_id  (UUID string)
  prefix      (CIDR)
  neighbor_ip (IPv4)
  event_type  (UPDATE | WITHDRAW)
Fields:
  route_count       int    -- active routes from speaker
  flap_count        int    -- flaps in last 5-min window
  path_diversity    float  -- unique AS paths for prefix
  convergence_ms    float  -- ms to stable state
  as_path_length    int
  next_hop_count    int

Retention: 7 days raw / 90 days aggregated
```

## Anomaly Detection

### Algorithm 1: Z-Score (Statistical)
```
For each (speaker, prefix) 5-min window:
  z = (current_flap_rate - baseline_mean) / baseline_std
  if z > 3.0: WARNING
  if z > 5.0: CRITICAL
```

### Algorithm 2: Isolation Forest (ML)
```
Feature vector per 5-min window:
  [flap_count, route_count_delta, path_diversity_delta,
   neighbor_churn, convergence_ms]

Training: 7-day historical data
sklearn IsolationForest(contamination=0.05).fit(X)
predict(x_new) == -1 → UNUSUAL_CHURN anomaly
```

### Algorithm 3: Correlation Analysis
```
If N > 10 prefixes withdrawn within 60s window:
  Pearson correlation > 0.8 across time-series
  → CORRELATED_FAILURE (link failure indicator)
  → Includes list of affected_prefixes in details
```

### Algorithm 4: Convergence Detection
```
Cluster UPDATE events for same prefix:
  convergence_time = last_UPDATE.ts - first_UPDATE.ts
  if convergence_time > 60s: CONVERGENCE_DELAY anomaly
```

## Service Ports

| Service | Port | Description |
|---------|------|-------------|
| FastAPI | 8000 | REST API + Swagger |
| BMP Server | 9179 | TCP listener for BMP streams |
| PostgreSQL | 5432 | Relational DB |
| Redis | 6379 | Celery broker + cache |
| InfluxDB | 8086 | Time-series metrics |
| Prometheus | 9090 | Metrics scraping |
| Grafana | 3000 | Dashboards |
