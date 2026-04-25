"""
SpecMem memory service — CRUD for bug memories and token logs.

All functions return plain dicts with "id" (string) instead of "_id" (ObjectId).
Person 2 imports these directly.
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
    """Convert a raw Mongo document to an API-safe dict.

    * Renames ``_id`` → ``id`` and converts ObjectId to str.
    * Recursively converts any remaining ObjectId values.
    """
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


# ── Bug Memory CRUD ───────────────────────────────────────────

def create_bug_memory(
    data: BugMemoryCreate,
    embedding: list[float] | None = None,
) -> dict:
    """Insert a new bug memory and return the cleaned document."""
    doc = data.model_dump()
    doc["created_at"] = datetime.now(timezone.utc)
    doc["embedding"] = embedding or []

    result = _col().insert_one(doc)
    doc["_id"] = result.inserted_id
    return clean_mongo_doc(doc)


def get_bug_memory_by_id(memory_id: str) -> dict | None:
    """Fetch a single bug memory by its id string."""
    try:
        doc = _col().find_one({"_id": ObjectId(memory_id)})
    except Exception:
        return None
    return clean_mongo_doc(doc) if doc else None


def list_bug_memories(project_id: str, limit: int = 20) -> list[dict]:
    """Return the most recent bug memories for a project."""
    cursor = (
        _col()
        .find({"project_id": project_id})
        .sort("created_at", -1)
        .limit(limit)
    )
    return [clean_mongo_doc(d) for d in cursor]


def search_bug_memories_by_keyword(
    project_id: str,
    query: str,
    limit: int = 5,
) -> list[dict]:
    """Simple keyword/regex search across text fields.

    Used as a fallback when vector search is unavailable.
    """
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
) -> dict | None:
    """Set the embedding vector on an existing bug memory."""
    try:
        oid = ObjectId(memory_id)
    except Exception:
        return None

    result = _col().find_one_and_update(
        {"_id": oid},
        {"$set": {"embedding": embedding}},
        return_document=True,
    )
    return clean_mongo_doc(result) if result else None


# ── Token Logs ────────────────────────────────────────────────

def save_token_log(
    project_id: str,
    query: str,
    before_tokens: int,
    after_tokens: int,
) -> dict:
    """Record a token-usage log entry."""
    doc = {
        "project_id": project_id,
        "query": query,
        "before_tokens": before_tokens,
        "after_tokens": after_tokens,
        "savings_percent": round(
            (1 - after_tokens / max(before_tokens, 1)) * 100, 2
        ),
        "created_at": datetime.now(timezone.utc),
    }
    result = _col("token_logs").insert_one(doc)
    doc["_id"] = result.inserted_id
    return clean_mongo_doc(doc)
