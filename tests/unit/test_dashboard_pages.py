"""Unit tests for Streamlit dashboard pages (streamlit mocked)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _mock_streamlit(**overrides):
    """Build a MagicMock stand-in for streamlit with sensible defaults."""
    st = MagicMock()

    def _columns(spec):
        n = spec if isinstance(spec, int) else len(spec)
        return [MagicMock() for _ in range(n)]

    st.columns.side_effect = _columns
    st.button.return_value = overrides.get("button", False)
    st.selectbox.return_value = overrides.get("selectbox", "(all)")
    st.multiselect.side_effect = overrides.get(
        "multiselect_side_effect",
        lambda *a, **k: overrides.get("multiselect", []),
    )
    st.checkbox.return_value = overrides.get("checkbox", False)
    st.text_input.return_value = overrides.get("text_input", "")
    st.slider.return_value = overrides.get("slider", 20)
    expander = MagicMock()
    expander.__enter__ = MagicMock(return_value=None)
    expander.__exit__ = MagicMock(return_value=False)
    st.expander.return_value = expander
    st.metric = MagicMock()
    st.plotly_chart = MagicMock()
    st.dataframe = MagicMock()
    st.divider = MagicMock()
    st.caption = MagicMock()
    st.title = MagicMock()
    st.subheader = MagicMock()
    st.error = MagicMock()
    st.info = MagicMock()
    st.warning = MagicMock()
    st.success = MagicMock()
    st.write = MagicMock()
    st.rerun = MagicMock()
    st.cache_data.clear = MagicMock()
    return st


@pytest.fixture
def api_client():
    client = MagicMock()
    client.list_speakers.return_value = []
    client.list_anomalies.return_value = []
    client.get_route_events.return_value = []
    client.get_correlation.return_value = {"matrix": {}}
    return client


class TestDeviceHealthPage:
    def test_empty_speakers_shows_info(self, api_client):
        from dashboard.views import device_health

        st = _mock_streamlit()
        with patch.object(device_health, "st", st):
            device_health.render(api_client)
        st.info.assert_called_once()
        api_client.list_speakers.assert_called_once()

    def test_api_connect_error_shows_error(self, api_client):
        import httpx
        from dashboard.views import device_health

        api_client.list_speakers.side_effect = httpx.ConnectError("refused")
        st = _mock_streamlit()
        with patch.object(device_health, "st", st):
            device_health.render(api_client)
        st.error.assert_called_once()

    def test_renders_speaker_expander(self, api_client):
        from dashboard.views import device_health

        api_client.list_speakers.return_value = [
            {
                "id": "sp-1",
                "hostname": "r1",
                "local_asn": 65001,
                "status": "CONNECTED",
            }
        ]
        api_client.get_speaker_status.return_value = {
            "connected_for_seconds": 120,
            "routes_advertised_24h": 10,
            "routes_withdrawn_24h": 2,
            "current_flap_rate": 1.5,
        }
        api_client.get_route_stats.return_value = {"data_points": []}

        st = _mock_streamlit()
        with patch.object(device_health, "st", st):
            device_health.render(api_client)
        st.expander.assert_called()
        api_client.get_speaker_status.assert_called_with("sp-1")


class TestRouteTimelinePage:
    def test_fetch_button_not_pressed_returns_early(self, api_client):
        from dashboard.views import route_timeline

        api_client.list_speakers.return_value = [{"hostname": "r1", "id": "sp-1"}]
        st = _mock_streamlit(button=False)
        with patch.object(route_timeline, "st", st):
            route_timeline.render(api_client)
        api_client.get_route_events.assert_not_called()

    def test_no_events_shows_warning(self, api_client):
        from dashboard.views import route_timeline

        api_client.list_speakers.return_value = [{"hostname": "r1", "id": "sp-1"}]
        st = _mock_streamlit(button=True)
        with patch.object(route_timeline, "st", st):
            route_timeline.render(api_client)
        st.warning.assert_called_once()

    def test_events_render_charts(self, api_client):
        from dashboard.views import route_timeline

        api_client.list_speakers.return_value = [{"hostname": "r1", "id": "sp-1"}]
        api_client.get_route_events.return_value = [
            {
                "timestamp": "2024-01-01T00:00:00+00:00",
                "event_type": "UPDATE",
                "prefix": "10.0.0.0/24",
                "neighbor_ip": "10.0.0.1",
                "neighbor_asn": 65001,
            },
            {
                "timestamp": "2024-01-01T00:01:00+00:00",
                "event_type": "WITHDRAW",
                "prefix": "10.0.0.0/24",
                "neighbor_ip": "10.0.0.1",
                "neighbor_asn": 65001,
            },
        ]
        st = _mock_streamlit(button=True)
        with patch.object(route_timeline, "st", st):
            route_timeline.render(api_client)
        assert st.plotly_chart.call_count >= 1


class TestAnomalyTimelinePage:
    def test_no_anomalies_shows_success(self, api_client):
        from dashboard.views import anomaly_timeline

        st = _mock_streamlit()
        with patch.object(anomaly_timeline, "st", st):
            anomaly_timeline.render(api_client)
        st.success.assert_called_once()

    def test_anomalies_render_expander(self, api_client):
        from dashboard.views import anomaly_timeline

        api_client.list_anomalies.return_value = [
            {
                "id": "a1",
                "anomaly_type": "ROUTE_FLAP",
                "severity": "WARNING",
                "prefix": "10.0.0.0/24",
                "detected_at": "2024-01-01T00:00:00+00:00",
                "acknowledged": False,
                "details": {"z_score": 4.2},
            }
        ]
        st = _mock_streamlit(
            multiselect_side_effect=[
                ["WARNING", "CRITICAL"],
                [],
            ],
        )
        with patch.object(anomaly_timeline, "st", st):
            anomaly_timeline.render(api_client)
        st.expander.assert_called()
        st.plotly_chart.assert_called_once()


class TestCorrelationMatrixPage:
    def test_compute_not_pressed_returns_early(self, api_client):
        from dashboard.views import correlation_matrix

        st = _mock_streamlit(button=False)
        with patch.object(correlation_matrix, "st", st):
            correlation_matrix.render(api_client)
        api_client.get_correlation.assert_not_called()

    def test_empty_matrix_shows_warning(self, api_client):
        from dashboard.views import correlation_matrix

        st = _mock_streamlit(button=True)
        with patch.object(correlation_matrix, "st", st):
            correlation_matrix.render(api_client)
        st.warning.assert_called_once()

    def test_matrix_renders_heatmap(self, api_client):
        from dashboard.views import correlation_matrix

        api_client.get_correlation.return_value = {
            "matrix": {
                "10.0.0.0/24": {"10.0.0.0/24": 1.0, "10.0.1.0/24": 0.9},
                "10.0.1.0/24": {"10.0.0.0/24": 0.9, "10.0.1.0/24": 1.0},
            },
        }
        st = _mock_streamlit(button=True)
        with patch.object(correlation_matrix, "st", st):
            correlation_matrix.render(api_client)
        st.plotly_chart.assert_called_once()
        st.dataframe.assert_called_once()
