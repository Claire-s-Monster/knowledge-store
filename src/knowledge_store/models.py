"""Pydantic models for knowledge-store.

Data models for knowledge entries, search results, and statistics.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class KnowledgeEntry(BaseModel):
    """A single knowledge entry stored in ChromaDB."""

    # Identity
    id: str = Field(description="UUID for the entry")

    # Content (embedded for search)
    problem_pattern: str = Field(description="What problem this solves")
    solution: str = Field(description="The solution/pattern")
    code_example: str | None = Field(default=None, description="Optional code snippet")

    # Classification
    tags: list[str] = Field(default_factory=list, description="e.g., ['python', 'pytest', 'async']")
    pattern_type: Literal[
        "bugfix",
        "best_practice",
        "optimization",
        "setup",
        "architecture",
    ] = Field(default="bugfix", description="Type of pattern")

    # Quality metrics (updated by curator)
    times_applied: int = Field(default=0, description="Number of times this pattern was applied")
    success_count: int = Field(default=0, description="Successful applications")
    failure_count: int = Field(default=0, description="Failed applications")
    quality_score: float = Field(default=0.5, ge=0.0, le=1.0, description="Quality score 0.0 to 1.0")

    # Lifecycle
    status: Literal[
        "active",
        "canonical",
        "archived",
        "superseded",
    ] = Field(default="active", description="Entry status")
    superseded_by: str | None = Field(default=None, description="Entry ID if superseded")

    # Provenance
    source_session: str | None = Field(default=None, description="session-intelligence session ID")
    source_type: Literal["session", "direct", "seeded"] = Field(
        default="session", description="How entry was created"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_applied_at: datetime | None = Field(default=None)

    def to_document(self) -> str:
        """Combine content fields for embedding."""
        parts = [self.problem_pattern, self.solution]
        if self.code_example:
            parts.append(self.code_example)
        return "\n\n".join(parts)

    def to_metadata(self) -> dict:
        """Extract metadata for ChromaDB storage."""
        return {
            "id": self.id,
            "tags": ",".join(self.tags),  # ChromaDB requires primitive types
            "pattern_type": self.pattern_type,
            "quality_score": self.quality_score,
            "times_applied": self.times_applied,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "status": self.status,
            "superseded_by": self.superseded_by or "",
            "source_session": self.source_session or "",
            "source_type": self.source_type,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "last_applied_at": self.last_applied_at.isoformat() if self.last_applied_at else "",
        }


class SearchResult(BaseModel):
    """Result from semantic search."""

    entry: KnowledgeEntry
    similarity_score: float = Field(ge=0.0, le=1.0, description="Similarity score 0.0 to 1.0")


class EntryResult(BaseModel):
    """Result from CRUD operations."""

    success: bool
    entry_id: str | None = None
    message: str | None = None
    entry: KnowledgeEntry | None = None


class StoreStats(BaseModel):
    """Statistics about the knowledge store."""

    total_entries: int
    entries_by_status: dict[str, int]
    entries_by_type: dict[str, int]
    avg_quality_score: float
    top_tags: list[tuple[str, int]]  # [(tag, count), ...]


class ToolSummary(BaseModel):
    """Summary of an available tool."""

    name: str
    description: str
    category: str


class ToolSpec(BaseModel):
    """Full specification for a tool."""

    name: str
    description: str
    category: str
    parameters: dict
    examples: list[dict] = Field(default_factory=list)
