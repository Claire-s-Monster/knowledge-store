"""MCP Server implementation with lean 3-tool pattern.

Provides discover_tools, get_tool_spec, and execute_tool for knowledge store operations.
"""

from typing import Any

import structlog
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from .models import ToolSpec, ToolSummary
from .store import KnowledgeStore

logger = structlog.get_logger(__name__)

# Tool definitions
TOOLS: dict[str, dict[str, Any]] = {
    "add_entry": {
        "category": "crud",
        "description": "Add a new knowledge entry to the store",
        "parameters": {
            "type": "object",
            "properties": {
                "problem_pattern": {"type": "string", "description": "What problem this solves"},
                "solution": {"type": "string", "description": "The solution/pattern"},
                "code_example": {"type": "string", "description": "Optional code snippet"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Classification tags"},
                "pattern_type": {
                    "type": "string",
                    "enum": ["bugfix", "best_practice", "optimization", "setup", "architecture"],
                    "default": "bugfix",
                },
                "source_session": {"type": "string", "description": "Source session ID"},
                "source_type": {"type": "string", "enum": ["session", "direct", "seeded"], "default": "session"},
            },
            "required": ["problem_pattern", "solution"],
        },
        "examples": [
            {
                "problem_pattern": "pytest fixtures not found in conftest.py",
                "solution": "Ensure conftest.py is in the test root directory",
                "tags": ["pytest", "fixtures"],
                "pattern_type": "bugfix",
            }
        ],
    },
    "get_entry": {
        "category": "crud",
        "description": "Retrieve a knowledge entry by ID",
        "parameters": {
            "type": "object",
            "properties": {
                "entry_id": {"type": "string", "description": "Entry UUID"},
            },
            "required": ["entry_id"],
        },
        "examples": [{"entry_id": "550e8400-e29b-41d4-a716-446655440000"}],
    },
    "update_entry": {
        "category": "crud",
        "description": "Update an existing entry (partial update)",
        "parameters": {
            "type": "object",
            "properties": {
                "entry_id": {"type": "string", "description": "Entry UUID"},
                "updates": {
                    "type": "object",
                    "description": "Fields to update (quality_score, status, tags, etc.)",
                },
            },
            "required": ["entry_id", "updates"],
        },
        "examples": [
            {
                "entry_id": "550e8400-e29b-41d4-a716-446655440000",
                "updates": {"quality_score": 0.9, "status": "canonical"},
            }
        ],
    },
    "delete_entry": {
        "category": "crud",
        "description": "Delete an entry by ID (prefer archiving via update_entry)",
        "parameters": {
            "type": "object",
            "properties": {
                "entry_id": {"type": "string", "description": "Entry UUID"},
            },
            "required": ["entry_id"],
        },
        "examples": [{"entry_id": "550e8400-e29b-41d4-a716-446655440000"}],
    },
    "search": {
        "category": "search",
        "description": "Semantic search for knowledge entries",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query text"},
                "limit": {"type": "integer", "default": 10, "description": "Max results"},
                "filters": {
                    "type": "object",
                    "description": "Metadata filters (status, tags, quality_score, etc.)",
                },
            },
            "required": ["query"],
        },
        "examples": [
            {"query": "pytest async fixture", "limit": 5, "filters": {"status": "active"}}
        ],
    },
    "find_similar": {
        "category": "search",
        "description": "Find entries similar to a given entry (for deduplication)",
        "parameters": {
            "type": "object",
            "properties": {
                "entry_id": {"type": "string", "description": "Entry UUID to find similar entries for"},
                "threshold": {"type": "number", "default": 0.85, "description": "Minimum similarity score"},
                "limit": {"type": "integer", "default": 10, "description": "Max results"},
            },
            "required": ["entry_id"],
        },
        "examples": [
            {"entry_id": "550e8400-e29b-41d4-a716-446655440000", "threshold": 0.9}
        ],
    },
    "list_entries": {
        "category": "search",
        "description": "List entries with optional filtering and pagination",
        "parameters": {
            "type": "object",
            "properties": {
                "filters": {"type": "object", "description": "Metadata filters"},
                "limit": {"type": "integer", "default": 100, "description": "Max results"},
                "offset": {"type": "integer", "default": 0, "description": "Pagination offset"},
            },
        },
        "examples": [{"filters": {"status": "canonical"}, "limit": 50}],
    },
    "get_stats": {
        "category": "analytics",
        "description": "Get collection statistics",
        "parameters": {"type": "object", "properties": {}},
        "examples": [{}],
    },
}


