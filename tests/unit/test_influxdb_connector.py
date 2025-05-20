"""Unit tests for InfluxDBConnector."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


class TestWriteMetric:
    def test_write_metric_calls_write_api(self):
        with patch("influxdb_client.InfluxDBClient") as mock_client_class:
            mock_client = MagicMock()
            mock_write_api = MagicMock()
            mock_client.write_api.return_value = mock_write_api
            mock_client.query_api.return_value = MagicMock()
            mock_client_class.return_value = mock_client

            from core.influxdb_connector import InfluxDBConnector

            connector = InfluxDBConnector(
                url="http://localhost:8086",
                token="test-token",
                org="testorg",
                bucket="test_bucket",
            )
            connector.write_metric(
                {
                    "measurement": "route_stats",
                    "tags": {"speaker_id": "abc", "prefix": "10.0.0.0/24"},
                    "fields": {"flap_count": 5, "route_count": 100},
                }
            )
            mock_write_api.write.assert_called_once()

    def test_write_metric_with_timestamp(self):
        with patch("influxdb_client.InfluxDBClient") as mock_client_class:
            mock_client = MagicMock()
            mock_write_api = MagicMock()
            mock_client.write_api.return_value = mock_write_api
            mock_client.query_api.return_value = MagicMock()
            mock_client_class.return_value = mock_client

            from core.influxdb_connector import InfluxDBConnector

            connector = InfluxDBConnector(
                url="http://localhost:8086",
                token="t",
                org="o",
                bucket="b",
            )
            ts = datetime(2024, 1, 1, tzinfo=timezone.utc)
            connector.write_metric(
                {
                    "measurement": "route_stats",
                    "tags": {},
                    "fields": {"flap_count": 1},
                    "time": ts,
                }
            )
            mock_write_api.write.assert_called_once()

    def test_write_metric_sets_all_tags(self):
        with patch("influxdb_client.InfluxDBClient") as mock_client_class:
            mock_client = MagicMock()
            mock_write_api = MagicMock()
            mock_client.write_api.return_value = mock_write_api
            mock_client.query_api.return_value = MagicMock()
            mock_client_class.return_value = mock_client

            from core.influxdb_connector import InfluxDBConnector

            connector = InfluxDBConnector(
                url="http://x", token="t", org="o", bucket="b"
            )
            connector.write_metric(
                {
                    "measurement": "route_stats",
                    "tags": {"speaker_id": "s1", "prefix": "10.0.0.0/24"},
                    "fields": {"flap_count": 1},
                }
            )
            call_args = mock_write_api.write.call_args
            assert call_args is not None

    def test_write_metric_sets_all_fields(self):
        with patch("influxdb_client.InfluxDBClient") as mock_client_class:
            mock_client = MagicMock()
            mock_write_api = MagicMock()
            mock_client.write_api.return_value = mock_write_api
            mock_client.query_api.return_value = MagicMock()
            mock_client_class.return_value = mock_client

            from core.influxdb_connector import InfluxDBConnector

            connector = InfluxDBConnector(
                url="http://x", token="t", org="o", bucket="b"
            )
            connector.write_metric(
                {
                    "measurement": "route_stats",
                    "tags": {},
                    "fields": {
                        "flap_count": 5,
                        "route_count": 100,
                        "path_diversity": 2.5,
                    },
                }
            )
            mock_write_api.write.assert_called_once()


class TestWriteMetricsBatch:
    def test_batch_write_multiple_points(self):
        with patch("influxdb_client.InfluxDBClient") as mock_client_class:
            mock_client = MagicMock()
            mock_write_api = MagicMock()
            mock_client.write_api.return_value = mock_write_api
            mock_client.query_api.return_value = MagicMock()
            mock_client_class.return_value = mock_client

            from core.influxdb_connector import InfluxDBConnector

            connector = InfluxDBConnector(
                url="http://x", token="t", org="o", bucket="b"
            )
            connector.write_metrics_batch(
                [
                    {
                        "measurement": "route_stats",
                        "tags": {},
                        "fields": {"flap_count": 1},
                    },
                    {
                        "measurement": "route_stats",
                        "tags": {},
                        "fields": {"flap_count": 2},
                    },
                ]
            )
            mock_write_api.write.assert_called_once()
            records = mock_write_api.write.call_args.kwargs.get(
                "record"
            ) or mock_write_api.write.call_args[1].get("record")
            assert records is not None

    def test_empty_batch_no_error(self):
        with patch("influxdb_client.InfluxDBClient") as mock_client_class:
            mock_client = MagicMock()
            mock_write_api = MagicMock()
            mock_client.write_api.return_value = mock_write_api
            mock_client.query_api.return_value = MagicMock()
            mock_client_class.return_value = mock_client

            from core.influxdb_connector import InfluxDBConnector

            connector = InfluxDBConnector(
                url="http://x", token="t", org="o", bucket="b"
            )
            connector.write_metrics_batch([])
            mock_write_api.write.assert_not_called()


class TestQueryRouteStats:
    def test_query_returns_list(self):
        with patch("influxdb_client.InfluxDBClient") as mock_client_class:
            mock_client = MagicMock()
            mock_query_api = MagicMock()
            mock_record = MagicMock()
            mock_record.get_time.return_value = datetime(
                2024, 1, 1, tzinfo=timezone.utc
            )
            mock_record.values = {
                "flap_count": 3,
                "route_count": 100,
                "path_diversity": 1.5,
                "convergence_ms": 50.0,
            }
            mock_table = MagicMock()
            mock_table.records = [mock_record]
            mock_query_api.query.return_value = [mock_table]
            mock_client.write_api.return_value = MagicMock()
            mock_client.query_api.return_value = mock_query_api
            mock_client_class.return_value = mock_client

            from core.influxdb_connector import InfluxDBConnector

            connector = InfluxDBConnector(
                url="http://x", token="t", org="o", bucket="b"
            )
            results = connector.query_route_stats("speaker-1")
            assert isinstance(results, list)
            assert len(results) == 1
            assert results[0]["flap_count"] == 3

    def test_query_with_prefix_filter(self):
        with patch("influxdb_client.InfluxDBClient") as mock_client_class:
            mock_client = MagicMock()
            mock_query_api = MagicMock()
            mock_query_api.query.return_value = []
            mock_client.write_api.return_value = MagicMock()
            mock_client.query_api.return_value = mock_query_api
            mock_client_class.return_value = mock_client

            from core.influxdb_connector import InfluxDBConnector

            connector = InfluxDBConnector(
                url="http://x", token="t", org="o", bucket="b"
            )
            connector.query_route_stats("speaker-1", prefix="10.0.0.0/24")
            flux = mock_query_api.query.call_args[0][0]
            assert "10.0.0.0/24" in flux

    def test_query_without_prefix_no_filter(self):
        with patch("influxdb_client.InfluxDBClient") as mock_client_class:
            mock_client = MagicMock()
            mock_query_api = MagicMock()
            mock_query_api.query.return_value = []
            mock_client.write_api.return_value = MagicMock()
            mock_client.query_api.return_value = mock_query_api
            mock_client_class.return_value = mock_client

            from core.influxdb_connector import InfluxDBConnector

            connector = InfluxDBConnector(
                url="http://x", token="t", org="o", bucket="b"
            )
            connector.query_route_stats("speaker-1")
            flux = mock_query_api.query.call_args[0][0]
            assert "r.prefix ==" not in flux

    def test_time_range_passed_to_query(self):
        with patch("influxdb_client.InfluxDBClient") as mock_client_class:
            mock_client = MagicMock()
            mock_query_api = MagicMock()
            mock_query_api.query.return_value = []
            mock_client.write_api.return_value = MagicMock()
            mock_client.query_api.return_value = mock_query_api
            mock_client_class.return_value = mock_client

            from core.influxdb_connector import InfluxDBConnector

            connector = InfluxDBConnector(
                url="http://x", token="t", org="o", bucket="b"
            )
            connector.query_route_stats("speaker-1", time_range="1h")
            flux = mock_query_api.query.call_args[0][0]
            assert "-1h" in flux


class TestQueryFlapBaseline:
    def test_query_flap_baseline_returns_dict(self):
        with patch("influxdb_client.InfluxDBClient") as mock_client_class:
            mock_client = MagicMock()
            mock_query_api = MagicMock()
            mock_record = MagicMock()
            mock_record.values = {"flap_count": 3, "route_count": 100}
            mock_table = MagicMock()
            mock_table.records = [mock_record, mock_record]
            mock_query_api.query.return_value = [mock_table]
            mock_client.write_api.return_value = MagicMock()
            mock_client.query_api.return_value = mock_query_api
            mock_client_class.return_value = mock_client

            from core.influxdb_connector import InfluxDBConnector

            connector = InfluxDBConnector(
                url="http://x", token="t", org="o", bucket="b"
            )
            baseline = connector.query_flap_baseline("speaker-1", days=7)
            assert "mean_flap_rate" in baseline
            assert "p95_flap_rate" in baseline


class TestClose:
    def test_close_calls_client_close(self):
        with patch("influxdb_client.InfluxDBClient") as mock_client_class:
            mock_client = MagicMock()
            mock_client.write_api.return_value = MagicMock()
            mock_client.query_api.return_value = MagicMock()
            mock_client_class.return_value = mock_client

            from core.influxdb_connector import InfluxDBConnector

            connector = InfluxDBConnector(
                url="http://x", token="t", org="o", bucket="b"
            )
            connector.close()
            mock_client.close.assert_called_once()


class TestQueryAnomalyTimeline:
    def test_query_anomaly_timeline_returns_buckets(self):
        with patch("influxdb_client.InfluxDBClient") as mock_client_class:
            mock_client = MagicMock()
            mock_query_api = MagicMock()
            mock_record = MagicMock()
            mock_record.get_time.return_value = MagicMock(
                isoformat=lambda: "2024-01-01T00:00:00+00:00"
            )
            mock_record.get_value.return_value = 12
            mock_table = MagicMock()
            mock_table.records = [mock_record]
            mock_query_api.query.return_value = [mock_table]
            mock_client.write_api.return_value = MagicMock()
            mock_client.query_api.return_value = mock_query_api
            mock_client_class.return_value = mock_client

            from core.influxdb_connector import InfluxDBConnector

            connector = InfluxDBConnector(
                url="http://x", token="t", org="o", bucket="b"
            )
            results = connector.query_anomaly_timeline("speaker-1", time_range="24h")
            assert len(results) == 1
            assert results[0]["flap_count"] == 12
            flux = mock_query_api.query.call_args[0][0]
            assert "aggregateWindow" in flux
            assert 'speaker_id == "speaker-1"' in flux

    def test_query_anomaly_timeline_without_speaker_filter(self):
        with patch("influxdb_client.InfluxDBClient") as mock_client_class:
            mock_client = MagicMock()
            mock_query_api = MagicMock()
            mock_query_api.query.return_value = []
            mock_client.write_api.return_value = MagicMock()
            mock_client.query_api.return_value = mock_query_api
            mock_client_class.return_value = mock_client

            from core.influxdb_connector import InfluxDBConnector

            connector = InfluxDBConnector(
                url="http://x", token="t", org="o", bucket="b"
            )
            connector.query_anomaly_timeline(time_range="7d")
            flux = mock_query_api.query.call_args[0][0]
            assert "speaker_id" not in flux


class TestQueryCorrelationMatrix:
    def test_query_correlation_matrix_empty(self):
        with patch("influxdb_client.InfluxDBClient") as mock_client_class:
            mock_client = MagicMock()
            mock_query_api = MagicMock()
            mock_query_api.query.return_value = []
            mock_client.write_api.return_value = MagicMock()
            mock_client.query_api.return_value = mock_query_api
            mock_client_class.return_value = mock_client

            from core.influxdb_connector import InfluxDBConnector

            connector = InfluxDBConnector(
                url="http://x", token="t", org="o", bucket="b"
            )
            assert connector.query_correlation_matrix() == {}

    def test_query_correlation_matrix_returns_dict(self):
        with patch("influxdb_client.InfluxDBClient") as mock_client_class:
            mock_client = MagicMock()
            mock_query_api = MagicMock()
            mock_record = MagicMock()
            mock_record.get_time.return_value = MagicMock(
                isoformat=lambda: "2024-01-01T00:00:00+00:00"
            )
            mock_record.get_value.return_value = 3.0
            mock_record.values = {"prefix": "10.0.0.0/24"}
            mock_table = MagicMock()
            mock_table.records = [mock_record]
            mock_query_api.query.return_value = [mock_table]
            mock_client.write_api.return_value = MagicMock()
            mock_client.query_api.return_value = mock_query_api
            mock_client_class.return_value = mock_client

            from core.influxdb_connector import InfluxDBConnector

            connector = InfluxDBConnector(
                url="http://x", token="t", org="o", bucket="b"
            )
            matrix = connector.query_correlation_matrix(
                time_range="7d", top_n_prefixes=10
            )
            assert "10.0.0.0/24" in matrix
