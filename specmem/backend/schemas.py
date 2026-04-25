"""
SpecMem Pydantic schemas — shared across all team members.
"""

from datetime import datetime
from pydantic import BaseModel, Field


# ── Bug Memory ────────────────────────────────────────────────

class BugMemoryCreate(BaseModel):
    project_id: str
    bug_title: str
    description: str
    file_path: str
    module: str
    failed_fixes: list[str] = Field(default_factory=list)
    root_cause: str
    final_fix: str
    tags: list[str] = Field(default_factory=list)


class BugMemoryResponse(BaseModel):
    id: str
    project_id: str
    bug_title: str
    description: str
    file_path: str
    module: str
    failed_fixes: list[str] = Field(default_factory=list)
    root_cause: str
    final_fix: str
    tags: list[str] = Field(default_factory=list)
    created_at: datetime


# ── Debug Query / Response ────────────────────────────────────

class DebugQuery(BaseModel):
    project_id: str
    query: str
    file_path: str | None = None
    module: str | None = None


class DebugResponse(BaseModel):
    answer: str
    similar_bugs: list[dict] = Field(default_factory=list)
    failed_fix_warning: str | None = None
    token_savings: dict | None = None


# ── Check Fix ─────────────────────────────────────────────────

class CheckFixRequest(BaseModel):
    project_id: str
    proposed_fix: str
    module: str | None = None


# ── Token Log ─────────────────────────────────────────────────

class TokenLogCreate(BaseModel):
    project_id: str
    query: str
    before_tokens: int
    after_tokens: int
