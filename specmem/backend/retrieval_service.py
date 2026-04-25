"""
SpecMem retrieval service — Gemini embeddings + MongoDB vector search.
"""

from google import genai

from specmem.backend.config import GEMINI_API_KEY
from specmem.backend.database import get_db
from specmem.backend.memory_service import (
    clean_mongo_doc,
    get_bug_memory_by_id,
    search_bug_memories_by_keyword,
    update_memory_embedding,
)

_client: genai.Client | None = None


def get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def create_embedding(text: str) -> list[float]:
    result = get_client().models.embed_content(
        model="gemini-embedding-001",
        contents=text,
    )
    return list(result.embeddings[0].values)


def build_embedding_text(memory: dict) -> str:
    parts = [
        memory.get("bug_title", ""),
        memory.get("description", ""),
        " ".join(memory.get("failed_fixes", [])),
        memory.get("root_cause", ""),
        memory.get("final_fix", ""),
        memory.get("module", ""),
        memory.get("file_path", ""),
        " ".join(memory.get("tags", [])),
    ]
    return " | ".join(p for p in parts if p)


def add_embedding_to_memory(memory_id: str) -> dict:
    """Generate and store embedding for an existing bug memory."""
    memory = get_bug_memory_by_id(memory_id)
    if not memory:
        return {}
    text = build_embedding_text(memory)
    embedding = create_embedding(text)
    return update_memory_embedding(memory_id, embedding) or {}


def retrieve_similar_bugs(
    project_id: str,
    query: str,
    module: str | None = None,
    file_path: str | None = None,
    limit: int = 5,
) -> list[dict]:
    """Retrieve similar bugs via vector search, falling back to keyword search."""
    try:
        query_embedding = create_embedding(query)
        db = get_db()

        match_filter: dict = {"project_id": project_id}
        if module:
            match_filter["module"] = module
        if file_path:
            match_filter["file_path"] = file_path

        pipeline = [
            {
                "$vectorSearch": {
                    "index": "vector_index",
                    "path": "embedding",
                    "queryVector": query_embedding,
                    "numCandidates": limit * 10,
                    "limit": limit * 2,
                }
            },
            {"$match": match_filter},
            {"$limit": limit},
        ]

        results = list(db["bug_memories"].aggregate(pipeline))
        if results:
            return [clean_mongo_doc(d) for d in results]
    except Exception as e:
        print(f"[vector search] fallback to keyword: {e}")

    return search_bug_memories_by_keyword(project_id, query, limit=limit)


def detect_failed_fix(
    project_id: str,
    proposed_fix: str,
    module: str | None = None,
) -> dict | None:
    """Return the bug memory if the proposed fix matches a known failed fix."""
    try:
        fix_embedding = create_embedding(proposed_fix)
        db = get_db()

        match_filter: dict = {"project_id": project_id}
        if module:
            match_filter["module"] = module

        pipeline = [
            {
                "$vectorSearch": {
                    "index": "vector_index",
                    "path": "embedding",
                    "queryVector": fix_embedding,
                    "numCandidates": 50,
                    "limit": 10,
                }
            },
            {"$match": match_filter},
        ]

        candidates = list(db["bug_memories"].aggregate(pipeline))
        for doc in candidates:
            for ff in doc.get("failed_fixes", []):
                if proposed_fix.lower() in ff.lower() or ff.lower() in proposed_fix.lower():
                    return clean_mongo_doc(doc)
    except Exception as e:
        print(f"[detect_failed_fix] fallback to keyword: {e}")

    # Keyword fallback
    candidates = search_bug_memories_by_keyword(project_id, proposed_fix, limit=10)
    for doc in candidates:
        for ff in doc.get("failed_fixes", []):
            if proposed_fix.lower() in ff.lower() or ff.lower() in proposed_fix.lower():
                return doc

    return None
