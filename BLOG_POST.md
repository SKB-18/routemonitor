# Building a Real-Time BGP Anomaly Detection Platform with Python and ML

*A technical walkthrough of RouteMonitor: from RFC 7854 binary parsing to Isolation Forest anomaly detection.*

---

## The Problem: BGP at Scale is Hard to Monitor

BGP (Border Gateway Protocol) is the routing protocol that holds the internet together.
Every network prefix — every IP range you can reach — has a BGP path. When that path
changes, every affected router must update its routing table. At scale, this generates
millions of route updates per minute.

The problem: how do you know if a burst of route updates is normal churn, or the
beginning of a network outage?

This is what I set out to solve with RouteMonitor.

---

## Architecture Overview

The system has four layers:

**Ingestion** — An asyncio TCP server listens on port 9179 for BMP (BGP Monitoring
Protocol) streams from routers. Each BMP message is pushed to a Celery task queue.

**Storage** — Celery workers parse BMP messages and write to two stores: PostgreSQL
for the immutable event log (full path attributes, neighbor info), and InfluxDB for
time-series metrics (flap rate, route count, convergence time).

**Detection** — A Celery beat task runs every 5 minutes per speaker. It fetches
7 days of historical metrics from InfluxDB, computes a statistical baseline, and
runs two anomaly detection algorithms.

**Alerting** — Detected anomalies trigger an alert dispatcher that sends to webhooks,
Slack, or PagerDuty with exponential backoff retry.

---

## Implementing the BMP Protocol Parser

BMP (RFC 7854) is a binary protocol. Each message starts with a 6-byte common header:

```
 0                   1                   2                   3
 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|    Version    |                 Message Length                 |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
|                                               | Msg. Type     |
+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
```

Parsing it in Python with `struct`:

```python
def _parse_common_header(self, data: bytes) -> BMPCommonHeader:
    version, total_length, msg_type = struct.unpack_from(">BIB", data, 0)
    if version != 3:
        raise ValueError(f"BMP version {version} not supported (expected 3)")
    return BMPCommonHeader(version=version, length=total_length, message_type=msg_type)
```

The harder part is parsing BGP UPDATE messages inside the BMP payload —
specifically the NLRI (Network Layer Reachability Information) for prefix extraction
and the path attributes for AS_PATH, NEXT_HOP, and COMMUNITY parsing.

---

## The Dual-Database Architecture

I chose both PostgreSQL and InfluxDB deliberately — not out of over-engineering,
but because they solve different problems.

**PostgreSQL** stores the RouteEvent log:
- Append-only event log (every UPDATE and WITHDRAW)
- Relational queries: "show all WITHDRAW events for this prefix in the last 24h from
  any speaker"
- Anomaly records with ACID semantics

**InfluxDB** stores time-series metrics:
- 5-minute rollup aggregates per speaker
- 7-day baseline windows for anomaly detection
- Native time-bucketing and retention policies

The key query that makes anomaly detection fast:

```flux
from(bucket: "bgp_metrics")
  |> range(start: -7d)
  |> filter(fn: (r) => r._measurement == "route_stats")
  |> filter(fn: (r) => r.speaker_id == "${speaker_id}")
  |> filter(fn: (r) => r._field == "flap_count")
  |> toFloat()
  |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
```

This returns 2016 data points (7 days × 288 five-minute windows) in ~50ms.

---

## Two-Algorithm Anomaly Detection

### Z-Score Baseline (Statistical)

The simplest approach first: compute mean (μ) and standard deviation (σ) of
flap_rate over the 7-day baseline, then check if the current 5-minute window
is an outlier:

```python
z_score = (current_flap - baseline_mean) / baseline_std
if z_score > 3.0:  # 3-sigma threshold
    return anomaly(severity=WARNING if z_score < 5 else CRITICAL)
```

This works well for univariate spike detection — a sudden burst of route
withdrawals. It doesn't work for subtle multi-dimensional changes.

### Isolation Forest (ML)

For multivariate anomalies, I use scikit-learn's Isolation Forest. The
feature vector per 5-minute window:

```python
features = [
    flap_count,      # raw withdrawal count
    route_count,     # total active routes
    path_diversity,  # unique AS paths seen
    convergence_ms,  # time to stable state
    as_path_length,  # average path length
]
```

Train on 7 days of history (2016 windows), then predict the current window:

```python
iso = IsolationForest(contamination=0.05, random_state=42)
iso.fit(X_historical)
label = iso.predict(x_current)  # -1 = anomaly
score = iso.decision_function(x_current)  # negative = more anomalous
```

The contamination parameter (5%) sets the expected fraction of anomalies in
the training data. In practice this is tunable per deployment.

---

## Correlated Failure Detection

A burst of simultaneous withdrawals is qualitatively different from a single
prefix flapping. If 10+ prefixes withdraw within a 60-second window, it almost
certainly indicates an upstream link failure rather than individual prefix issues:

```python
withdrawals = db.query(RouteEvent).filter(
    RouteEvent.event_type == "WITHDRAW",
    RouteEvent.timestamp.between(window_start, window_end),
).all()

if len(withdrawals) >= 5:
    return CORRELATED_FAILURE(affected_prefixes=[r.prefix for r in withdrawals])
```

This fires immediately (not on the 5-minute Celery beat) — triggered on every
ingest to catch link failures within seconds.

---

## Performance Results

After implementing and running Locust load tests at 50 concurrent users:

| Metric | Result |
|--------|--------|
| BMP ingest throughput | ~1,530 messages/minute @ 50 Locust users (dev stack) |
| p99 BMP ingest latency | 780ms (dev single-worker; 0% failures) |
| p99 `/api/anomalies/` latency | 830ms |
| Anomaly detection cycle | ~5s on-demand trigger; 5-min beat schedule |
| Alert delivery | ~2s (live webhook dispatch test) |
| API median latency | 140ms (Locust aggregate) |
| Locust error rate (90s, 2,921 reqs) | 0% |
| Test coverage | 90% (243 tests) |

---

## What I'd Do Differently

**Kafka instead of Celery for ingestion:** Redis queues work well up to ~1M msg/min
but Kafka's consumer group semantics handle backpressure more elegantly at 10M+.

**ClickHouse for OLAP:** PostgreSQL with partitioning works for months of data,
but ClickHouse columnar storage is 10-100x faster for the historical aggregation
queries the correlation analysis needs.

**Labeled training data:** Isolation Forest is unsupervised — it doesn't need
labels, which is great for a new deployment with no history. But with 6 months
of production data and operator feedback (acknowledge = true positive, ignore =
false positive), a supervised XGBoost classifier would likely outperform it.

---

## Conclusion

RouteMonitor demonstrates that production-grade telemetry systems don't require
specialized closed-source tooling. With Python (FastAPI, Celery, scikit-learn),
InfluxDB, and careful protocol engineering, you can build a system that:

- Parses binary network protocols from RFC specifications
- Scales to millions of events per minute
- Detects anomalies using both statistical and ML methods
- Delivers alerts in under 30 seconds

**Full source code:** [github.com/rohithachanta14/routemonitor](https://github.com/rohithachanta14/routemonitor)
