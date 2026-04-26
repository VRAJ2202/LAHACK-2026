"""
SpecMem memory service — CRUD for bug memories, debug episodes, and token logs.

All functions return plain dicts with "id" (string) instead of "_id" (ObjectId).
"""

import re
from datetime import datetime, timezone

from bson import ObjectId
from pymongo.collection import Collection

from specmem.backend.database import get_db
from specmem.backend.schemas import BugMemoryCreate


# ── Helpers ────────────────────────────────────────────────────

def _col(name: str = "bug_memories") -> Collection:
    return get_db()[name]


def clean_mongo_doc(doc: dict) -> dict:
    """Convert a raw Mongo document to an API-safe dict."""
    if doc is None:
        return {}
    out: dict = {}
    for key, value in doc.items():
        new_key = "id" if key == "_id" else key
        if isinstance(value, ObjectId):
            out[new_key] = str(value)
        elif isinstance(value, dict):
            out[new_key] = clean_mongo_doc(value)
        elif isinstance(value, list):
            out[new_key] = [
                clean_mongo_doc(v) if isinstance(v, dict)
                else str(v) if isinstance(v, ObjectId)
                else v
                for v in value
            ]
        else:
            out[new_key] = value
    return out


# ── Bug Memory CRUD (legacy manual) ───────────────────────────

def create_bug_memory(
    data: BugMemoryCreate,
    embedding: list[float] | None = None,
) -> dict:
    doc = data.model_dump()
    doc["created_at"] = datetime.now(timezone.utc)
    doc["embedding"] = embedding or []
    doc["failed_fix_embeddings"] = []
    result = _col().insert_one(doc)
    doc["_id"] = result.inserted_id
    return clean_mongo_doc(doc)


def get_bug_memory_by_id(memory_id: str) -> dict | None:
    try:
        doc = _col().find_one({"_id": ObjectId(memory_id)})
    except Exception:
        return None
    return clean_mongo_doc(doc) if doc else None


def list_bug_memories(project_id: str, limit: int = 20) -> list[dict]:
    cursor = (
        _col()
        .find({"project_id": project_id})
        .sort("created_at", -1)
        .limit(limit)
    )
    return [clean_mongo_doc(d) for d in cursor]


def search_bug_memories_by_keyword(
    project_id: str, query: str, limit: int = 5,
) -> list[dict]:
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    filter_q = {
        "project_id": project_id,
        "$or": [
            {"bug_title": pattern},
            {"description": pattern},
            {"root_cause": pattern},
            {"final_fix": pattern},
            {"tags": pattern},
            {"module": pattern},
        ],
    }
    cursor = _col().find(filter_q).sort("created_at", -1).limit(limit)
    return [clean_mongo_doc(d) for d in cursor]


def update_memory_embedding(
    memory_id: str,
    embedding: list[float],
    failed_fix_embeddings: list[list[float]] | None = None,
) -> dict | None:
    try:
        oid = ObjectId(memory_id)
    except Exception:
        return None
    update_fields: dict = {"embedding": embedding}
    if failed_fix_embeddings is not None:
        update_fields["failed_fix_embeddings"] = failed_fix_embeddings
    result = _col().find_one_and_update(
        {"_id": oid}, {"$set": update_fields}, return_document=True,
    )
    return clean_mongo_doc(result) if result else None


def update_memory_feedback(
    memory_id: str, fix_worked: bool, notes: str | None = None,
) -> dict | None:
    try:
        oid = ObjectId(memory_id)
    except Exception:
        return None
    memory = _col().find_one({"_id": oid})
    if not memory:
        return None
    update: dict = {"$set": {"fix_worked": fix_worked}}
    if notes:
        update["$set"]["feedback_notes"] = notes
    if not fix_worked and memory.get("final_fix"):
        update["$addToSet"] = {"failed_fixes": memory["final_fix"]}
        update["$set"]["final_fix"] = ""
    result = _col().find_one_and_update({"_id": oid}, update, return_document=True)
    return clean_mongo_doc(result) if result else None


# ── Debug Episode CRUD (automatic capture) ────────────────────

