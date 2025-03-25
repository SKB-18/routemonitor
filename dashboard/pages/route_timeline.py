"""Route Timeline — Streamlit page entry point."""
from dashboard.utils.session import get_dashboard_client
from dashboard.views.route_timeline import render

render(get_dashboard_client())
