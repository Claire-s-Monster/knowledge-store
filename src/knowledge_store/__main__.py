"""Entry point for knowledge-store MCP server.

Supports both stdio and HTTP transport modes.
"""

import argparse
import asyncio
import sys

import structlog

from .config import settings
from .server import KnowledgeStoreServer
from .transport.http import run_http_server


def configure_logging() -> None:
    """Configure structured logging."""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.dev.ConsoleRenderer()
            if sys.stderr.isatty()
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Knowledge Store MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="http",
        help="Transport mode (default: http)",
    )
    parser.add_argument(
        "--host",
        default=None,
        help=f"HTTP host (default: {settings.host})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help=f"HTTP port (default: {settings.port})",
    )
    parser.add_argument(
        "--repository",
        default=None,
        help="Repository path (for compatibility with other MCP servers)",
    )

    args = parser.parse_args()

    # Override settings from CLI args
    if args.host:
        settings.host = args.host
    if args.port:
        settings.port = args.port

    configure_logging()
    logger = structlog.get_logger(__name__)

    if args.transport == "stdio":
        logger.info("starting_stdio_server")
        server = KnowledgeStoreServer()
        asyncio.run(server.run_stdio())
    else:
        logger.info("starting_http_server", host=settings.host, port=settings.port)
        run_http_server()


if __name__ == "__main__":
    main()
