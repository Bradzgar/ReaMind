from __future__ import annotations

from .mcp.protocol import next_id, parse_response, send_notification, send_request
from .mcp.stdio import StdioTransport
from .mcp.sse import SSETransport
from .providers.base import ToolCall, ToolSpec


class MCPClient:
    def __init__(self, name: str, transport) -> None:
        self.name = name
        self._transport = transport
        self.tools: list[ToolSpec] = []

    def connect(self) -> bool:
        self._transport.start()
        req_id = next_id()
        self._transport.send(send_request(req_id, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "reamind", "version": "1.0.0"},
        }))
        resp = parse_response(self._transport.recv())
        if "error" in str(resp):
            raise RuntimeError(f"initialize failed: {resp}")
        self._transport.send(send_notification("notifications/initialized"))
        return True

    def disconnect(self) -> None:
        self._transport.stop()

    def list_tools(self) -> list[ToolSpec]:
        req_id = next_id()
        self._transport.send(send_request(req_id, "tools/list"))
        resp = parse_response(self._transport.recv())
        raw_tools = resp.get("result", {}).get("tools", [])
        self.tools = []
        for tool in raw_tools:
            is_destructive = bool(tool.get("annotations", {}).get("destructiveHint", False))
            self.tools.append(ToolSpec(
                name=f"{self.name}__{tool['name']}",
                description=f"[MCP: {self.name}] {tool.get('description', '')}",
                parameters=tool.get("inputSchema", {"type": "object", "properties": {}}),
                executor="mcp",
                destructive=is_destructive,
                return_confirmation=is_destructive,
            ))
        return self.tools

    def call_tool(self, name: str, args: dict) -> dict:
        prefix = self.name + "__"
        if not name.startswith(prefix):
            return {"ok": False, "error": f"namespace mismatch for '{name}'"}
        stripped = name[len(prefix):]
        req_id = next_id()
        self._transport.send(send_request(req_id, "tools/call", {
            "name": stripped,
            "arguments": args,
        }))
        try:
            resp = parse_response(self._transport.recv())
        except Exception as e:
            return {"ok": False, "error": str(e)}
        result = resp.get("result", {})
        return {"ok": True, "result": result}

    def connected(self) -> bool:
        return self._transport.alive()


class MCPHost:
    def __init__(self) -> None:
        self._clients: dict[str, MCPClient] = {}

    def add_server(self, name: str, config: dict) -> MCPClient:
        transport_type = config.get("transport", "stdio")
        if transport_type == "sse":
            transport = SSETransport(config["url"])
        else:
            transport = StdioTransport(
                config["command"],
                config.get("args", []),
                config.get("env"),
            )
        client = MCPClient(name, transport)
        client.connect()
        self._clients[name] = client
        return client

    def remove_server(self, name: str) -> None:
        client = self._clients.pop(name, None)
        if client is not None:
            client.disconnect()

    def get_all_tools(self) -> list[ToolSpec]:
        all_tools: list[ToolSpec] = []
        for client in self._clients.values():
            all_tools.extend(client.list_tools())
        return all_tools

    def execute(self, call: ToolCall) -> dict:
        for client in self._clients.values():
            prefix = client.name + "__"
            if call.name.startswith(prefix):
                return client.call_tool(call.name, call.arguments)
        return {"ok": False, "error": f"unknown MCP tool: {call.name}"}

    def list_servers(self) -> list[dict]:
        return [
            {
                "name": c.name,
                "connected": c.connected(),
                "tool_count": len(c.tools),
            }
            for c in self._clients.values()
        ]
