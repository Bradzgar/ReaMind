from reamind.providers.base import ToolSpec


def test_list_mcp_servers_spec():
    spec = ToolSpec(
        name="list_mcp_servers",
        description="List all connected MCP servers and their tool counts",
        parameters={"type": "object", "properties": {}, "required": []},
        executor="local",
        destructive=False,
        return_confirmation=False,
    )
    assert spec.name == "list_mcp_servers"
    assert spec.executor == "local"
    assert spec.destructive is False


def test_connect_mcp_server_spec():
    spec = ToolSpec(
        name="connect_mcp_server",
        description="Connect to an MCP server and register its tools. For stdio servers provide command and args; for SSE servers provide url.",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name for this MCP server (used as tool prefix)"},
                "transport": {"type": "string", "description": "stdio or sse"},
                "command": {"type": "string", "description": "Executable (stdio transport)"},
                "args": {"type": "array", "items": {"type": "string"}, "description": "Arguments (stdio transport)"},
                "env": {"type": "object", "description": "Environment variables (stdio transport)"},
                "url": {"type": "string", "description": "SSE endpoint URL (sse transport)"},
            },
            "required": ["name", "transport"],
        },
        executor="local",
        destructive=False,
        return_confirmation=False,
    )
    assert spec.name == "connect_mcp_server"
    assert spec.executor == "local"
    assert spec.destructive is False


def test_disconnect_mcp_server_spec():
    spec = ToolSpec(
        name="disconnect_mcp_server",
        description="Disconnect from an MCP server and unregister its tools. Requires confirmation.",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Name of the MCP server to disconnect"},
                "confirm_ok": {"type": "boolean", "description": "Set to true to confirm disconnection"},
            },
            "required": ["name", "confirm_ok"],
        },
        executor="local",
        destructive=True,
        return_confirmation=True,
    )
    assert spec.name == "disconnect_mcp_server"
    assert spec.executor == "local"
    assert spec.destructive is True
    assert spec.return_confirmation is True
