"""Tests for MCP server and HTTP transport."""

import pytest
from starlette.testclient import TestClient

from knowledge_store.server import KnowledgeStoreServer
from knowledge_store.transport.http import create_app


@pytest.fixture
def server(knowledge_store) -> KnowledgeStoreServer:
    """Create a server with test store."""
    server = KnowledgeStoreServer.__new__(KnowledgeStoreServer)
    server.store = knowledge_store
    return server


@pytest.fixture
def http_client(knowledge_store, monkeypatch) -> TestClient:
    """Create a test client for HTTP endpoints."""
    # Patch the global server to use our test store
    from knowledge_store.transport import http

    test_server = KnowledgeStoreServer.__new__(KnowledgeStoreServer)
    test_server.store = knowledge_store
    monkeypatch.setattr(http, "_server", test_server)

    app = create_app()
    return TestClient(app)


class TestDiscoverTools:
    """Tests for discover_tools meta-tool."""

    def test_discover_all_tools(self, server: KnowledgeStoreServer) -> None:
        """Test discovering all tools."""
        result = server._discover_tools("")

        assert "tools" in result
        assert result["total_count"] == 8  # All 8 tools
        assert "categories" in result
        assert set(result["categories"]) == {"crud", "search", "analytics"}

    def test_discover_with_pattern(self, server: KnowledgeStoreServer) -> None:
        """Test discovering tools with pattern filter."""
        result = server._discover_tools("entry")

        assert result["total_count"] < 8
        # Pattern matches in either name or description
        assert all(
            "entry" in t["name"].lower() or "entry" in t["description"].lower()
            for t in result["tools"]
        )


class TestGetToolSpec:
    """Tests for get_tool_spec meta-tool."""

    def test_get_valid_tool_spec(self, server: KnowledgeStoreServer) -> None:
        """Test getting spec for valid tool."""
        result = server._get_tool_spec("add_entry")

        assert result["name"] == "add_entry"
        assert "description" in result
        assert "parameters" in result
        assert "examples" in result

    def test_get_invalid_tool_spec(self, server: KnowledgeStoreServer) -> None:
        """Test getting spec for invalid tool."""
        result = server._get_tool_spec("nonexistent_tool")

        assert "error" in result


class TestExecuteTool:
    """Tests for execute_tool meta-tool."""

    @pytest.mark.asyncio
    async def test_execute_add_entry(self, server: KnowledgeStoreServer) -> None:
        """Test executing add_entry tool."""
        result = await server._execute_tool(
            "add_entry",
            {
                "problem_pattern": "Test problem",
                "solution": "Test solution",
            },
        )

        assert result["success"] is True
        assert "entry_id" in result

    @pytest.mark.asyncio
    async def test_execute_get_stats(self, server: KnowledgeStoreServer) -> None:
        """Test executing get_stats tool."""
        result = await server._execute_tool("get_stats", {})

        assert "total_entries" in result
        assert "entries_by_status" in result

    @pytest.mark.asyncio
    async def test_execute_invalid_tool(self, server: KnowledgeStoreServer) -> None:
        """Test executing invalid tool."""
        result = await server._execute_tool("nonexistent_tool", {})

        assert "error" in result


class TestHTTPTransport:
    """Tests for HTTP transport endpoints."""

    def test_health_endpoint(self, http_client: TestClient) -> None:
        """Test health check endpoint."""
        response = http_client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "entry_count" in data

    def test_stats_endpoint(self, http_client: TestClient) -> None:
        """Test stats endpoint."""
        response = http_client.get("/stats")

        assert response.status_code == 200
        data = response.json()
        assert "total_entries" in data

    def test_mcp_initialize(self, http_client: TestClient) -> None:
        """Test MCP initialize request."""
        response = http_client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {},
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["result"]["serverInfo"]["name"] == "knowledge-store"

    def test_mcp_tools_list(self, http_client: TestClient) -> None:
        """Test MCP tools/list request."""
        response = http_client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/list",
                "params": {},
            },
        )

        assert response.status_code == 200
        data = response.json()
        tools = data["result"]["tools"]
        assert len(tools) == 3  # The 3 meta-tools
        tool_names = {t["name"] for t in tools}
        assert tool_names == {"discover_tools", "get_tool_spec", "execute_tool"}

    def test_mcp_tools_call(self, http_client: TestClient) -> None:
        """Test MCP tools/call request."""
        response = http_client.post(
            "/mcp",
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "tools/call",
                "params": {
                    "name": "discover_tools",
                    "arguments": {"pattern": ""},
                },
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert "content" in data["result"]
