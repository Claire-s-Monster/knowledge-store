"""HTTP transport for knowledge-store MCP server.

Provides HTTP endpoints for MCP protocol and convenience REST endpoints.
"""

import dataclasses
import json
import uuid
from datetime import datetime
from typing import Any

import structlog
import uvicorn
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from ..config import settings
from ..server import KnowledgeStoreServer

logger = structlog.get_logger(__name__)

# MCP Protocol version
MCP_PROTOCOL_VERSION = "2024-11-05"

# Simple in-memory MCP session storage
_mcp_sessions: dict[str, dict[str, Any]] = {}

# Global server instance
_server: KnowledgeStoreServer | None = None


class DatetimeJSONEncoder(json.JSONEncoder):
    """JSON encoder that handles datetime and dataclass objects."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, datetime):
            return obj.isoformat()
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            return dataclasses.asdict(obj)
        if hasattr(obj, "model_dump"):  # Pydantic v2
            return obj.model_dump()
        if hasattr(obj, "dict"):  # Pydantic v1
            return obj.dict()
        return super().default(obj)


def get_server() -> KnowledgeStoreServer:
    """Get or create the server instance."""
    global _server
    if _server is None:
        _server = KnowledgeStoreServer()
    return _server


async def handle_mcp(request: Request) -> Response:
    """Handle MCP JSON-RPC requests."""
    try:
        body = await request.json()
        logger.debug("mcp_request", method=body.get("method"))

        server = get_server()

        # Handle JSON-RPC request
        method = body.get("method", "")
        params = body.get("params", {})
        request_id = body.get("id")

        result: dict[str, Any] = {}

        if method == "tools/list":
            # Return the 3 meta-tools with LLM-friendly descriptions
            from mcp.types import Tool

            tools = [
                Tool(
                    name="discover_tools",
                    description=(
                        "Discover knowledge store tools for storing and retrieving learned patterns. "
                        "USE WHEN: starting knowledge store work, finding available operations, "
                        "exploring CRUD/search/analytics capabilities. "
                        "[STEP 1 of 3] Call this first to see available tools."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "pattern": {
                                "type": "string",
                                "default": "",
                                "description": "Filter pattern",
                            }
                        },
                    },
                ),
                Tool(
                    name="get_tool_spec",
                    description=(
                        "Get full specification for a knowledge store tool including schema and examples. "
                        "USE WHEN: need parameter details for add_entry, search, find_similar, etc. "
                        "[STEP 2 of 3] Call after discover_tools to get schema before execute_tool."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {"tool_name": {"type": "string"}},
                        "required": ["tool_name"],
                    },
                ),
                Tool(
                    name="execute_tool",
                    description=(
                        "Execute knowledge store operations: add/search/update entries, find duplicates, get stats. "
                        "USE WHEN: storing learned patterns, searching knowledge base, deduplication checks. "
                        "[STEP 3 of 3] Call after get_tool_spec with proper parameters."
                    ),
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "tool_name": {"type": "string"},
                            "parameters": {"type": "object"},
                        },
                        "required": ["tool_name", "parameters"],
                    },
                ),
            ]
            result = {"tools": [t.model_dump() for t in tools]}

        elif method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            # Call our handler methods directly
            if tool_name == "discover_tools":
                tool_result = server._discover_tools(arguments.get("pattern", ""))
            elif tool_name == "get_tool_spec":
                tool_result = server._get_tool_spec(arguments.get("tool_name", ""))
            elif tool_name == "execute_tool":
                tool_result = await server._execute_tool(
                    arguments.get("tool_name", ""),
                    arguments.get("parameters", {}),
                )
            else:
                tool_result = {"error": f"Unknown tool: {tool_name}"}
            result = {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(tool_result, cls=DatetimeJSONEncoder),
                    }
                ]
            }

        elif method == "initialize":
            new_session_id = str(uuid.uuid4())
            _mcp_sessions[new_session_id] = {"created": True}
            response = JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": MCP_PROTOCOL_VERSION,
                        "capabilities": {"tools": {"listChanged": True}},
                        "serverInfo": {
                            "name": "knowledge-store",
                            "version": "0.1.0",
                        },
                    },
                }
            )
            response.headers["MCP-Session-Id"] = new_session_id
            response.headers["MCP-Protocol-Version"] = MCP_PROTOCOL_VERSION
            return response

        elif method == "notifications/initialized":
            result = {}

        elif method in ("resources/list", "resources/templates/list"):
            result = {"resources": []}

        elif method == "prompts/list":
            result = {"prompts": []}

        else:
            return JSONResponse(
                {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": f"Method not found: {method}"},
                },
                status_code=400,
            )

        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result,
            }
        )

    except json.JSONDecodeError:
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error"},
            },
            status_code=400,
        )
    except Exception as e:
        logger.error("mcp_error", error=str(e))
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": str(e)},
            },
            status_code=500,
        )


async def handle_health(request: Request) -> JSONResponse:
    """Health check endpoint."""
    server = get_server()
    stats = server.store.get_stats()

    return JSONResponse(
        {
            "status": "healthy",
            "chromadb": "connected",
            "collection": settings.chroma_collection_name,
            "entry_count": stats.total_entries,
            "version": "0.1.0",
        }
    )


async def handle_stats(request: Request) -> JSONResponse:
    """Statistics endpoint."""
    server = get_server()
    stats = server.store.get_stats()
    return JSONResponse(stats.model_dump())


def create_app() -> Starlette:
    """Create the Starlette application."""
    routes = [
        Route("/mcp", handle_mcp, methods=["POST"]),
        Route("/health", handle_health, methods=["GET"]),
        Route("/stats", handle_stats, methods=["GET"]),
    ]

    app = Starlette(routes=routes)

    @app.on_event("startup")
    async def startup() -> None:
        logger.info(
            "server_starting",
            host=settings.host,
            port=settings.port,
        )
        # Initialize server on startup
        get_server()

    @app.on_event("shutdown")
    async def shutdown() -> None:
        logger.info("server_stopping")

    return app


def run_http_server() -> None:
    """Run the HTTP server."""
    app = create_app()
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )
