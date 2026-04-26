"""
SpecMem Streamlit Dashboard — judge-facing demo UI.
Shows both manual memories and auto-captured episodes.
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

    st.divider()
    st.markdown("**CLI Commands**")
    st.code('specmem run "python app.py"', language="bash")
    st.code('specmem fix "python app.py"', language="bash")
    st.caption("Run these in VS Code terminal")

# ── Tabs ───────────────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🔴 Debug Episodes", "Auto Extract", "Debug Bug",
    "Check Fix", "Browse Memories", "Add Memory",
])

# ── Tab 1: Debug Episodes (auto-captured) ──────────────────────
with tab1:
    st.subheader("Auto-Captured Debugging Episodes")
    st.caption("These are errors captured automatically via `specmem run`")

    with st.form("episodes_form"):
        ep_project = st.text_input("Project ID", value="demo-project", key="ep_proj")
        ep_submitted = st.form_submit_button("Load Episodes")

    if ep_submitted:
        try:
            r = requests.get(
                f"{BACKEND_URL}/episodes",
                params={"project_id": ep_project},
                timeout=10,
            )
            r.raise_for_status()
            episodes = r.json()
            if not episodes:
                st.info("No episodes found. Run `specmem run \"python app.py\"` to capture errors.")
            for ep in episodes:
                status_icon = {"open": "🔴", "fixing": "🟡", "resolved": "🟢"}.get(ep.get("status", ""), "⚪")
                title = f"{status_icon} {ep.get('error_type', 'Error')}: {ep.get('error_message', '')[:60]}"
                with st.expander(title):
                    col1, col2, col3 = st.columns(3)
                    col1.metric("Status", ep.get("status", "unknown"))
                    col2.metric("Fix Attempts", len(ep.get("failed_fixes", [])))
                    col3.metric("Command", ep.get("command", "")[:30])

                    st.write(f"**Files:** {', '.join(ep.get('file_paths', []))}")
                    st.write(f"**Module:** {ep.get('module', 'N/A')}")

                    if ep.get("stack_trace"):
                        st.code(ep["stack_trace"][:500], language="pytb")

                    if ep.get("failed_fixes"):
                        st.markdown("**Failed Fix Attempts:**")
                        for i, ff in enumerate(ep["failed_fixes"], 1):
                            st.markdown(f"*Attempt {i}:*")
                            if ff.get("diff"):
                                st.code(ff["diff"][:300], language="diff")

                    if ep.get("successful_fix"):
                        st.markdown("**✅ Successful Fix:**")
                        st.code(ep["successful_fix"].get("diff", "")[:300], language="diff")

                    if ep.get("ai_suggestion"):
                        st.markdown("**🧠 AI Suggestion:**")
                        st.markdown(ep["ai_suggestion"])

                    st.caption(f"ID: {ep.get('id')} | Created: {ep.get('created_at')}")
        except Exception as e:
            st.error(f"Error: {e}")

# ── Tab 2: Auto Extract ────────────────────────────────────────
with tab2:
    st.subheader("Auto Extract Bug Memory")
    st.caption("Paste raw text — bug report, Slack message, terminal output — Gemini extracts and saves it.")
    with st.form("extract_form"):
        e_project = st.text_input("Project ID", value="demo-project", key="e_proj")
        e_text = st.text_area(
            "Raw text", height=200,
            placeholder="e.g. Fixed the login bug today. We tried increasing the timeout but that didn't work...",
        )
        extract_submitted = st.form_submit_button("Extract & Save Memory")
    if extract_submitted and e_text:
        with st.spinner("Gemini is extracting..."):
            try:
                r = requests.post(f"{BACKEND_URL}/extract", json={"project_id": e_project, "raw_text": e_text}, timeout=30)
                r.raise_for_status()
                mem = r.json()
                st.success(f"Memory saved! ID: {mem.get('id','')[:8]}...")
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Title:** {mem.get('bug_title')}")
                    st.write(f"**Root cause:** {mem.get('root_cause')}")
                with col2:
                    st.write(f"**Final fix:** {mem.get('final_fix')}")
                    st.write(f"**Failed fixes:** {', '.join(mem.get('failed_fixes', []))}")
            except Exception as e:
                st.error(f"Error: {e}")

# ── Tab 3: Debug ───────────────────────────────────────────────
with tab3:
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
                    st.markdown("### Similar Past Issues")
                    for bug in res["similar_bugs"]:
                        title = bug.get("bug_title", bug.get("error_type", "Unknown"))
                        with st.expander(title):
                            st.write(f"**Module:** {bug.get('module')} | **File:** {bug.get('file_path', ', '.join(bug.get('file_paths', [])))}")
                            st.write(f"**Root cause:** {bug.get('root_cause', bug.get('error_message', ''))}")
                            st.write(f"**Final fix:** {bug.get('final_fix', bug.get('status', ''))}")
                            if bug.get("failed_fixes"):
                                st.write(f"**Failed approaches:** {len(bug['failed_fixes'])} attempts")
            except Exception as e:
                st.error(f"Error: {e}")

# ── Tab 4: Check Fix ───────────────────────────────────────────
with tab4:
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
                st.success("No matching failed fix — safe to try.")
        except Exception as e:
            st.error(f"Error: {e}")

# ── Tab 5: Browse Memories ─────────────────────────────────────
with tab5:
    st.subheader("Browse Project Memories")
    with st.form("browse_form"):
        b_project = st.text_input("Project ID", value="demo-project", key="b_proj")
        browse_submitted = st.form_submit_button("Load Memories")
    if browse_submitted:
        try:
            r = requests.get(f"{BACKEND_URL}/memory", params={"project_id": b_project}, timeout=10)
            r.raise_for_status()
            memories = r.json()
            if not memories:
                st.info("No memories found.")
            for mem in memories:
                with st.expander(f"{mem.get('bug_title','Unknown')} — {mem.get('module','?')}"):
                    st.write(f"**File:** {mem.get('file_path')}")
                    st.write(f"**Description:** {mem.get('description')}")
                    st.write(f"**Root cause:** {mem.get('root_cause')}")
                    st.write(f"**Final fix:** {mem.get('final_fix')}")
                    if mem.get("failed_fixes"):
                        st.write(f"**Failed fixes:** {', '.join(str(f) for f in mem['failed_fixes'])}")
                    st.caption(f"ID: {mem.get('id')} | Created: {mem.get('created_at')}")
        except Exception as e:
            st.error(f"Error: {e}")

# ── Tab 6: Add Memory (manual) ────────────────────────────────
with tab6:
    st.subheader("Save a Bug Memory (Manual)")
    with st.form("add_memory_form"):
        project_id = st.text_input("Project ID", value="demo-project")
        bug_title = st.text_input("Bug Title")
        description = st.text_area("Description")
        file_path = st.text_input("File Path")
        module = st.text_input("Module")
        failed_fixes_raw = st.text_area("Failed Fixes (one per line)")
        root_cause = st.text_input("Root Cause")
        final_fix = st.text_area("Final Fix")
        tags_raw = st.text_input("Tags (comma-separated)")
        submitted = st.form_submit_button("Save Memory")
    if submitted:
        payload = {
            "project_id": project_id, "bug_title": bug_title,
            "description": description, "file_path": file_path,
            "module": module, "root_cause": root_cause, "final_fix": final_fix,
            "failed_fixes": [l.strip() for l in failed_fixes_raw.splitlines() if l.strip()],
            "tags": [t.strip() for t in tags_raw.split(",") if t.strip()],
        }
        try:
            r = requests.post(f"{BACKEND_URL}/memory", json=payload, timeout=10)
            r.raise_for_status()
            st.success(f"Memory saved! ID: {r.json().get('id','')[:8]}...")
        except Exception as e:
            st.error(f"Error: {e}")
