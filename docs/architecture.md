# RouteMonitor Architecture

See the main [README](../README.md) for the full architecture diagram and component list.

## Data Flow

```
BGP Routers (BMP/TCP :9179)
    → BMP Server (asyncio)
    → Celery: parse_bmp_message_task
    → Celery: ingest_metrics_task → PostgreSQL (RouteEvent) + InfluxDB (metrics)
    → Celery: detect_anomalies_task → PostgreSQL (Anomaly)
    → Celery: dispatch_alerts_task → Webhooks / Slack / PagerDuty
    → Streamlit Dashboard (reads FastAPI)
```

## Production Deployment

- **Dev:** `docker-compose.yml` (single uvicorn worker, bind mounts)
- **Prod:** `docker-compose.prod.yml` (4 workers, resource limits, no bind mounts)
- **K8s:** `k8s/` manifests with HPA (2→8 API replicas)

## Monitoring

- Prometheus metrics at `/metrics` (`routemonitor_*` counters)
- Grafana dashboard: `monitoring/grafana/dashboards/routemonitor.json`
