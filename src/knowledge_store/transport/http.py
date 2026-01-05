"""HTTP transport for knowledge-store MCP server.

Provides HTTP endpoints for MCP protocol and convenience REST endpoints.
"""

import json
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

# Global server instance
_server: KnowledgeStoreServer | None = None


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
            # List the 3 meta-tools
            tools = await server.server.list_tools()
            result = {"tools": [t.model_dump() for t in tools]}

        elif method == "tools/call":
            tool_name = params.get("name", "")
            arguments = params.get("arguments", {})
            contents = await server.server.call_tool(tool_name, arguments)
            result = {"content": [c.model_dump() for c in contents]}

        elif method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "knowledge-store",
                    "version": "0.1.0",
                },
            }

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
            {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}},
            status_code=400,
        )
    except Exception as e:
        logger.error("mcp_error", error=str(e))
        return JSONResponse(
            {"jsonrpc": "2.0", "id": None, "error": {"code": -32603, "message": str(e)}},
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
