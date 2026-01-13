"""Vulture whitelist for false positives.

This file tells vulture which names are actually used (via frameworks,
serialization, etc.) even though vulture can't detect their usage.

Run vulture with: vulture src/ tests/ vulture_whitelist.py --min-confidence 60
"""

# Pydantic BaseSettings - model_config is a required class variable
_.model_config  # type: ignore

# Config field reserved for future custom embedding support
_.embedding_model  # type: ignore

# Pydantic model fields - used in JSON serialization via model_dump()
_.entries_by_status  # type: ignore
_.top_tags  # type: ignore
_.description  # type: ignore
_.category  # type: ignore
_.examples  # type: ignore

# Starlette lifecycle hooks - registered via @app.on_event() decorator
_.startup  # type: ignore
_.shutdown  # type: ignore
