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
    TokenLogCreate,
)
from specmem.backend.memory_service import (
    create_bug_memory,
    get_bug_memory_by_id,
    list_bug_memories,
    save_token_log,
)

app = FastAPI(
    title="SpecMem API",
    description="Memory-Powered Debugging Agent",
    version="0.1.0",
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


# ── Bug Memory endpoints ──────────────────────────────────────

@app.post("/memory", response_model=BugMemoryResponse)
def create_memory(data: BugMemoryCreate):
    """Store a new bug memory and auto-generate embedding."""
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


# ── Token Log endpoint ────────────────────────────────────────

@app.post("/token-log")
def create_token_log(data: TokenLogCreate):
    doc = save_token_log(
        project_id=data.project_id,
        query=data.query,
        before_tokens=data.before_tokens,
        after_tokens=data.after_tokens,
    )
    return doc


# ── Debug endpoint ────────────────────────────────────────────

@app.post("/debug", response_model=DebugResponse)
def debug_bug(data: DebugQuery):
    """Generate a memory-powered debugging response."""
    from specmem.backend.llm_service import generate_debug_response
    result = generate_debug_response(
        project_id=data.project_id,
        query=data.query,
        module=data.module,
        file_path=data.file_path,
    )
    return result


# ── Check Fix endpoint ────────────────────────────────────────

@app.post("/check")
def check_fix(data: CheckFixRequest):
    """Check if a proposed fix has been tried and failed before."""
    from specmem.backend.retrieval_service import detect_failed_fix
    match = detect_failed_fix(
        project_id=data.project_id,
        proposed_fix=data.proposed_fix,
        module=data.module,
    )
    if match:
        return {
            "warning": f"This fix was already tried and failed: '{match.get('bug_title', 'unknown bug')}'",
            "matched_failed_fix": match,
        }
    return {"warning": None, "matched_failed_fix": None}
