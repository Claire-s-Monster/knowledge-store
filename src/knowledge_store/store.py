"""ChromaDB store operations.

Handles all interactions with ChromaDB for knowledge entry storage and retrieval.
"""

import uuid
from collections import Counter
from collections.abc import Mapping
from datetime import datetime
from typing import Any

import chromadb
import structlog
from chromadb.api.types import IncludeEnum
from chromadb.config import Settings as ChromaSettings

from .config import settings
from .models import EntryResult, KnowledgeEntry, SearchResult, StoreStats

logger = structlog.get_logger(__name__)


class KnowledgeStore:
    """ChromaDB-based knowledge store."""

    def __init__(self) -> None:
        """Initialize the knowledge store."""
        settings.ensure_dirs()

        self._client = chromadb.PersistentClient(
            path=str(settings.chroma_persist_dir),
            settings=ChromaSettings(
                anonymized_telemetry=False,
                allow_reset=True,
            ),
        )

        self._collection = self._client.get_or_create_collection(
            name=settings.chroma_collection_name,
            metadata={"hnsw:space": "cosine"},
        )

        logger.info(
            "knowledge_store_initialized",
            collection=settings.chroma_collection_name,
            entry_count=self._collection.count(),
        )

    def add_entry(
        self,
        problem_pattern: str,
        solution: str,
        code_example: str | None = None,
        tags: list[str] | None = None,
        pattern_type: str = "bugfix",
        source_session: str | None = None,
        source_type: str = "session",
    ) -> EntryResult:
        """Add a new knowledge entry."""
        entry_id = str(uuid.uuid4())
        now = datetime.utcnow()

        entry = KnowledgeEntry(
            id=entry_id,
            problem_pattern=problem_pattern,
            solution=solution,
            code_example=code_example,
            tags=tags or [],
            pattern_type=pattern_type,
            source_session=source_session,
            source_type=source_type,
            created_at=now,
            updated_at=now,
        )

        try:
            self._collection.add(
                ids=[entry_id],
                documents=[entry.to_document()],
                metadatas=[entry.to_metadata()],  # type: ignore[list-item]
            )

            logger.info("entry_added", entry_id=entry_id, tags=tags)
            return EntryResult(success=True, entry_id=entry_id, entry=entry)

        except Exception as e:
            logger.error("entry_add_failed", error=str(e))
            return EntryResult(success=False, message=str(e))

    def get_entry(self, entry_id: str) -> KnowledgeEntry | None:
        """Retrieve an entry by ID."""
        try:
            result = self._collection.get(
                ids=[entry_id],
                include=[IncludeEnum.documents, IncludeEnum.metadatas],
            )

            if not result["ids"]:
                return None

            metadata = result["metadatas"][0] if result["metadatas"] else {}
            return self._metadata_to_entry(
                metadata, result["documents"][0] if result["documents"] else ""
            )

        except Exception as e:
            logger.error("entry_get_failed", entry_id=entry_id, error=str(e))
            return None

    def update_entry(self, entry_id: str, updates: dict[str, Any]) -> EntryResult:
        """Update an existing entry (partial update)."""
        # Immutable fields that cannot be updated
        immutable = {
            "id",
            "problem_pattern",
            "solution",
            "code_example",
            "created_at",
            "source_session",
            "source_type",
        }
        invalid_keys = set(updates.keys()) & immutable
        if invalid_keys:
            return EntryResult(
                success=False,
                message=f"Cannot update immutable fields: {invalid_keys}",
            )

        existing = self.get_entry(entry_id)
        if not existing:
            return EntryResult(success=False, message="Entry not found")

        try:
            # Apply updates
            entry_dict = existing.model_dump()
            entry_dict.update(updates)
            entry_dict["updated_at"] = datetime.utcnow()

            updated_entry = KnowledgeEntry(**entry_dict)

            self._collection.update(
                ids=[entry_id],
                metadatas=[updated_entry.to_metadata()],  # type: ignore[list-item]
            )

            logger.info(
                "entry_updated", entry_id=entry_id, updates=list(updates.keys())
            )
            return EntryResult(success=True, entry_id=entry_id, entry=updated_entry)

        except Exception as e:
            logger.error("entry_update_failed", entry_id=entry_id, error=str(e))
            return EntryResult(success=False, message=str(e))

    def delete_entry(self, entry_id: str) -> bool:
        """Delete an entry by ID."""
        try:
            self._collection.delete(ids=[entry_id])
            logger.info("entry_deleted", entry_id=entry_id)
            return True
        except Exception as e:
            logger.error("entry_delete_failed", entry_id=entry_id, error=str(e))
            return False

    def search(
        self,
        query: str,
        limit: int | None = None,
        filters: dict[str, Any] | None = None,
    ) -> list[SearchResult]:
        """Semantic search for entries.

        Args:
            query: Search query text.
            limit: Max results to return. Defaults to settings.default_search_limit.
            filters: Optional filters to apply.

        Returns:
            List of SearchResult with matching entries and similarity scores.
        """
        if limit is None:
            limit = settings.default_search_limit

        where_clause = self._build_where_clause(filters) if filters else None

        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=limit,
                where=where_clause,
                include=[IncludeEnum.documents, IncludeEnum.metadatas, IncludeEnum.distances],
            )

            search_results = []
            if results["ids"] and results["ids"][0]:
                for i, _entry_id in enumerate(results["ids"][0]):
                    metadata = (
                        results["metadatas"][0][i] if results["metadatas"] else {}
                    )
                    document = (
                        results["documents"][0][i] if results["documents"] else ""
                    )
                    distance = (
                        results["distances"][0][i] if results["distances"] else 1.0
                    )

                    entry = self._metadata_to_entry(metadata, document)
                    if entry:
                        # Convert cosine distance to similarity (1 - distance)
                        similarity = max(0.0, min(1.0, 1.0 - distance))
                        search_results.append(
                            SearchResult(entry=entry, similarity_score=similarity)
                        )

            logger.info(
                "search_completed", query_length=len(query), results=len(search_results)
            )
            return search_results

        except Exception as e:
            logger.error("search_failed", error=str(e))
            return []

    def find_similar(
        self,
        entry_id: str,
        threshold: float | None = None,
        limit: int | None = None,
    ) -> list[SearchResult]:
        """Find entries similar to the specified entry.

        Args:
            entry_id: ID of the source entry to find similar entries for.
            threshold: Minimum similarity score. Defaults to settings.default_similarity_threshold.
            limit: Max results to return. Defaults to settings.default_search_limit.

        Returns:
            List of SearchResult with similar entries (excludes the source entry).
        """
        if threshold is None:
            threshold = settings.default_similarity_threshold
        if limit is None:
            limit = settings.default_search_limit

        entry = self.get_entry(entry_id)
        if not entry:
            return []

        # Search using the entry's document as query
        results = self.search(entry.to_document(), limit=limit + 1)

        # Filter out the source entry and apply threshold
        return [
            r
            for r in results
            if r.entry.id != entry_id and r.similarity_score >= threshold
        ]

    def list_entries(
        self,
        filters: dict[str, Any] | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[KnowledgeEntry]:
        """List entries with optional filtering."""
        where_clause = self._build_where_clause(filters) if filters else None

        try:
            # ChromaDB doesn't have native offset, so we fetch more and slice
            results = self._collection.get(
                where=where_clause,
                limit=limit + offset,
                include=[IncludeEnum.documents, IncludeEnum.metadatas],
            )

            entries = []
            if results["ids"]:
                for i, _entry_id in enumerate(results["ids"]):
                    if i < offset:
                        continue
                    metadata = results["metadatas"][i] if results["metadatas"] else {}
                    document = results["documents"][i] if results["documents"] else ""
                    entry = self._metadata_to_entry(metadata, document)
                    if entry:
                        entries.append(entry)

            return entries

        except Exception as e:
            logger.error("list_entries_failed", error=str(e))
            return []

    def get_stats(self) -> StoreStats:
        """Get collection statistics."""
        try:
            all_entries = self.list_entries(limit=100000)

            status_counts: Counter[str] = Counter()
            type_counts: Counter[str] = Counter()
            tag_counts: Counter[str] = Counter()
            quality_scores: list[float] = []

            for entry in all_entries:
                status_counts[entry.status] += 1
                type_counts[entry.pattern_type] += 1
                quality_scores.append(entry.quality_score)
                for tag in entry.tags:
                    tag_counts[tag] += 1

            avg_quality = (
                sum(quality_scores) / len(quality_scores) if quality_scores else 0.0
            )

            return StoreStats(
                total_entries=len(all_entries),
                entries_by_status=dict(status_counts),
                entries_by_type=dict(type_counts),
                avg_quality_score=avg_quality,
                top_tags=tag_counts.most_common(10),
            )

        except Exception as e:
            logger.error("get_stats_failed", error=str(e))
            return StoreStats(
                total_entries=0,
                entries_by_status={},
                entries_by_type={},
                avg_quality_score=0.0,
                top_tags=[],
            )

    def _build_where_clause(self, filters: dict[str, Any]) -> dict[str, Any] | None:
        """Build ChromaDB where clause from filters."""
        if not filters:
            return None

        conditions = []
        for key, value in filters.items():
            if isinstance(value, dict):
                # Handle operator syntax: {"$gte": 0.5}
                for op, val in value.items():
                    if op == "$contains" and key == "tags":
                        # Tags are stored as comma-separated string
                        conditions.append({key: {"$contains": val}})
                    else:
                        conditions.append({key: {op: val}})
            else:
                conditions.append({key: {"$eq": value}})

        if len(conditions) == 1:
            return conditions[0]
        return {"$and": conditions}

    def _metadata_to_entry(
        self, metadata: Mapping[str, Any], document: str
    ) -> KnowledgeEntry | None:
        """Convert ChromaDB metadata back to KnowledgeEntry."""
        try:
            # Parse document back into components
            parts = document.split("\n\n")
            problem_pattern = parts[0] if parts else ""
            solution = parts[1] if len(parts) > 1 else ""
            code_example = parts[2] if len(parts) > 2 else None

            # Parse tags from comma-separated string
            tags_str = metadata.get("tags", "")
            tags = [t.strip() for t in tags_str.split(",") if t.strip()]

            # Parse datetime fields
            created_at = datetime.fromisoformat(
                metadata.get("created_at", datetime.utcnow().isoformat())
            )
            updated_at = datetime.fromisoformat(
                metadata.get("updated_at", datetime.utcnow().isoformat())
            )
            last_applied_str = metadata.get("last_applied_at", "")
            last_applied_at = (
                datetime.fromisoformat(last_applied_str) if last_applied_str else None
            )

            return KnowledgeEntry(
                id=metadata.get("id", ""),
                problem_pattern=problem_pattern,
                solution=solution,
                code_example=code_example if code_example else None,
                tags=tags,
                pattern_type=metadata.get("pattern_type", "bugfix"),
                quality_score=float(metadata.get("quality_score", 0.5)),
                times_applied=int(metadata.get("times_applied", 0)),
                success_count=int(metadata.get("success_count", 0)),
                failure_count=int(metadata.get("failure_count", 0)),
                status=metadata.get("status", "active"),
                superseded_by=metadata.get("superseded_by") or None,
                source_session=metadata.get("source_session") or None,
                source_type=metadata.get("source_type", "session"),
                created_at=created_at,
                updated_at=updated_at,
                last_applied_at=last_applied_at,
            )

        except Exception as e:
            logger.error("metadata_parse_failed", error=str(e))
            return None
