"""InfluxDB 2.0 connector for reading/writing BGP routing metrics.

Uses the official influxdb-client-python library with Flux query language.

Measurement schema:
    measurement: "route_stats"
    tags:
        speaker_id  (str)  — BGPSpeaker UUID
        prefix      (str)  — CIDR prefix, e.g. "10.0.0.0/24"
        neighbor_ip (str)  — peer IP
        event_type  (str)  — UPDATE | WITHDRAW
    fields:
        route_count       (int)   — active routes from this speaker
        flap_count        (int)   — flaps in the last 5-min window
        path_diversity    (float) — unique AS paths seen for this prefix
        convergence_ms    (float) — ms from first UPDATE to stable state
        as_path_length    (int)   — length of best AS path
        next_hop_count    (int)   — number of distinct next hops
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from core.config import settings


class InfluxDBConnector:
    """Reads and writes BGP routing metrics to InfluxDB 2.0.

    Lifecycle:
        connector = InfluxDBConnector(url, token, org, bucket)
        connector.write_metric(point)
        results = connector.query_route_stats(speaker_id, prefix, "7d")
        connector.close()
    """

    def __init__(
        self,
        url: str = settings.INFLUXDB_URL,
        token: str = settings.INFLUXDB_TOKEN,
        org: str = settings.INFLUXDB_ORG,
        bucket: str = settings.INFLUXDB_BUCKET,
    ) -> None:
        """Initialize the InfluxDB client."""
        from influxdb_client import InfluxDBClient
        from influxdb_client.client.write_api import SYNCHRONOUS

        self.url = url
        self.token = token
        self.org = org
        self.bucket = bucket
        self.client = InfluxDBClient(url=url, token=token, org=org)
        self.write_api = self.client.write_api(write_options=SYNCHRONOUS)
        self.query_api = self.client.query_api()

    # ── Write ─────────────────────────────────────────────────────────────────

    def write_metric(self, point_dict: Dict[str, Any]) -> None:
        """Write a single metrics point to InfluxDB.

        Args:
            point_dict: {
                "measurement": "route_stats",
                "tags": {"speaker_id": str, "prefix": str, ...},
                "fields": {"flap_count": int, "route_count": int, ...},
                "time": datetime | None   (None = use current time)
            }

        """
        from influxdb_client import Point

        p = Point(point_dict["measurement"])
        if point_dict.get("time") is not None:
            p = p.time(point_dict["time"])
        for key, value in point_dict.get("tags", {}).items():
            p = p.tag(key, str(value))
        for key, value in point_dict.get("fields", {}).items():
            p = p.field(key, value)
        self.write_api.write(bucket=self.bucket, org=self.org, record=p)

    def write_metrics_batch(self, points: List[Dict[str, Any]]) -> None:
        """Write multiple metric points in a single batch."""
        if not points:
            return
        from influxdb_client import Point

        records = []
        for point_dict in points:
            p = Point(point_dict["measurement"])
            if point_dict.get("time") is not None:
                p = p.time(point_dict["time"])
            for key, value in point_dict.get("tags", {}).items():
                p = p.tag(key, str(value))
            for key, value in point_dict.get("fields", {}).items():
                p = p.field(key, value)
            records.append(p)
        self.write_api.write(bucket=self.bucket, org=self.org, record=records)

    # ── Query ─────────────────────────────────────────────────────────────────

    def query_route_stats(
        self,
        speaker_id: str,
        prefix: Optional[str] = None,
        time_range: str = "7d",
    ) -> List[Dict[str, Any]]:
        """Query route statistics for a speaker over a time window.

        Args:
            speaker_id: UUID of the BGP speaker
            prefix: Optional CIDR filter (e.g. "10.0.0.0/24")
            time_range: Flux duration string — "1h", "24h", "7d"

        Returns:
            List of dicts: [{time, flap_count, route_count, path_diversity, ...}]

        Flux query template:
            from(bucket: "{self.bucket}")
              |> range(start: -{time_range})
              |> filter(fn: (r) => r._measurement == "route_stats")
              |> filter(fn: (r) => r.speaker_id == "{speaker_id}")
              [|> filter(fn: (r) => r.prefix == "{prefix}")]
              |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
              |> sort(columns: ["_time"], desc: true)

        [CURSOR TO IMPLEMENT - Phase 2]
        """
        flux = f"""
from(bucket: "{self.bucket}")
  |> range(start: -{time_range})
  |> filter(fn: (r) => r._measurement == "route_stats")
  |> filter(fn: (r) => r.speaker_id == "{speaker_id}")
