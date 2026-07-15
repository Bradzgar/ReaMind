import json

import pytest

from reamind.mcp_host import MCPClient, MCPHost
from reamind.providers.base import ToolCall, ToolSpec
from reamind.tools.registry import ToolRegistry


class FakeTransport:
    def __init__(self, responses=None):
        self.responses = responses or []
        self._sent = []
        self._started = False

    def start(self):
        self._started = True
        return True

    def stop(self):
        self._started = False

    def send(self, msg):
        self._sent.append(json.loads(json.dumps(msg)))

    def recv(self):
        return json.loads(json.dumps(self.responses.pop(0)))

    def alive(self):
        return self._started


def make_init_response(req_id):
    return {"jsonrpc": "2.0", "id": req_id, "result": {"capabilities": {"tools": {}}}}


def make_tools_list_response(req_id, tools=None):
    if tools is None:
        tools = [{"name": "echo", "description": "Echo", "inputSchema": {"type": "object", "properties": {}}}]
    return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools}}


def make_tools_call_response(req_id, result_text="ok"):
    return {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": result_text}]}}


class TestMCPClient:
    def test_connect_sends_initialize(self):
        t = FakeTransport([make_init_response(1)])
        client = MCPClient("test", t)
        client.connect()
        assert len(t._sent) == 2
        assert t._sent[0]["method"] == "initialize"
        assert t._sent[1]["method"] == "notifications/initialized"

    def test_list_tools_namespaces(self):
        t = FakeTransport([
            make_init_response(1),
            make_tools_list_response(2, [{"name": "read", "description": "Read files", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}}}]),
        ])
        client = MCPClient("filesystem", t)
        client.connect()
        tools = client.list_tools()
        assert len(tools) == 1
        spec = tools[0]
        assert spec.name == "filesystem__read"
        assert "[MCP: filesystem]" in spec.description
        assert spec.executor == "mcp"
        assert spec.parameters == {"type": "object", "properties": {"path": {"type": "string"}}}

    def test_list_tools_destructive_hint(self):
        t = FakeTransport([
            make_init_response(1),
            make_tools_list_response(2, [{"name": "delete", "description": "Delete", "inputSchema": {}, "annotations": {"destructiveHint": True}}]),
        ])
        client = MCPClient("fs", t)
        client.connect()
        tools = client.list_tools()
        assert tools[0].destructive is True
        assert tools[0].return_confirmation is True

    def test_call_tool_strips_namespace(self):
        t = FakeTransport([
            make_init_response(1),
            make_tools_call_response(3, "result text"),
        ])
        client = MCPClient("my", t)
        client.connect()
        result = client.call_tool("my__stuff", {"a": 1})
        assert result["ok"] is True
        assert result["result"] == {"content": [{"type": "text", "text": "result text"}]}
        assert t._sent[-1]["params"]["name"] == "stuff"

    def test_call_tool_namespace_mismatch(self):
        t = FakeTransport([make_init_response(1)])
        client = MCPClient("my", t)
        client.connect()
        result = client.call_tool("other__tool", {})
        assert result["ok"] is False
        assert "namespace" in result["error"].lower()


class TestMCPHost:
    def _make_client(self, name, tools=None):
        if tools is None:
            tools = [{"name": "echo", "description": "E", "inputSchema": {}}]
        t = FakeTransport([make_init_response(1), make_tools_list_response(2, tools)])
        return MCPClient(name, t), t

    def test_add_and_list_servers(self):
        host = MCPHost()
        client, transport = self._make_client("srv1")
        host._clients["srv1"] = client
        client.connect()
        client.list_tools()
        servers = host.list_servers()
        assert len(servers) == 1
        assert servers[0]["name"] == "srv1"
        assert servers[0]["tool_count"] == 1

    def test_get_all_tools(self):
        host = MCPHost()
        c1, t1 = self._make_client("srv1", [{"name": "a", "description": "A", "inputSchema": {}}])
        c2, t2 = self._make_client("srv2", [{"name": "b", "description": "B", "inputSchema": {}}])
        host._clients["srv1"] = c1
        host._clients["srv2"] = c2
        c1.connect()
        c2.connect()
        t1.responses.append(make_tools_list_response(3, [{"name": "a", "description": "A", "inputSchema": {}}]))
        t2.responses.append(make_tools_list_response(4, [{"name": "b", "description": "B", "inputSchema": {}}]))
        tools = host.get_all_tools()
        names = {t.name for t in tools}
        assert "srv1__a" in names
        assert "srv2__b" in names

    def test_execute_routes_to_correct_client(self):
        host = MCPHost()
        c1, t1 = self._make_client("srv1")
        c2, t2 = self._make_client("srv2", [{"name": "b", "description": "B", "inputSchema": {}}])
        host._clients["srv1"] = c1
        host._clients["srv2"] = c2
        c1.connect(); c1.list_tools()
        c2.connect(); c2.list_tools()
        t2.responses.append(make_tools_call_response(10, "from_srv2"))
        result = host.execute(ToolCall(id="c1", name="srv2__b", arguments={"x": 1}))
        assert result["ok"] is True

    def test_execute_unknown_tool(self):
        host = MCPHost()
        result = host.execute(ToolCall(id="c1", name="nonexistent__tool", arguments={}))
        assert result["ok"] is False
        assert "unknown" in result["error"].lower()

    def test_remove_server(self):
        host = MCPHost()
        c1, _ = self._make_client("srv1")
        host._clients["srv1"] = c1
        c1.connect()
        host.remove_server("srv1")
        assert "srv1" not in host._clients


class TestToolRegistryUnregisterPrefix:
    def test_unregister_prefix(self):
        reg = ToolRegistry()
        reg.register(ToolSpec("a__one", "", {}, "local"))
        reg.register(ToolSpec("a__two", "", {}, "local"))
        reg.register(ToolSpec("b__one", "", {}, "local"))
        assert len(reg.specs()) == 3
        reg.unregister_prefix("a")
        assert len(reg.specs()) == 1
        names = [s.name for s in reg.specs()]
        assert "b__one" in names
        assert "a__one" not in names

    def test_unregister_prefix_no_match(self):
        reg = ToolRegistry()
        reg.register(ToolSpec("a__one", "", {}, "local"))
        reg.unregister_prefix("b")
        assert len(reg.specs()) == 1