def create_debug_episode(
    project_id: str,
    command: str,
    error_message: str,
    stack_trace: str,
    error_type: str,
    file_paths: list[str],
    module: str = "",
    embedding: list[float] | None = None,
) -> dict:
    """Create a new debug episode from an automatically captured error."""
    doc = {
        "project_id": project_id,
        "command": command,
        "error_message": error_message,
        "stack_trace": stack_trace,
        "error_type": error_type,
        "file_paths": file_paths,
        "module": module,
        "failed_fixes": [],
        "successful_fix": None,
        "status": "open",
        "ai_suggestion": "",
        "similar_episodes": [],
        "embedding": embedding or [],
        "created_at": datetime.now(timezone.utc),
    }
    result = _col("debug_episodes").insert_one(doc)
    doc["_id"] = result.inserted_id
    return clean_mongo_doc(doc)


def get_episode_by_id(episode_id: str) -> dict | None:
    try:
        doc = _col("debug_episodes").find_one({"_id": ObjectId(episode_id)})
    except Exception:
        return None
    return clean_mongo_doc(doc) if doc else None


def get_latest_open_episode(project_id: str) -> dict | None:
    """Get the most recent open episode for a project."""
    doc = (
        _col("debug_episodes")
        .find({"project_id": project_id, "status": {"$in": ["open", "fixing"]}})
        .sort("created_at", -1)
        .limit(1)
    )
    docs = list(doc)
    return clean_mongo_doc(docs[0]) if docs else None


def list_episodes(project_id: str, limit: int = 20) -> list[dict]:
    cursor = (
        _col("debug_episodes")
        .find({"project_id": project_id})
        .sort("created_at", -1)
        .limit(limit)
    )
    return [clean_mongo_doc(d) for d in cursor]


def add_failed_fix_to_episode(episode_id: str, diff: str, error_after: str) -> dict | None:
    """Record a failed fix attempt on an episode."""
    try:
        oid = ObjectId(episode_id)
    except Exception:
        return None
    fix_entry = {
        "diff": diff,
        "error_after": error_after,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    result = _col("debug_episodes").find_one_and_update(
        {"_id": oid},
        {
            "$push": {"failed_fixes": fix_entry},
            "$set": {"status": "fixing"},
        },
        return_document=True,
    )
    return clean_mongo_doc(result) if result else None


def resolve_episode(episode_id: str, diff: str) -> dict | None:
    """Mark an episode as resolved with the successful fix."""
    try:
        oid = ObjectId(episode_id)
    except Exception:
        return None
    fix_entry = {
        "diff": diff,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    result = _col("debug_episodes").find_one_and_update(
        {"_id": oid},
        {"$set": {"successful_fix": fix_entry, "status": "resolved"}},
        return_document=True,
    )
    return clean_mongo_doc(result) if result else None


def update_episode_ai_suggestion(episode_id: str, suggestion: str, similar: list[dict]) -> dict | None:
    """Store the AI suggestion and similar episodes on an episode."""
    try:
        oid = ObjectId(episode_id)
    except Exception:
        return None
    result = _col("debug_episodes").find_one_and_update(
        {"_id": oid},
        {"$set": {"ai_suggestion": suggestion, "similar_episodes": similar}},
        return_document=True,
    )
    return clean_mongo_doc(result) if result else None


def update_episode_embedding(episode_id: str, embedding: list[float]) -> dict | None:
    """Store the embedding vector on a debug episode."""
    try:
        oid = ObjectId(episode_id)
    except Exception:
        return None
    result = _col("debug_episodes").find_one_and_update(
        {"_id": oid},
        {"$set": {"embedding": embedding}},
        return_document=True,
    )
    return clean_mongo_doc(result) if result else None


def search_episodes_by_keyword(
    project_id: str, query: str, limit: int = 5,
) -> list[dict]:
    pattern = re.compile(re.escape(query), re.IGNORECASE)
    filter_q = {
        "project_id": project_id,
        "$or": [
            {"error_message": pattern},
            {"error_type": pattern},
            {"stack_trace": pattern},
            {"command": pattern},
        ],
    }
    cursor = _col("debug_episodes").find(filter_q).sort("created_at", -1).limit(limit)
    return [clean_mongo_doc(d) for d in cursor]


# ── Token Logs ────────────────────────────────────────────────

def save_token_log(
    project_id: str, query: str, before_tokens: int, after_tokens: int,
) -> dict:
    doc = {
        "project_id": project_id,
        "query": query,
        "before_tokens": before_tokens,
        "after_tokens": after_tokens,
        "savings_percent": round((1 - after_tokens / max(before_tokens, 1)) * 100, 2),
        "created_at": datetime.now(timezone.utc),
    }
    result = _col("token_logs").insert_one(doc)
    doc["_id"] = result.inserted_id
    return clean_mongo_doc(doc)
