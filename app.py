from __future__ import annotations

import json
from pathlib import Path

import streamlit as st

from agentic_telco import AutonomousTelcoOrchestrator, load_incidents

st.set_page_config(page_title="TELCO AUTONOMOUS RESOLVE-X", page_icon="📡", layout="wide")

BASE_DIR = Path(__file__).resolve().parent

st.title("📡 TELCO AUTONOMOUS RESOLVE-X")
st.caption("Autonomous telecom incident detection → reasoning → action → validation")

incidents = load_incidents()
incident_map = {x["incident_id"]: x for x in incidents}

with st.sidebar:
    st.header("Demo Control")
    incident_id = st.selectbox("Choose telecom scenario", list(incident_map))
    st.write("**Autonomy mode:** Enabled")
    st.write("**Human intervention:** None")
    st.write("**Execution:** Safe simulator / no production network access")
    run = st.button("🚀 Start Autonomous Recovery", type="primary", use_container_width=True)

incident = incident_map[incident_id]

col1, col2, col3, col4 = st.columns(4)
col1.metric("Incident", incident["incident_id"])
col2.metric("Site", incident["site_id"])
col3.metric("Severity", incident["severity"])
col4.metric("Users Impacted", f"{incident['users_impacted']:,}")

st.subheader("Live Telemetry")
st.json(incident["metrics"])

if run:
    with st.spinner("Agents are detecting, reasoning, acting and validating..."):
        result = AutonomousTelcoOrchestrator().run(incident)
    st.session_state["result"] = result

result = st.session_state.get("result")
if result:
    inc = result["incident"]
    st.divider()
    left, right = st.columns([1.2, 1])
    with left:
        st.subheader("Autonomous Resolution")
        st.success(f"Status: {inc['status']}") if inc['status'] == 'RESOLVED' else st.error(f"Status: {inc['status']}")
        st.write(f"**Root cause:** {inc['root_cause']}")
        st.write(f"**Confidence:** {inc['confidence']:.0%}")
        st.write(f"**Actions executed:** {', '.join(inc['actions'])}")
        st.write(f"**Customer impact message:** {inc['customer_message']}")
        st.write(f"**Agent summary:** {result['summary']}")
    with right:
        st.subheader("Validation")
        st.metric("Recovered", "YES" if inc["validation"].get("recovered") else "NO")
        st.json(inc["validation"])

    st.subheader("Agent Trace")
    for i, item in enumerate(result["trace"], 1):
        agent = item.get("agent", "Agent")
        with st.expander(f"{i:02d}. {agent}", expanded=i <= 4):
            st.json(item)
else:
    st.info("Select a scenario and click 'Start Autonomous Recovery' to run the multi-agent workflow.")

st.divider()
st.caption("TELCO RESOLVE-X is a hackathon prototype using simulated telecom tools. It does not connect to production network equipment.")
