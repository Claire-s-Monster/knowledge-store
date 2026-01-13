"""Tests for KnowledgeStore ChromaDB operations."""

from knowledge_store.store import KnowledgeStore


class TestKnowledgeStoreAdd:
    """Tests for add_entry operation."""

    def test_add_entry_success(
        self, knowledge_store: KnowledgeStore, sample_entry_data: dict
    ) -> None:
        """Test adding a new entry."""
        result = knowledge_store.add_entry(**sample_entry_data)

        assert result.success is True
        assert result.entry_id is not None
        assert result.entry is not None
        assert result.entry.problem_pattern == sample_entry_data["problem_pattern"]
        assert result.entry.tags == sample_entry_data["tags"]

    def test_add_entry_minimal(self, knowledge_store: KnowledgeStore) -> None:
        """Test adding entry with minimal required fields."""
        result = knowledge_store.add_entry(
            problem_pattern="Test problem",
            solution="Test solution",
        )

        assert result.success is True
        assert result.entry is not None
        assert result.entry.pattern_type == "bugfix"  # Default
        assert result.entry.tags == []  # Default


class TestKnowledgeStoreGet:
    """Tests for get_entry operation."""

    def test_get_existing_entry(
        self, knowledge_store: KnowledgeStore, sample_entry_data: dict
    ) -> None:
        """Test retrieving an existing entry."""
        add_result = knowledge_store.add_entry(**sample_entry_data)
        assert add_result.entry_id is not None

        entry = knowledge_store.get_entry(add_result.entry_id)

        assert entry is not None
        assert entry.id == add_result.entry_id
        assert entry.problem_pattern == sample_entry_data["problem_pattern"]

    def test_get_nonexistent_entry(self, knowledge_store: KnowledgeStore) -> None:
        """Test retrieving a non-existent entry."""
        entry = knowledge_store.get_entry("nonexistent-id")
        assert entry is None


class TestKnowledgeStoreUpdate:
    """Tests for update_entry operation."""

    def test_update_allowed_fields(
        self, knowledge_store: KnowledgeStore, sample_entry_data: dict
    ) -> None:
        """Test updating allowed fields."""
        add_result = knowledge_store.add_entry(**sample_entry_data)
        assert add_result.entry_id is not None

        result = knowledge_store.update_entry(
            add_result.entry_id,
            {"quality_score": 0.95, "status": "canonical"},
        )

        assert result.success is True
        assert result.entry is not None
        assert result.entry.quality_score == 0.95
        assert result.entry.status == "canonical"

    def test_update_immutable_fields_rejected(
        self, knowledge_store: KnowledgeStore, sample_entry_data: dict
    ) -> None:
        """Test that immutable fields cannot be updated."""
        add_result = knowledge_store.add_entry(**sample_entry_data)
        assert add_result.entry_id is not None

        result = knowledge_store.update_entry(
            add_result.entry_id,
            {"problem_pattern": "New pattern"},  # Immutable
        )

        assert result.success is False
        assert "immutable" in result.message.lower()

    def test_update_nonexistent_entry(self, knowledge_store: KnowledgeStore) -> None:
        """Test updating a non-existent entry."""
        result = knowledge_store.update_entry("nonexistent-id", {"status": "archived"})
        assert result.success is False


class TestKnowledgeStoreDelete:
    """Tests for delete_entry operation."""

    def test_delete_existing_entry(
        self, knowledge_store: KnowledgeStore, sample_entry_data: dict
    ) -> None:
        """Test deleting an existing entry."""
        add_result = knowledge_store.add_entry(**sample_entry_data)
        assert add_result.entry_id is not None

        success = knowledge_store.delete_entry(add_result.entry_id)
        assert success is True

        # Verify entry is gone
        entry = knowledge_store.get_entry(add_result.entry_id)
        assert entry is None


class TestKnowledgeStoreSearch:
    """Tests for search operations."""

    def test_semantic_search(self, knowledge_store: KnowledgeStore) -> None:
        """Test semantic search returns relevant results."""
        # Add some entries
        knowledge_store.add_entry(
            problem_pattern="Python import errors with relative imports",
            solution="Use absolute imports or fix package structure",
            tags=["python", "imports"],
        )
        knowledge_store.add_entry(
            problem_pattern="pytest async test failures",
            solution="Use pytest-asyncio and async fixtures",
            tags=["pytest", "async"],
        )

        # Search for related content
        results = knowledge_store.search("python import problems", limit=5)

        assert len(results) > 0
        assert any("import" in r.entry.problem_pattern.lower() for r in results)

    def test_search_with_filters(
        self, knowledge_store: KnowledgeStore, sample_entry_data: dict
    ) -> None:
        """Test search with metadata filters."""
        knowledge_store.add_entry(**sample_entry_data)

        results = knowledge_store.search(
            "pytest",
            filters={"pattern_type": "bugfix"},
        )

        assert all(r.entry.pattern_type == "bugfix" for r in results)


class TestKnowledgeStoreFindSimilar:
    """Tests for find_similar operation."""

    def test_find_similar_entries(self, knowledge_store: KnowledgeStore) -> None:
        """Test finding similar entries."""
        # Add similar entries
        result1 = knowledge_store.add_entry(
            problem_pattern="pytest fixtures not found",
            solution="Check conftest.py location",
            tags=["pytest"],
        )
        # Add second entry to have something similar to find (result intentionally unused)
        knowledge_store.add_entry(
            problem_pattern="pytest fixtures missing from conftest",
            solution="Verify conftest.py is in test directory",
            tags=["pytest"],
        )

        assert result1.entry_id is not None

        similar = knowledge_store.find_similar(result1.entry_id, threshold=0.5)

        # Should find the similar entry but not itself
        assert all(r.entry.id != result1.entry_id for r in similar)


class TestKnowledgeStoreStats:
    """Tests for get_stats operation."""

    def test_empty_store_stats(self, knowledge_store: KnowledgeStore) -> None:
        """Test stats on empty store."""
        stats = knowledge_store.get_stats()

        assert stats.total_entries == 0
        assert stats.avg_quality_score == 0.0

    def test_stats_with_entries(
        self, knowledge_store: KnowledgeStore, sample_entry_data: dict
    ) -> None:
        """Test stats with entries."""
        knowledge_store.add_entry(**sample_entry_data)
        knowledge_store.add_entry(
            problem_pattern="Another problem",
            solution="Another solution",
            pattern_type="optimization",
        )

        stats = knowledge_store.get_stats()

        assert stats.total_entries == 2
        assert "bugfix" in stats.entries_by_type
        assert "optimization" in stats.entries_by_type
