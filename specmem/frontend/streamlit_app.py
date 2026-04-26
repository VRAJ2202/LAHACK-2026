"""
SpecMem Streamlit Dashboard — Debug Episodes view.
Shows auto-captured errors with full lifecycle status.
"""

import os
import requests
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="SpecMem", page_icon="🧠", layout="wide")
st.title("🧠 SpecMem — Memory-Powered Debugging Agent")
st.caption("AI that remembers past bugs so it doesn't repeat mistakes.")

# ── Sidebar ────────────────────────────────────────────────────
with st.sidebar:
    st.header("Backend")
    try:
        r = requests.get(f"{BACKEND_URL}/health", timeout=3)
        data = r.json()
        if data.get("status") == "ok":
            st.success(f"Backend: connected\nMongoDB: {data.get('mongodb')}")
        else:
            st.warning(f"Backend: degraded\nMongoDB: {data.get('mongodb')}")
    except Exception as e:
        st.error(f"Backend unreachable: {e}")

    st.divider()
    st.markdown("**CLI Commands**")
    st.code('specmem run "python app.py"', language="bash")
    st.code('specmem fix "python app.py"', language="bash")
    st.code('specmem agent "python app.py"', language="bash")
    st.caption("Run these in your terminal")

# ── Debug Episodes ─────────────────────────────────────────────
st.subheader("Auto-Captured Debugging Episodes")
st.caption("Errors captured automatically via `specmem run` or `specmem agent`")

with st.form("episodes_form"):
    col1, col2 = st.columns([3, 1])
    ep_project = col1.text_input("Project ID", value="demo-project")
    ep_limit = col2.number_input("Limit", min_value=1, max_value=100, value=20)
    ep_submitted = st.form_submit_button("Load Episodes", use_container_width=True)

if ep_submitted:
    try:
        r = requests.get(
            f"{BACKEND_URL}/episodes",
            params={"project_id": ep_project, "limit": ep_limit},
            timeout=10,
        )
        r.raise_for_status()
        episodes = r.json()

        if not episodes:
            st.info('No episodes found. Run `specmem run "python app.py"` to capture errors.')
        else:
            # Summary metrics
            total = len(episodes)
            resolved = sum(1 for e in episodes if e.get("status") == "resolved")
            fixing = sum(1 for e in episodes if e.get("status") == "fixing")
            open_ = sum(1 for e in episodes if e.get("status") == "open")

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Episodes", total)
            m2.metric("🟢 Resolved", resolved)
            m3.metric("🟡 Fixing", fixing)
            m4.metric("🔴 Open", open_)

            st.divider()

            for ep in episodes:
                status = ep.get("status", "unknown")
                status_icon = {"open": "🔴", "fixing": "🟡", "resolved": "🟢"}.get(status, "⚪")
                title = f"{status_icon} {ep.get('error_type', 'Error')}: {ep.get('error_message', '')[:70]}"

                with st.expander(title):
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Status", status)
                    col2.metric("Fix Attempts", len(ep.get("failed_fixes", [])))
                    col3.metric("Command", ep.get("command", "")[:30])

                    st.write(f"**Files:** {', '.join(ep.get('file_paths', [])) or 'N/A'}")
                    st.write(f"**Module:** {ep.get('module', 'N/A')}")

                    if ep.get("stack_trace"):
                        st.code(ep["stack_trace"][:600], language="pytb")

                    if ep.get("failed_fixes"):
                        st.markdown("**❌ Failed Fix Attempts:**")
                        for i, ff in enumerate(ep["failed_fixes"], 1):
                            st.markdown(f"*Attempt {i}:*")
                            if ff.get("diff"):
                                st.code(ff["diff"][:300], language="diff")

                    if ep.get("successful_fix"):
                        st.markdown("**✅ Successful Fix:**")
                        st.code(ep["successful_fix"].get("diff", "")[:500], language="diff")

                    if ep.get("ai_suggestion"):
                        st.markdown("**🧠 AI Suggestion:**")
                        st.markdown(ep["ai_suggestion"])

                    st.caption(f"ID: {ep.get('id')} | Created: {ep.get('created_at')}")

    except Exception as e:
        st.error(f"Error: {e}")