class KnowledgeStoreServer:
    """MCP server for knowledge store with lean 3-tool pattern."""

    def __init__(self) -> None:
        """Initialize the server."""
        self.store = KnowledgeStore()
        self.server = Server("knowledge-store")
        self._register_handlers()

    def _register_handlers(self) -> None:
        """Register MCP handlers."""

        @self.server.list_tools()
        async def list_tools() -> list[Tool]:
            """List the 3 meta-tools."""
            return [
                Tool(
                    name="discover_tools",
                    description="Get available tools with minimal context consumption",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "pattern": {
                                "type": "string",
                                "default": "",
                                "description": "Filter by name pattern (substring match)",
                            }
                        },
                    },
                ),
                Tool(
                    name="get_tool_spec",
                    description="Get full specification for specific tool including schema and examples",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "tool_name": {"type": "string", "description": "Name of tool to get specification for"}
                        },
                        "required": ["tool_name"],
                    },
                ),
                Tool(
                    name="execute_tool",
                    description="Execute tool with parameters using dynamic dispatch",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "tool_name": {"type": "string", "description": "Name of tool to execute"},
                            "parameters": {"type": "object", "description": "Tool parameters"},
                        },
                        "required": ["tool_name", "parameters"],
                    },
                ),
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: dict) -> list[TextContent]:
            """Handle tool calls."""
            try:
                if name == "discover_tools":
                    result = self._discover_tools(arguments.get("pattern", ""))
                elif name == "get_tool_spec":
                    result = self._get_tool_spec(arguments["tool_name"])
                elif name == "execute_tool":
                    result = await self._execute_tool(
                        arguments["tool_name"],
                        arguments.get("parameters", {}),
                    )
                else:
                    result = {"error": f"Unknown tool: {name}"}

                return [TextContent(type="text", text=str(result))]

            except Exception as e:
                logger.error("tool_call_failed", tool=name, error=str(e))
                return [TextContent(type="text", text=f"Error: {e}")]

    def _discover_tools(self, pattern: str = "") -> dict[str, Any]:
        """Get available tools with minimal context."""
        tools = []
        for name, spec in TOOLS.items():
            if pattern.lower() in name.lower() or pattern.lower() in spec["description"].lower():
                tools.append(
                    ToolSummary(
                        name=name,
                        description=spec["description"],
                        category=spec["category"],
                    ).model_dump()
                )

        return {
            "tools": tools,
            "total_count": len(tools),
            "categories": list({t["category"] for t in tools}),
        }

    def _get_tool_spec(self, tool_name: str) -> dict[str, Any]:
        """Get full specification for a tool."""
        if tool_name not in TOOLS:
            return {"error": f"Unknown tool: {tool_name}"}

        spec = TOOLS[tool_name]
        return ToolSpec(
            name=tool_name,
            description=spec["description"],
            category=spec["category"],
            parameters=spec["parameters"],
            examples=spec.get("examples", []),
        ).model_dump()

    async def _execute_tool(self, tool_name: str, parameters: dict) -> dict[str, Any]:
        """Execute a tool with parameters."""
        if tool_name not in TOOLS:
            return {"error": f"Unknown tool: {tool_name}"}

        logger.info("executing_tool", tool=tool_name, params=list(parameters.keys()))

        try:
            if tool_name == "add_entry":
                result = self.store.add_entry(**parameters)
                return result.model_dump()

            elif tool_name == "get_entry":
                entry = self.store.get_entry(parameters["entry_id"])
                return {"entry": entry.model_dump() if entry else None}

            elif tool_name == "update_entry":
                result = self.store.update_entry(
                    parameters["entry_id"],
                    parameters["updates"],
                )
                return result.model_dump()

            elif tool_name == "delete_entry":
                success = self.store.delete_entry(parameters["entry_id"])
                return {"success": success}

            elif tool_name == "search":
                results = self.store.search(
                    query=parameters["query"],
                    limit=parameters.get("limit", 10),
                    filters=parameters.get("filters"),
                )
                return {
                    "results": [r.model_dump() for r in results],
                    "count": len(results),
                }

            elif tool_name == "find_similar":
                results = self.store.find_similar(
                    entry_id=parameters["entry_id"],
                    threshold=parameters.get("threshold", 0.85),
                    limit=parameters.get("limit", 10),
                )
                return {
                    "results": [r.model_dump() for r in results],
                    "count": len(results),
                }

            elif tool_name == "list_entries":
                entries = self.store.list_entries(
                    filters=parameters.get("filters"),
                    limit=parameters.get("limit", 100),
                    offset=parameters.get("offset", 0),
                )
                return {
                    "entries": [e.model_dump() for e in entries],
                    "count": len(entries),
                }

            elif tool_name == "get_stats":
                stats = self.store.get_stats()
                return stats.model_dump()

            else:
                return {"error": f"Tool not implemented: {tool_name}"}

        except Exception as e:
            logger.error("tool_execution_failed", tool=tool_name, error=str(e))
            return {"error": str(e)}

    async def run_stdio(self) -> None:
        """Run the server with stdio transport."""
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                self.server.create_initialization_options(),
            )
