"""Shared Streamlit session helpers."""
from __future__ import annotations

import streamlit as st

from dashboard.utils.api_client import RouteMonitorClient


@st.cache_resource
def get_dashboard_client() -> RouteMonitorClient:
    """Return a cached API client configured for the dashboard."""
    return RouteMonitorClient()
