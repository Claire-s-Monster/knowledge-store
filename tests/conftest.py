"""Pytest fixtures for knowledge-store tests."""

import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest

from knowledge_store.config import Settings, settings
from knowledge_store.store import KnowledgeStore


@pytest.fixture
def temp_chroma_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for ChromaDB."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_settings(temp_chroma_dir: Path) -> Settings:
    """Create test settings with temporary storage."""
    return Settings(
        chroma_persist_dir=temp_chroma_dir,
        chroma_collection_name="test_knowledge_patterns",
    )


@pytest.fixture
def knowledge_store(test_settings: Settings, monkeypatch: pytest.MonkeyPatch) -> KnowledgeStore:
    """Create a KnowledgeStore with test settings."""
    # Patch the global settings
    monkeypatch.setattr("knowledge_store.store.settings", test_settings)
    monkeypatch.setattr("knowledge_store.config.settings", test_settings)
    return KnowledgeStore()


@pytest.fixture
def sample_entry_data() -> dict:
    """Sample entry data for testing."""
    return {
        "problem_pattern": "pytest fixtures not loading from conftest.py",
        "solution": "Ensure conftest.py is in the test root and check __init__.py files",
        "code_example": "# conftest.py\nimport pytest\n\n@pytest.fixture\ndef my_fixture():\n    return 'value'",
        "tags": ["pytest", "fixtures", "testing"],
        "pattern_type": "bugfix",
        "source_type": "direct",
    }
