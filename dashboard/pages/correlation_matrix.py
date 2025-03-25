"""Correlation Matrix — Streamlit page entry point."""
from dashboard.utils.session import get_dashboard_client
from dashboard.views.correlation_matrix import render

render(get_dashboard_client())
