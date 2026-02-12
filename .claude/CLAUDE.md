# knowledge-store MCP Server

**Project**: knowledge-store
**Version**: 0.1.0
**Port**: 4004 (HTTP transport)
**Storage**: ChromaDB (vector embeddings)
**Status**: Running (systemd user service)

---

## Architecture Context

```
session-intelligence:4002 (PostgreSQL)
         │
         │ learnings
         ▼
knowledge-bridge:4003 (PostgreSQL) ◄──── curator daemon
         │                                    │
         │ promoted entries                   │ similarity queries
         ▼                                    ▼
    knowledge-store:4004 (ChromaDB)  ◄──── THIS PROJECT
```

## Quick Reference

### Service Management
```bash
# Status
systemctl --user status knowledge-store

# Logs
journalctl --user -u knowledge-store -f

# Restart
systemctl --user restart knowledge-store

# Health check
curl http://127.0.0.1:4004/health
```

### Development
```bash
# Install dependencies
pixi install

# Run locally (not via systemd)
pixi run serve

# Run tests
pixi run test

# Quality checks
pixi run quality  # lint + format-check + typecheck
```

---

## MCP Interface (Lean 3-Tool Pattern)

### Meta-Tools
| Tool | Purpose |
|------|---------|
| `discover_tools` | List available tools with filtering |
| `get_tool_spec` | Get full schema for a tool |
| `execute_tool` | Execute a tool with parameters |

### Available Tools (via execute_tool)
| Tool | Category | Purpose |
|------|----------|---------|
| `add_entry` | CRUD | Add new knowledge entry |
| `get_entry` | CRUD | Retrieve by ID |
| `update_entry` | CRUD | Partial update (quality_score, status, tags) |
| `delete_entry` | CRUD | Remove entry (prefer archiving) |
| `search` | Search | Semantic search with filters |
| `find_similar` | Search | Deduplication via similarity |
| `list_entries` | Search | Batch listing with pagination |
| `get_stats` | Analytics | Collection statistics |

### Example: Add Entry
```bash
curl -X POST http://127.0.0.1:4004/mcp \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {
      "name": "execute_tool",
      "arguments": {
        "tool_name": "add_entry",
        "parameters": {
          "problem_pattern": "pytest fixtures not loading",
          "solution": "Check conftest.py location",
          "tags": ["pytest", "fixtures"],
          "pattern_type": "bugfix"
        }
      }
    }
  }'
```

---

## Data Model

### KnowledgeEntry
```python
class KnowledgeEntry:
    id: str                    # UUID
    problem_pattern: str       # What problem this solves
    solution: str              # The solution/pattern
    code_example: str | None   # Optional code snippet
    tags: list[str]            # Classification tags
    pattern_type: Literal["bugfix", "best_practice", "optimization", "setup", "architecture"]

    # Quality metrics
    quality_score: float       # 0.0 to 1.0
    times_applied: int
    success_count: int
    failure_count: int

    # Lifecycle
    status: Literal["active", "canonical", "archived", "superseded"]
    superseded_by: str | None

    # Provenance
    source_session: str | None
    source_type: Literal["session", "direct", "seeded"]
    created_at: datetime
    updated_at: datetime
```

### Immutable Fields (cannot update)
- `id`, `problem_pattern`, `solution`, `code_example`
- `created_at`, `source_session`, `source_type`

### Mutable Fields (can update)
- `quality_score`, `status`, `tags`, `pattern_type`
- `times_applied`, `success_count`, `failure_count`
- `superseded_by`

---

## Project Structure

```
development/
├── src/knowledge_store/
│   ├── __init__.py          # Package (v0.1.0)
│   ├── __main__.py          # Entry point (stdio/http)
│   ├── config.py            # Settings (pydantic-settings)
│   ├── models.py            # Pydantic models
│   ├── store.py             # ChromaDB operations
│   ├── server.py            # MCP server (lean pattern)
│   └── transport/
│       └── http.py          # HTTP transport + REST endpoints
├── tests/
│   ├── conftest.py          # Fixtures (temp ChromaDB)
│   ├── test_store.py        # Store operations
│   └── test_server.py       # MCP + HTTP tests
├── data/chromadb/           # Runtime storage (gitignored)
├── pyproject.toml           # Config + pixi tasks
├── PRD.md                   # Requirements document
└── README.md                # Quick start
```

---

## Configuration

### Environment Variables
| Variable | Default | Description |
|----------|---------|-------------|
| `KNOWLEDGE_STORE_HOST` | 127.0.0.1 | Bind address |
| `KNOWLEDGE_STORE_PORT` | 4004 | HTTP port |
| `KNOWLEDGE_STORE_CHROMA_PERSIST_DIR` | ./data/chromadb | Storage path |
| `KNOWLEDGE_STORE_CHROMA_COLLECTION_NAME` | knowledge_patterns | Collection name |
| `KNOWLEDGE_STORE_LOG_LEVEL` | INFO | Log level |

### Systemd Service
```
~/.config/systemd/user/knowledge-store.service
```

---

## Key Decisions

### Port 4004
- Canonical port in ecosystem (session:4002, bridge:4003, store:4004)
- Killed legacy uckn-knowledge to free port

### Python 3.12.*
- ChromaDB/onnxruntime don't have wheels for Python 3.14
- Pinned in `[tool.pixi.dependencies]`

### HTTP Transport Direct Dispatch
- MCP Server.call_tool() decorator has incompatible signature for HTTP
- HTTP handler calls `_discover_tools()`, `_get_tool_spec()`, `_execute_tool()` directly

---

## Integration Points

### knowledge-bridge (upstream)
- Promotes entries to knowledge-store via `add_entry`
- Queries for deduplication via `find_similar`
- Currently using `MockUCKNClient` - needs real client implementation

### curator daemon (planned)
- Periodic obsolescence checks via `list_entries`
- Quality score updates via `update_entry`
- Deduplication via `find_similar`

---

## Known Issues / TODOs

1. **knowledge-bridge client**: Bridge still uses MockUCKNClient, needs real KnowledgeStoreClient
2. **Embedding model**: Using ChromaDB default (all-MiniLM-L6-v2), may want to configure
3. **Backup/restore**: No backup strategy for ChromaDB data yet
4. **Rate limiting**: No rate limiting on HTTP endpoints

---

## Changelog

| Date | Change |
|------|--------|
| 2026-01-05 | Initial scaffolding, systemd service, port 4004 |
