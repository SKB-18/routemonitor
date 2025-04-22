"""Unit tests for the RouteMonitor API client."""
from unittest.mock import MagicMock, patch

import httpx
import pytest

from dashboard.utils.api_client import API_BASE_URL, RouteMonitorClient


@pytest.fixture
def client():
    c = RouteMonitorClient(base_url="http://test")
    yield c
    c.close()


def _mock_response(json_data, status_code=200):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.text = str(json_data)
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    return resp


class TestClientInit:
    def test_default_base_url(self):
        assert API_BASE_URL == "http://localhost:8001"

    def test_strips_trailing_slash(self):
        c = RouteMonitorClient(base_url="http://test/")
        assert c.base_url == "http://test"
        c.close()

    def test_context_manager(self):
        with RouteMonitorClient(base_url="http://test") as c:
            assert isinstance(c, RouteMonitorClient)


class TestRouteMonitorClient:
    def test_list_speakers(self, client):
        with patch.object(
            client._client, "get", return_value=_mock_response([{"id": "1"}])
        ):
            assert client.list_speakers() == [{"id": "1"}]
            client._client.get.assert_called_with("/api/telemetry/speakers")

    def test_get_speaker(self, client):
        with patch.object(
            client._client, "get", return_value=_mock_response({"id": "1"})
        ):
            assert client.get_speaker("1")["id"] == "1"
            client._client.get.assert_called_with("/api/telemetry/speakers/1")

    def test_get_speaker_status(self, client):
        payload = {"status": "CONNECTED", "current_flap_rate": 2.0}
        with patch.object(client._client, "get", return_value=_mock_response(payload)):
            assert client.get_speaker_status("1") == payload

    def test_health_check_uses_root_path(self, client):
        with patch.object(
            client._client,
            "get",
            return_value=_mock_response({"status": "healthy", "services": {}}),
        ):
            data = client.health_check()
            assert data["status"] == "healthy"
            client._client.get.assert_called_with("/health")

    def test_get_speaker_metrics(self, client):
        payload = {"speaker_id": "abc", "total_flaps": 5}
        with patch.object(client._client, "get", return_value=_mock_response(payload)):
            assert client.get_speaker_metrics("abc", "24h") == payload
            client._client.get.assert_called_with(
                "/api/metrics/speaker/abc",
                params={"time_range": "24h"},
            )

    def test_get_route_events_minimal_params(self, client):
        with patch.object(client._client, "get", return_value=_mock_response([])):
            client.get_route_events()
            _, kwargs = client._client.get.call_args
            assert kwargs["params"] == {"limit": 500}
            assert "speaker_id" not in kwargs["params"]

    def test_get_route_events_all_filters(self, client):
        with patch.object(client._client, "get", return_value=_mock_response([])):
            client.get_route_events(
                speaker_id="s1",
                prefix="10.0.0.0/24",
                event_type="WITHDRAW",
                limit=50,
            )
            _, kwargs = client._client.get.call_args
            assert kwargs["params"] == {
                "limit": 50,
                "speaker_id": "s1",
                "prefix": "10.0.0.0/24",
                "event_type": "WITHDRAW",
            }

    def test_get_route_stats_with_prefix(self, client):
        with patch.object(
            client._client, "get", return_value=_mock_response({"data_points": []})
        ):
            client.get_route_stats("s1", prefix="10.0.0.0/24", time_range="7d")
            _, kwargs = client._client.get.call_args
            assert kwargs["params"]["prefix"] == "10.0.0.0/24"
            assert kwargs["params"]["time_range"] == "7d"

    def test_list_anomalies_with_acknowledged_filter(self, client):
        with patch.object(client._client, "get", return_value=_mock_response([])):
            client.list_anomalies(acknowledged=False)
            _, kwargs = client._client.get.call_args
            assert kwargs["params"]["acknowledged"] == "false"

    def test_list_anomalies_acknowledged_true(self, client):
        with patch.object(client._client, "get", return_value=_mock_response([])):
            client.list_anomalies(acknowledged=True)
            _, kwargs = client._client.get.call_args
            assert kwargs["params"]["acknowledged"] == "true"

    def test_list_anomalies_all_optional_filters(self, client):
        with patch.object(client._client, "get", return_value=_mock_response([])):
            client.list_anomalies(
                speaker_id="s1",
                severity="CRITICAL",
                anomaly_type="ROUTE_FLAP",
                time_range="7d",
                limit=10,
            )
            _, kwargs = client._client.get.call_args
            p = kwargs["params"]
            assert p["speaker_id"] == "s1"
            assert p["severity"] == "CRITICAL"
            assert p["anomaly_type"] == "ROUTE_FLAP"
            assert p["time_range"] == "7d"
            assert p["limit"] == 10

    def test_acknowledge_anomaly(self, client):
        token_resp = _mock_response({"access_token": "tok"})
        ack_resp = _mock_response({"acknowledged": True})
        with patch.object(
            client._client, "post", side_effect=[token_resp, ack_resp]
        ) as mock_post:
            result = client.acknowledge_anomaly("id-1", "ops")
            assert result["acknowledged"] is True
            assert mock_post.call_count == 2
            _, kwargs = mock_post.call_args
            assert kwargs["headers"]["Authorization"] == "Bearer tok"

    def test_get_correlation(self, client):
        with patch.object(
            client._client,
            "get",
            return_value=_mock_response({"matrix": {}}),
        ):
            assert client.get_correlation("7d", top_n_prefixes=20) == {"matrix": {}}
            _, kwargs = client._client.get.call_args
            assert kwargs["params"] == {"time_range": "7d", "top_n_prefixes": 20}

    def test_http_error_propagates(self, client):
        with patch.object(
            client._client, "get", return_value=_mock_response({}, status_code=500)
        ):
            with pytest.raises(httpx.HTTPStatusError):
                client.list_speakers()

    def test_close_closes_underlying_client(self, client):
        with patch.object(client._client, "close", MagicMock()) as mock_close:
            client.close()
            mock_close.assert_called_once()
