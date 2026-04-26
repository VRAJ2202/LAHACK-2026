"""
SpecMem FastAPI application — all endpoints.
"""

from fastapi import FastAPI, HTTPException, Query

from specmem.backend.database import ensure_indexes, ping
from specmem.backend.schemas import (
    BugMemoryCreate,
    BugMemoryResponse,
    CheckFixRequest,
    DebugQuery,
    DebugResponse,
    DebugEpisodeResponse,
    ExtractRequest,
    FeedbackRequest,
    TokenLogCreate,
)
from specmem.backend.memory_service import (
    create_bug_memory,
    get_bug_memory_by_id,
    list_bug_memories,
    save_token_log,
    update_memory_feedback,
    list_episodes,
    get_episode_by_id,
)

app = FastAPI(
    title="SpecMem API",
    description="Memory-Powered Debugging Agent",
    version="0.2.0",
)


@app.on_event("startup")
def on_startup() -> None:
    ensure_indexes()


# ── Health ─────────────────────────────────────────────────────

@app.get("/health")
def health_check():
    mongo_ok = ping()
    return {
        "status": "ok" if mongo_ok else "degraded",
        "mongodb": "connected" if mongo_ok else "unreachable",
    }


# ── Bug Memory endpoints (manual) ─────────────────────────────

@app.post("/memory", response_model=BugMemoryResponse)
def create_memory(data: BugMemoryCreate):
    doc = create_bug_memory(data)
    try:
        from specmem.backend.retrieval_service import add_embedding_to_memory
        updated = add_embedding_to_memory(doc["id"])
        if updated:
            doc = updated
    except Exception as e:
        print(f"[embedding] failed for {doc['id']}: {e}")
    return doc


@app.get("/memory/{memory_id}", response_model=BugMemoryResponse)
def get_memory(memory_id: str):
    doc = get_bug_memory_by_id(memory_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Memory not found")
    return doc


@app.get("/memory", response_model=list[BugMemoryResponse])
def get_memories(
    project_id: str = Query(..., description="Project identifier"),
    limit: int = Query(20, ge=1, le=100),
):
    return list_bug_memories(project_id, limit=limit)


# ── Token Log ──────────────────────────────────────────────────

@app.post("/token-log")
def create_token_log(data: TokenLogCreate):
    return save_token_log(
        project_id=data.project_id, query=data.query,
        before_tokens=data.before_tokens, after_tokens=data.after_tokens,
    )


# ── Debug endpoint ─────────────────────────────────────────────

@app.post("/debug", response_model=DebugResponse)
def debug_bug(data: DebugQuery):
    from specmem.backend.llm_service import generate_debug_response
    return generate_debug_response(
        project_id=data.project_id, query=data.query,
        module=data.module, file_path=data.file_path,
    )


# ── Check Fix ──────────────────────────────────────────────────

@app.post("/check")
def check_fix(data: CheckFixRequest):
    from specmem.backend.retrieval_service import detect_failed_fix
    match, confidence = detect_failed_fix(
        project_id=data.project_id, proposed_fix=data.proposed_fix,
        module=data.module,
    )
    if match:
        return {
            "warning": f"This fix was already tried and failed: '{match.get('bug_title', 'unknown bug')}'",
            "matched_failed_fix": match,
        }
    return {"warning": None, "matched_failed_fix": None}


# ── Auto Extract ───────────────────────────────────────────────

@app.post("/extract", response_model=BugMemoryResponse)
def extract_and_save(data: ExtractRequest):
    from specmem.backend.llm_service import extract_bug_memory
    extracted = extract_bug_memory(project_id=data.project_id, raw_text=data.raw_text)
    memory_data = BugMemoryCreate(**extracted)
    doc = create_bug_memory(memory_data)
    try:
        from specmem.backend.retrieval_service import add_embedding_to_memory
        updated = add_embedding_to_memory(doc["id"])
        if updated:
            doc = updated
    except Exception as e:
        print(f"[embedding] failed for {doc['id']}: {e}")
    return doc


# ── Feedback ───────────────────────────────────────────────────

@app.patch("/memory/{memory_id}/feedback")
def give_feedback(memory_id: str, data: FeedbackRequest):
    doc = update_memory_feedback(
        memory_id=memory_id, fix_worked=data.fix_worked, notes=data.notes,
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Memory not found")
    return doc


# ── Debug Episodes (automatic capture) ─────────────────────────

@app.get("/episodes", response_model=list[DebugEpisodeResponse])
def get_episodes(
    project_id: str = Query(..., description="Project identifier"),
    limit: int = Query(20, ge=1, le=100),
):
    return list_episodes(project_id, limit=limit)


@app.get("/episodes/{episode_id}", response_model=DebugEpisodeResponse)
def get_episode(episode_id: str):
    doc = get_episode_by_id(episode_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Episode not found")
    return doc


@app.post("/episodes/capture", response_model=DebugEpisodeResponse)
def capture_episode(data: dict):
    """Auto-capture an error from specmem run."""
    from specmem.backend.memory_service import create_debug_episode, update_episode_ai_suggestion
    from specmem.backend.retrieval_service import add_embedding_to_episode
    from specmem.backend.llm_service import generate_episode_suggestion

    ep = create_debug_episode(
        project_id=data["project_id"],
        command=data.get("command", ""),
        error_message=data.get("error_message", ""),
        stack_trace=data.get("stack_trace", ""),
        error_type=data.get("error_type", ""),
        file_paths=data.get("file_paths", []),
        module=data.get("module", ""),
    )

    # Generate embedding
    try:
        add_embedding_to_episode(ep["id"], ep)
    except Exception as e:
        print(f"[episode embedding] failed: {e}")

    # Generate AI suggestion
    try:
        suggestion, similar = generate_episode_suggestion(
            project_id=data["project_id"],
            error_message=data.get("error_message", ""),
            stack_trace=data.get("stack_trace", ""),
            file_paths=data.get("file_paths", []),
        )
        ep = update_episode_ai_suggestion(ep["id"], suggestion, similar) or ep
    except Exception as e:
        print(f"[episode suggestion] failed: {e}")

    return ep


@app.post("/episodes/fix-result")
def record_fix_result(data: dict):
    """Record whether a fix attempt succeeded or failed (from specmem fix)."""
    from specmem.backend.memory_service import (
        get_latest_open_episode,
        add_failed_fix_to_episode,
        resolve_episode,
    )
    from specmem.backend.llm_service import generate_episode_suggestion

    ep = get_latest_open_episode(data["project_id"])
    if not ep:
        return {"message": "No open episode found", "ai_suggestion": ""}

    if data.get("success"):
        result = resolve_episode(ep["id"], data.get("diff", ""))
        return {
            "message": "Fix recorded as successful",
            "episode_id": ep["id"],
            "status": "resolved",
        }
    else:
        result = add_failed_fix_to_episode(
            ep["id"], data.get("diff", ""), data.get("stderr", ""),
        )

        # Generate updated suggestion after failed fix
        suggestion = ""
        try:
            suggestion, _ = generate_episode_suggestion(
                project_id=data["project_id"],
                error_message=data.get("stderr", "")[:500],
                stack_trace=data.get("stderr", ""),
                file_paths=[],
            )
        except Exception:
            pass

        return {
            "message": "Failed fix recorded",
            "episode_id": ep["id"],
            "status": "fixing",
            "ai_suggestion": suggestion,
        }
