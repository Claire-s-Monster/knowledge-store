"""Configuration for knowledge-store.

Environment-based configuration using pydantic-settings.
"""

import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_data_dir() -> Path:
    """Get XDG-compliant default data directory."""
    xdg_data = os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share"))
    return Path(xdg_data) / "knowledge-store" / "chromadb"


class Settings(BaseSettings):
    """Application settings loaded from environment."""

    model_config = SettingsConfigDict(
        env_prefix="KNOWLEDGE_STORE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # Ignore unknown env vars
    )

    # Server
    host: str = "127.0.0.1"
    port: int = 4004

    # ChromaDB
    chroma_persist_dir: Path = _default_data_dir()
    chroma_collection_name: str = "knowledge_patterns"

    # Embedding model name (reserved for future custom embedding support)
    # Currently ChromaDB uses all-MiniLM-L6-v2 by default
    # TODO: Implement custom embedding function when needed
    embedding_model: str = "all-MiniLM-L6-v2"

    # Logging
    log_level: str = "INFO"

    # Search defaults
    default_search_limit: int = 10
    default_similarity_threshold: float = 0.85

    def ensure_dirs(self) -> None:
        """Ensure required directories exist."""
        self.chroma_persist_dir.mkdir(parents=True, exist_ok=True)


# Global settings instance
settings = Settings()
