"""Device Health — Streamlit page entry point."""
from dashboard.utils.session import get_dashboard_client
from dashboard.views.device_health import render

render(get_dashboard_client())
