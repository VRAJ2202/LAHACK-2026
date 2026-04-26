"""
SpecMem database — MongoDB Atlas connection and index setup.
"""

from pymongo import MongoClient, ASCENDING, DESCENDING
from pymongo.database import Database

from specmem.backend.config import MONGODB_URI, MONGODB_DB_NAME

_client: MongoClient | None = None


def get_client() -> MongoClient:
    """Return a singleton MongoClient."""
    global _client
    if _client is None:
        _client = MongoClient(MONGODB_URI)
    return _client


def get_db() -> Database:
    """Return the SpecMem database handle."""
    return get_client()[MONGODB_DB_NAME]


def ensure_indexes() -> None:
    """Create indexes on all collections."""
    db = get_db()

    # bug_memories indexes (legacy manual memories)
    col = db["bug_memories"]
    col.create_index([("project_id", ASCENDING)])
    col.create_index([("module", ASCENDING)])
    col.create_index([("file_path", ASCENDING)])
    col.create_index([("tags", ASCENDING)])
    col.create_index([("created_at", DESCENDING)])
    col.create_index([("project_id", ASCENDING), ("created_at", DESCENDING)])

    # debug_episodes indexes (automatic capture)
    ep = db["debug_episodes"]
    ep.create_index([("project_id", ASCENDING)])
    ep.create_index([("status", ASCENDING)])
    ep.create_index([("error_type", ASCENDING)])
    ep.create_index([("created_at", DESCENDING)])
    ep.create_index([("project_id", ASCENDING), ("status", ASCENDING)])
    ep.create_index([("project_id", ASCENDING), ("created_at", DESCENDING)])


def ping() -> bool:
    """Return True if MongoDB is reachable."""
    try:
        get_client().admin.command("ping")
        return True
    except Exception:
        return False