"""
        if prefix:
            flux += f'  |> filter(fn: (r) => r.prefix == "{prefix}")\n'
        flux += (
            "  |> toFloat()\n"
            '  |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")\n'
            '  |> sort(columns: ["_time"], desc: true)'
        )

        tables = self.query_api.query(flux, org=self.org)
        results: List[Dict[str, Any]] = []
        for table in tables:
            for record in table.records:
                results.append(
                    {
                        "time": record.get_time().isoformat(),
                        "flap_count": record.values.get("flap_count", 0),
                        "route_count": record.values.get("route_count", 0),
                        "path_diversity": record.values.get("path_diversity", 0.0),
                        "convergence_ms": record.values.get("convergence_ms", 0.0),
                    }
                )
        return results

    def query_anomaly_timeline(
        self,
        speaker_id: Optional[str] = None,
        time_range: str = "24h",
    ) -> List[Dict[str, Any]]:
        """Query time-bucketed flap counts for dashboard charting."""
        flux = f"""
from(bucket: "{self.bucket}")
  |> range(start: -{time_range})
  |> filter(fn: (r) => r._measurement == "route_stats")
"""
        if speaker_id:
            flux += f'  |> filter(fn: (r) => r.speaker_id == "{speaker_id}")\n'
        flux += """
  |> filter(fn: (r) => r._field == "flap_count")
  |> aggregateWindow(every: 1h, fn: sum, createEmpty: false)
  |> sort(columns: ["_time"], desc: false)
"""
        tables = self.query_api.query(flux, org=self.org)
        results: List[Dict[str, Any]] = []
        for table in tables:
            for record in table.records:
                results.append(
                    {
                        "time": record.get_time().isoformat(),
                        "flap_count": record.get_value(),
                    }
                )
        return results

    def query_correlation_matrix(
        self,
        time_range: str = "7d",
        top_n_prefixes: int = 50,
    ) -> Dict[str, Dict[str, float]]:
        """Compute pairwise prefix failure correlation."""
        import pandas as pd

        flux = f"""
from(bucket: "{self.bucket}")
  |> range(start: -{time_range})
  |> filter(fn: (r) => r._measurement == "route_stats")
  |> filter(fn: (r) => r._field == "flap_count")
  |> filter(fn: (r) => exists r.prefix)
  |> toFloat()
"""
        tables = self.query_api.query(flux, org=self.org)
        rows: Dict[str, Dict[str, float]] = {}

        for table in tables:
            for record in table.records:
                prefix = record.values.get("prefix")
                if not prefix:
                    continue
                t = record.get_time().isoformat()
                if t not in rows:
                    rows[t] = {}
                rows[t][str(prefix)] = float(record.get_value())

        if not rows:
            return {}

        df = pd.DataFrame.from_dict(rows, orient="index").fillna(0)
        if len(df.columns) > top_n_prefixes:
            top = df.sum().nlargest(top_n_prefixes).index
            df = df[top]

        return df.corr(method="pearson").fillna(0).to_dict()

    def query_flap_baseline(
        self,
        speaker_id: str,
        days: int = 7,
    ) -> Dict[str, float]:
        """Compute baseline flap statistics for anomaly detection.

        Returns:
            {
                "mean_flap_rate": float,
                "std_flap_rate": float,
                "mean_route_count": float,
                "std_route_count": float,
                "p95_flap_rate": float,
            }

        [CURSOR TO IMPLEMENT - Phase 3]
        """
        import numpy as np

        time_range = f"{days}d"
        flux = f"""
from(bucket: "{self.bucket}")
  |> range(start: -{time_range})
  |> filter(fn: (r) => r._measurement == "route_stats")
  |> filter(fn: (r) => r.speaker_id == "{speaker_id}")
  |> filter(fn: (r) => r._field == "flap_count" or r._field == "route_count")
  |> toFloat()
  |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
"""
        tables = self.query_api.query(flux, org=self.org)
        flap_counts: List[float] = []
        route_counts: List[float] = []
        for table in tables:
            for record in table.records:
                if record.values.get("flap_count") is not None:
                    flap_counts.append(float(record.values["flap_count"]))
                if record.values.get("route_count") is not None:
                    route_counts.append(float(record.values["route_count"]))

        if not flap_counts:
            return {
                "mean_flap_rate": 0.0,
                "std_flap_rate": 0.0,
                "mean_route_count": 0.0,
                "std_route_count": 0.0,
                "p95_flap_rate": 0.0,
            }

        flap_arr = np.array(flap_counts)
        route_arr = np.array(route_counts) if route_counts else np.array([0.0])
        return {
            "mean_flap_rate": float(np.mean(flap_arr)),
            "std_flap_rate": float(np.std(flap_arr)),
            "mean_route_count": float(np.mean(route_arr)),
            "std_route_count": float(np.std(route_arr)),
            "p95_flap_rate": float(np.percentile(flap_arr, 95)),
        }

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def close(self) -> None:
        """Close the InfluxDB connection."""
        if self.client:
            self.client.close()
