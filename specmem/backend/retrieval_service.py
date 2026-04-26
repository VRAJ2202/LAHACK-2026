"""
SpecMem retrieval service — Gemini embeddings + MongoDB vector search.
Works with both bug_memories (manual) and debug_episodes (automatic).
"""

from google import genai

from specmem.backend.config import GEMINI_API_KEY
from specmem.backend.database import get_db
from specmem.backend.memory_service import (
    clean_mongo_doc,
    get_bug_memory_by_id,
    search_bug_memories_by_keyword,
    update_memory_embedding,
    search_episodes_by_keyword,
    update_episode_embedding,
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
        " ".join(memory.get("failed_fixes", [])) if isinstance(memory.get("failed_fixes"), list) and all(isinstance(f, str) for f in memory.get("failed_fixes", [])) else "",
        memory.get("root_cause", ""),
        memory.get("final_fix", ""),
        memory.get("module", ""),
        memory.get("file_path", ""),
        " ".join(memory.get("tags", [])),
    ]
    return " | ".join(p for p in parts if p)


def build_episode_embedding_text(episode: dict) -> str:
    """Build embedding text from a debug episode."""
    parts = [
        episode.get("error_type", ""),
        episode.get("error_message", ""),
        episode.get("stack_trace", "")[:500],  # truncate long traces
        episode.get("command", ""),
        " ".join(episode.get("file_paths", [])),
        episode.get("module", ""),
    ]
    return " | ".join(p for p in parts if p)


def add_embedding_to_memory(memory_id: str) -> dict:
    """Generate and store embeddings for a bug memory."""
    memory = get_bug_memory_by_id(memory_id)
    if not memory:
        return {}
    text = build_embedding_text(memory)
    embedding = create_embedding(text)
    failed_fix_embeddings: list[list[float]] = [
        create_embedding(ff)
        for ff in memory.get("failed_fixes", [])
        if isinstance(ff, str) and ff.strip()
    ]
    return update_memory_embedding(memory_id, embedding, failed_fix_embeddings) or {}


def add_embedding_to_episode(episode_id: str, episode: dict) -> dict:
    """Generate and store embedding for a debug episode."""
    text = build_episode_embedding_text(episode)
    embedding = create_embedding(text)
    return update_episode_embedding(episode_id, embedding) or {}


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = sum(x * x for x in a) ** 0.5
    mag_b = sum(x * x for x in b) ** 0.5
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def retrieve_similar_bugs(
    project_id: str,
    query: str,
    module: str | None = None,
    file_path: str | None = None,
    limit: int = 5,
) -> tuple[list[dict], str]:
    """Retrieve similar bugs via vector search with keyword fallback."""
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
            return [clean_mongo_doc(d) for d in results], "vector"
    except Exception as e:
        print(f"[vector search] fallback to keyword: {e}")
    return search_bug_memories_by_keyword(project_id, query, limit=limit), "keyword"


def retrieve_similar_episodes(
    project_id: str,
    query: str,
    limit: int = 5,
) -> tuple[list[dict], str]:
    """Retrieve similar debug episodes via vector search with keyword fallback."""
    try:
        query_embedding = create_embedding(query)
        db = get_db()
        pipeline = [
            {
                "$vectorSearch": {
                    "index": "episode_vector_index",
                    "path": "embedding",
                    "queryVector": query_embedding,
                    "numCandidates": limit * 10,
                    "limit": limit * 2,
                }
            },
            {"$match": {"project_id": project_id}},
            {"$limit": limit},
        ]
        results = list(db["debug_episodes"].aggregate(pipeline))
        if results:
            return [clean_mongo_doc(d) for d in results], "vector"
    except Exception as e:
        print(f"[episode vector search] fallback to keyword: {e}")
    return search_episodes_by_keyword(project_id, query, limit=limit), "keyword"


def detect_failed_fix(
    project_id: str,
    proposed_fix: str,
    module: str | None = None,
    similarity_threshold: float = 0.82,
) -> tuple[dict | None, float]:
    """Detect if a proposed fix semantically matches a known failed fix."""
    try:
        fix_embedding = create_embedding(proposed_fix)
        db = get_db()
        match_filter: dict = {"project_id": project_id, "failed_fixes": {"$ne": []}}
        if module:
            match_filter["module"] = module
        candidates = list(db["bug_memories"].find(match_filter).limit(50))
        best_match: dict | None = None
        best_score = 0.0
        for doc in candidates:
            failed_fixes = doc.get("failed_fixes", [])
            stored_embeddings = doc.get("failed_fix_embeddings", [])
            for i, ff in enumerate(failed_fixes):
                if i < len(stored_embeddings) and stored_embeddings[i]:
                    ff_embedding = stored_embeddings[i]
                else:
                    ff_embedding = create_embedding(ff)
                score = _cosine_similarity(fix_embedding, ff_embedding)
                if score > best_score:
                    best_score = score
                    best_match = doc
        if best_score >= similarity_threshold:
            return clean_mongo_doc(best_match), round(best_score, 3)
    except Exception as e:
        print(f"[detect_failed_fix] fallback to keyword: {e}")

    # Keyword fallback
    candidates = search_bug_memories_by_keyword(project_id, proposed_fix, limit=10)
    for doc in candidates:
        for ff in doc.get("failed_fixes", []):
            if isinstance(ff, str):
                if proposed_fix.lower() in ff.lower() or ff.lower() in proposed_fix.lower():
                    return doc, 1.0
    return None, 0.0
