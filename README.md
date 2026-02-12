# knowledge-store

ChromaDB-based MCP server providing semantic search over development patterns.

## Overview

Part of the session-intelligence ecosystem:

```
session-intelligence:4002 → knowledge-bridge:4003 → knowledge-store:4005
```

## Features

- **Lean MCP pattern**: 3 meta-tools (discover_tools, get_tool_spec, execute_tool)
- **8 tools**: add_entry, get_entry, update_entry, delete_entry, search, find_similar, list_entries, get_stats
- **ChromaDB**: Persistent vector storage with cosine similarity
- **HTTP transport**: Port 4004

## Quick Start

```bash
# Install dependencies
pixi install

# Run server
pixi run serve

# Run tests
pixi run test
```

## Endpoints

- `POST /mcp` - MCP JSON-RPC
- `GET /health` - Health check
- `GET /stats` - Collection statistics

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `KNOWLEDGE_STORE_HOST` | 127.0.0.1 | Bind address |
| `KNOWLEDGE_STORE_PORT` | 4004 | HTTP port |
| `KNOWLEDGE_STORE_CHROMA_PERSIST_DIR` | ./data/chromadb | ChromaDB storage |
| `KNOWLEDGE_STORE_LOG_LEVEL` | INFO | Log level |

## License

MIT
