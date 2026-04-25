"""
SpecMem Streamlit Dashboard — judge-facing demo UI.
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
    st.markdown("**Demo**")
    if st.button("Load Sample Demo Memory"):
        demo = {
            "project_id": "demo-project",
            "bug_title": "Login fails after token refresh",
            "description": "User gets logged out after refresh token expires.",
            "file_path": "auth/token.py",
            "module": "auth",
            "failed_fixes": ["Increased timeout"],
            "root_cause": "Async race condition during token refresh",
            "final_fix": "Refresh token before retrying protected request",
            "tags": ["auth", "async", "token"],
        }
        try:
            r = requests.post(f"{BACKEND_URL}/memory", json=demo, timeout=10)
            r.raise_for_status()
            st.success(f"Demo memory loaded! ID: {r.json().get('id','')[:8]}...")
        except Exception as e:
            st.error(f"Failed: {e}")

# ── Tabs ───────────────────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(["Add Memory", "Debug Bug", "Check Fix", "Browse Memories"])

# ── Tab 1: Add Memory ──────────────────────────────────────────
with tab1:
    st.subheader("Save a Bug Memory")
    with st.form("add_memory_form"):
        project_id = st.text_input("Project ID", value="demo-project")
        bug_title = st.text_input("Bug Title")
        description = st.text_area("Description")
        file_path = st.text_input("File Path (e.g. auth/token.py)")
        module = st.text_input("Module (e.g. auth)")
        failed_fixes_raw = st.text_area("Failed Fixes (one per line)")
        root_cause = st.text_input("Root Cause")
        final_fix = st.text_area("Final Fix")
        tags_raw = st.text_input("Tags (comma-separated)")
        submitted = st.form_submit_button("Save Memory")

    if submitted:
        payload = {
            "project_id": project_id,
            "bug_title": bug_title,
            "description": description,
            "file_path": file_path,
            "module": module,
            "failed_fixes": [l.strip() for l in failed_fixes_raw.splitlines() if l.strip()],
            "root_cause": root_cause,
            "final_fix": final_fix,
            "tags": [t.strip() for t in tags_raw.split(",") if t.strip()],
        }
        try:
            r = requests.post(f"{BACKEND_URL}/memory", json=payload, timeout=10)
            r.raise_for_status()
            st.success(f"Memory saved! ID: {r.json().get('id','')[:8]}...")
        except Exception as e:
            st.error(f"Error: {e}")

# ── Tab 2: Debug ───────────────────────────────────────────────
with tab2:
    st.subheader("Debug a Bug with SpecMem")
    with st.form("debug_form"):
        d_project = st.text_input("Project ID", value="demo-project", key="d_proj")
        d_query = st.text_area("Describe the bug", placeholder="Login fails after token refresh again...")
        d_module = st.text_input("Module (optional)", key="d_mod")
        d_file = st.text_input("File path (optional)", key="d_file")
        debug_submitted = st.form_submit_button("Debug with SpecMem")

    if debug_submitted and d_query:
        with st.spinner("Consulting memory..."):
            try:
                r = requests.post(
                    f"{BACKEND_URL}/debug",
                    json={"project_id": d_project, "query": d_query,
                          "module": d_module or None, "file_path": d_file or None},
                    timeout=30,
                )
                r.raise_for_status()
                res = r.json()

                st.markdown("### AI Answer")
                st.markdown(res.get("answer", ""))

                if res.get("failed_fix_warning"):
                    st.warning(f"⚠️ {res['failed_fix_warning']}")

                if res.get("token_savings"):
                    ts = res["token_savings"]
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Before (tokens)", ts.get("before_tokens"))
                    col2.metric("After (tokens)", ts.get("after_tokens"))
                    col3.metric("Savings", f"{ts.get('savings_percent')}%")

                if res.get("similar_bugs"):
                    st.markdown("### Similar Past Bugs")
                    for bug in res["similar_bugs"]:
                        with st.expander(bug.get("bug_title", "Unknown")):
                            st.write(f"**Module:** {bug.get('module')} | **File:** {bug.get('file_path')}")
                            st.write(f"**Root cause:** {bug.get('root_cause')}")
                            st.write(f"**Final fix:** {bug.get('final_fix')}")
                            if bug.get("failed_fixes"):
                                st.write(f"**Failed approaches:** {', '.join(bug['failed_fixes'])}")
            except Exception as e:
                st.error(f"Error: {e}")

# ── Tab 3: Check Fix ───────────────────────────────────────────
with tab3:
    st.subheader("Check if a Fix Has Failed Before")
    with st.form("check_form"):
        c_project = st.text_input("Project ID", value="demo-project", key="c_proj")
        c_fix = st.text_area("Proposed Fix", placeholder="Increase the timeout to 30s")
        c_module = st.text_input("Module (optional)", key="c_mod")
        check_submitted = st.form_submit_button("Check Fix")

    if check_submitted and c_fix:
        try:
            r = requests.post(
                f"{BACKEND_URL}/check",
                json={"project_id": c_project, "proposed_fix": c_fix, "module": c_module or None},
                timeout=10,
            )
            r.raise_for_status()
            res = r.json()
            if res.get("warning"):
                st.warning(f"⚠️ {res['warning']}")
                if res.get("matched_failed_fix"):
                    st.json(res["matched_failed_fix"])
            else:
                st.success("No matching failed fix found — this approach looks safe to try.")
        except Exception as e:
            st.error(f"Error: {e}")

# ── Tab 4: Browse Memories ─────────────────────────────────────
with tab4:
    st.subheader("Browse Project Memories")
    with st.form("browse_form"):
        b_project = st.text_input("Project ID", value="demo-project", key="b_proj")
        browse_submitted = st.form_submit_button("Load Memories")

    if browse_submitted:
        try:
            r = requests.get(
                f"{BACKEND_URL}/memory",
                params={"project_id": b_project},
                timeout=10,
            )
            r.raise_for_status()
            memories = r.json()
            if not memories:
                st.info("No memories found for this project.")
            for mem in memories:
                with st.expander(f"{mem.get('bug_title','Unknown')} — {mem.get('module','?')}"):
                    st.write(f"**File:** {mem.get('file_path')}")
                    st.write(f"**Description:** {mem.get('description')}")
                    st.write(f"**Root cause:** {mem.get('root_cause')}")
                    st.write(f"**Final fix:** {mem.get('final_fix')}")
                    if mem.get("failed_fixes"):
                        st.write(f"**Failed fixes:** {', '.join(mem['failed_fixes'])}")
                    st.caption(f"ID: {mem.get('id')} | Created: {mem.get('created_at')}")
        except Exception as e:
            st.error(f"Error: {e}")
