"""RouteMonitor Streamlit Dashboard — home page.

Run with: streamlit run dashboard/app.py
"""
import streamlit as st

from dashboard.utils.session import get_dashboard_client

st.set_page_config(
    page_title="RouteMonitor",
    page_icon="🛰️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("🛰️ RouteMonitor")
st.caption("Real-Time BGP Telemetry & Anomaly Detection")
st.markdown(
    "Use the sidebar to open **Route Timeline**, **Device Health**, "
    "**Anomaly Timeline**, or **Correlation Matrix**."
)

client = get_dashboard_client()

col1, col2, col3 = st.columns(3)
try:
    health = client.health_check()
    status = health.get("status", "unknown")
    col1.metric("API Status", status.upper())
    services = health.get("services", {})
    col2.metric("Services OK", sum(1 for v in services.values() if v == "ok"))
    col3.metric("Services Total", len(services))
    for svc, svc_status in services.items():
        icon = "✅" if svc_status == "ok" else "❌"
        st.caption(f"{icon} {svc}: {svc_status}")
except Exception:
    col1.metric("API Status", "UNREACHABLE")
    st.error(
        "Cannot connect to RouteMonitor API at http://localhost:8001. Is Docker running?"
    )

with st.sidebar:
    st.divider()
    try:
        health = client.health_check()
        status_color = "🟢" if health["status"] == "healthy" else "🟡"
        st.caption(f"{status_color} API: {health['status']}")
        for svc, svc_status in health.get("services", {}).items():
            icon = "✅" if svc_status == "ok" else "❌"
            st.caption(f"  {icon} {svc}: {svc_status}")
    except Exception:
        st.caption("🔴 API: unreachable")
