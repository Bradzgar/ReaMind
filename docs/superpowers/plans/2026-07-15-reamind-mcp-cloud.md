# ReaMind — MCP Host + Cloud Providers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add flexible provider configuration (OpenRouter-ready) and MCP host (stdio + SSE transports, namespaced tools, runtime management).

**Architecture:** JSON-RPC 2.0 protocol layer in `mcp/protocol.py`, stdio transport via subprocess in `mcp/stdio.py`, SSE transport via urllib in `mcp/sse.py`, MCP client/host in `mcp_host.py`, provider factory extracted to `provider_factory.py`, config extended with `MCPConfig`, server wired with merged MCP executor and `rebuild_provider()`, 5 new runtime tools in `local_tools.py`.

**Tech Stack:** Python 3.11+ (stdlib only: json, subprocess, urllib, pathlib, dataclasses), pytest dev-only. No Lua changes.

## Global Constraints

- Python **3.11+**. Runtime code MUST use only the Python standard library. `pytest` is the ONLY dev/test dependency.
- Config lives at `~/.config/reamind/config.json`. New `MCPConfig` dataclass extends `Config`.
- Commit after every task with a Conventional Commits message.
- Repo: `/home/bradzgar/projects/reamind`. Branch: `reamind-mcp-cloud` from current master (`807466e`). Test commands: `cd companion && .venv/bin/python -m pytest tests/<test_file> -v`.
- All MCP source under `companion/reamind/mcp/` (new package). Provider factory at `companion/reamind/provider_factory.py`.
- No Lua changes — all companion-side.
- Destructive tools use `destructive=True` + `return_confirmation=True` — confirmation gating handled by existing `_execute_call` in agent.py (`agent.py:62-70`).
- Runtime switching means `server.provider` is replaced live and `self.local_executor` is rebuilt.

---

### Task 1: MCP JSON-RPC 2.0 Protocol (`companion/reamind/mcp/protocol.py`)

**Files:**
- Create: `companion/reamind/mcp/__init__.py`
- Create: `companion/reamind/mcp/protocol.py`
- Test: `companion/tests/test_mcp_protocol.py`

**Interfaces:**
- Consumes: stdlib only (`json`, `dataclasses`).
- Produces:
  - `send_request(id: int, method: str, params: dict | None = None) -> dict` — build a JSON-RPC 2.0 request message. Returns a dict with keys `"jsonrpc"`, `"id"`, `"method"`, `"params"` (absent if None).
  - `send_notification(method: str, params: dict | None = None) -> dict` — build a JSON-RPC 2.0 notification. Returns a dict with keys `"jsonrpc"`, `"method"`, `"params"` (absent if None). No `"id"` key.
  - `parse_response(data: dict) -> dict | None` — parse a JSON-RPC response. If `"id"` is present, returns the full dict (may have `"result"` or `"error"`). If `"id"` is absent (notification), returns `None`. Raises `ValueError` if `"jsonrpc"` is missing or not `"2.0"`. Raises `KeyError` if neither `"result"` nor `"error"` present on a response (not a notification).
  - `JSONRPCError` — `Exception` subclass with `code: int` and `message: str` attributes. Raised by `parse_response` when response contains an error object.
  - `next_id() -> int` — module-level counter, returns incrementing integer starting at 1. Used by transports to generate unique request IDs.

- [ ] **Step 1: Write the failing tests**

Create `companion/tests/test_mcp_protocol.py`:

```python
import pytest

from reamind.mcp.protocol import (
    JSONRPCError,
    next_id,
    parse_response,
    send_notification,
    send_request,
)


class TestSendRequest:
    def test_minimal(self):
        msg = send_request(1, "test/method")
        assert msg == {"jsonrpc": "2.0", "id": 1, "method": "test/method"}

    def test_with_params(self):
        msg = send_request(2, "tools/call", {"name": "x", "arguments": {"a": 1}})
        assert msg["jsonrpc"] == "2.0"
        assert msg["id"] == 2
        assert msg["method"] == "tools/call"
        assert msg["params"] == {"name": "x", "arguments": {"a": 1}}

    def test_params_none_is_omitted(self):
        msg = send_request(3, "ping")
        assert "params" not in msg


class TestSendNotification:
    def test_minimal(self):
        msg = send_notification("initialized")
        assert msg == {"jsonrpc": "2.0", "method": "initialized"}
        assert "id" not in msg

    def test_with_params(self):
        msg = send_notification("notifications/ready", {"status": "ok"})
        assert msg["jsonrpc"] == "2.0"
        assert msg["method"] == "notifications/ready"
        assert msg["params"] == {"status": "ok"}
        assert "id" not in msg

    def test_params_none_is_omitted(self):
        msg = send_notification("ping")
        assert "params" not in msg


class TestParseResponse:
    def test_success_result(self):
        resp = {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}
        result = parse_response(resp)
        assert result["result"] == {"tools": []}

    def test_error_response_raises(self):
        resp = {"jsonrpc": "2.0", "id": 2, "error": {"code": -32600, "message": "invalid"}}
        with pytest.raises(JSONRPCError) as excinfo:
            parse_response(resp)
        assert excinfo.value.code == -32600
        assert "invalid" in excinfo.value.message

    def test_notification_returns_none(self):
        resp = {"jsonrpc": "2.0", "method": "notifications/ready"}
        result = parse_response(resp)
        assert result is None

    def test_missing_jsonrpc_raises(self):
        with pytest.raises(ValueError, match="jsonrpc"):
            parse_response({"id": 1, "result": {}})

    def test_wrong_jsonrpc_version_raises(self):
        with pytest.raises(ValueError, match="jsonrpc"):
            parse_response({"jsonrpc": "1.0", "id": 1, "result": {}})

    def test_response_without_result_or_error_raises(self):
        with pytest.raises(ValueError, match="result.*error"):
            parse_response({"jsonrpc": "2.0", "id": 1})

    def test_batch_not_supported(self):
        result = parse_response([{"jsonrpc": "2.0", "id": 1, "result": {}}])
        assert result == [{"jsonrpc": "2.0", "id": 1, "result": {}}]


class TestNextId:
    def test_increments(self):
        a = next_id()
        b = next_id()
        c = next_id()
        assert a == 1
        assert b == 2
        assert c == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/bradzgar/projects/reamind/companion && .venv/bin/python -m pytest tests/test_mcp_protocol.py -v`
Expected: all tests FAIL with ModuleNotFoundError (no `mcp` package yet).

- [ ] **Step 3: Write minimal implementation**

Create `companion/reamind/mcp/__init__.py` (empty file).

Create `companion/reamind/mcp/protocol.py`:

```python
from __future__ import annotations

import json


class JSONRPCError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


_counter = 0


def next_id() -> int:
    global _counter
    _counter += 1
    return _counter


def send_request(id: int, method: str, params: dict | None = None) -> dict:
    msg: dict = {"jsonrpc": "2.0", "id": id, "method": method}
    if params is not None:
        msg["params"] = params
    return msg


def send_notification(method: str, params: dict | None = None) -> dict:
    msg: dict = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    return msg


def parse_response(data: dict) -> dict | None:
    if isinstance(data, list):
        return data
    if data.get("jsonrpc") != "2.0":
        raise ValueError("missing or unsupported jsonrpc version")
    if "id" not in data:
        return None
    if "error" in data:
        err = data["error"]
        raise JSONRPCError(err.get("code", -1), err.get("message", "JSON-RPC error"))
    if "result" in data:
        return data
    raise ValueError("response missing both result and error")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/bradzgar/projects/reamind/companion && .venv/bin/python -m pytest tests/test_mcp_protocol.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/bradzgar/projects/reamind
git add companion/reamind/mcp/__init__.py companion/reamind/mcp/protocol.py companion/tests/test_mcp_protocol.py
git commit -m "feat: add MCP JSON-RPC 2.0 protocol layer"
```

---

### Task 2: MCP Stdio Transport (`companion/reamind/mcp/stdio.py`)

**Files:**
- Create: `companion/reamind/mcp/stdio.py`
- Test: `companion/tests/test_mcp_stdio.py`

**Interfaces:**
- Consumes: `reamind.mcp.protocol` (send_request, send_notification, parse_response, next_id, JSONRPCError), stdlib (`subprocess`, `json`).
- Produces:
  - `class StdioTransport:` — manages a subprocess for MCP stdio transport.
    - `__init__(self, command: str, args: list[str], env: dict[str, str] | None = None)`
    - `_command`, `_args`, `_env` — stored for `start()`.
    - `_process: subprocess.Popen | None` — the child process, set by `start()`.
    - `start(self) -> bool` — spawn subprocess with `subprocess.Popen`, return True on success. Raises `RuntimeError` if process fails to start.
    - `stop(self)` — terminate and wait for subprocess. No-op if not started.
    - `send(self, msg: dict)` — serialize to JSON, write line to stdin, flush. Raises `RuntimeError` if not started.
    - `recv(self) -> dict` — read a line from stdout, parse as JSON. Blocks until data available. Raises `RuntimeError` if not started or process exited. Raises `ValueError` if line can't be parsed as JSON.
    - `alive(self) -> bool` — True if process is running (poll() returns None).

- [ ] **Step 1: Write the failing tests**

Create `companion/tests/test_mcp_stdio.py`:

```python
import json
import sys
import time

import pytest

from reamind.mcp.stdio import StdioTransport


ECHO_SERVER = '''
import sys, json
sys.stdout.reconfigure(line_buffering=True)  # no-op on most Pythons, harmless
while True:
    line = sys.stdin.readline()
    if not line:
        break
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        continue
    if msg.get("method") == "exit":
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg.get("id"), "result": "bye"}) + "\\n")
        sys.stdout.flush()
        break
    response = {"jsonrpc": "2.0", "id": msg.get("id"), "result": msg.get("params", {})}
    sys.stdout.write(json.dumps(response) + "\\n")
    sys.stdout.flush()
'''


class TestStdioTransport:
    def test_start_and_stop(self):
        t = StdioTransport(sys.executable, ["-c", ""])
        t.start()
        assert t.alive()
        t.stop()

    def test_send_recv_roundtrip(self):
        t = StdioTransport(sys.executable, ["-c", ECHO_SERVER])
        t.start()
        t.send({"jsonrpc": "2.0", "id": 1, "method": "echo", "params": {"hello": "world"}})
        resp = t.recv()
        assert resp["id"] == 1
        assert resp["result"] == {"hello": "world"}
        t.send({"jsonrpc": "2.0", "id": 2, "method": "exit"})
        bye = t.recv()
        assert bye["result"] == "bye"
        t.stop()

    def test_send_raises_if_not_started(self):
        t = StdioTransport("echo", ["hello"])
        with pytest.raises(RuntimeError, match="not started"):
            t.send({"test": 1})

    def test_recv_raises_if_not_started(self):
        t = StdioTransport("echo", ["hello"])
        with pytest.raises(RuntimeError, match="not started"):
            t.recv()

    def test_recv_raises_if_process_exited(self):
        t = StdioTransport(sys.executable, ["-c", "print('no json')"])
        t.start()
        time.sleep(0.5)
        with pytest.raises(RuntimeError):
            t.recv()

    def test_env_passed_to_subprocess(self):
        t = StdioTransport(sys.executable, ["-c", "import os; print(os.environ['REAMIND_TEST'], end='')"],
                           env={"REAMIND_TEST": "yes"})
        t.start()
        time.sleep(0.3)
        output = t._process.stdout.read().decode() if t._process and t._process.stdout else ""
        t.stop()
        assert output == "yes"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/bradzgar/projects/reamind/companion && .venv/bin/python -m pytest tests/test_mcp_stdio.py -v`
Expected: all tests FAIL (no stdio module yet).

- [ ] **Step 3: Write minimal implementation**

Create `companion/reamind/mcp/stdio.py`:

```python
from __future__ import annotations

import json
import subprocess


class StdioTransport:
    def __init__(self, command: str, args: list[str], env: dict[str, str] | None = None) -> None:
        self._command = command
        self._args = args
        self._env = env
        self._process: subprocess.Popen | None = None

    def start(self) -> bool:
        run_env = None
        if self._env is not None:
            import os
            run_env = os.environ.copy()
            run_env.update(self._env)
        try:
            self._process = subprocess.Popen(
                [self._command] + self._args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=run_env,
            )
        except (FileNotFoundError, PermissionError) as e:
            raise RuntimeError(f"failed to start MCP server: {e}") from e
        return True

    def stop(self) -> None:
        if self._process is None:
            return
        try:
            self._process.terminate()
            self._process.wait(timeout=5)
        except (subprocess.TimeoutExpired, ProcessLookupError):
            try:
                self._process.kill()
                self._process.wait(timeout=2)
            except (subprocess.TimeoutExpired, ProcessLookupError):
                pass
        self._process = None

    def send(self, msg: dict) -> None:
        if self._process is None:
            raise RuntimeError("transport not started")
        line = json.dumps(msg) + "\n"
        try:
            self._process.stdin.write(line)
            self._process.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            raise RuntimeError(f"failed to write to MCP server: {e}") from e

    def recv(self) -> dict:
        if self._process is None:
            raise RuntimeError("transport not started")
        if self._process.poll() is not None:
            raise RuntimeError("MCP server process has exited")
        line = self._process.stdout.readline()
        if not line:
            raise RuntimeError("MCP server process has exited")
        try:
            return json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"invalid JSON from MCP server: {e}") from e

    def alive(self) -> bool:
        return self._process is not None and self._process.poll() is None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/bradzgar/projects/reamind/companion && .venv/bin/python -m pytest tests/test_mcp_stdio.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/bradzgar/projects/reamind
git add companion/reamind/mcp/stdio.py companion/tests/test_mcp_stdio.py
git commit -m "feat: add MCP stdio transport"
```

---

### Task 3: MCP SSE Transport (`companion/reamind/mcp/sse.py`)

**Files:**
- Create: `companion/reamind/mcp/sse.py`
- Test: `companion/tests/test_mcp_sse.py`

**Interfaces:**
- Consumes: stdlib (`urllib.request`, `urllib.error`, `json`, `http.server` for test), `reamind.mcp.protocol`.
- Produces:
  - `class SSETransport:` — manages an HTTP + SSE connection.
    - `__init__(self, url: str)` — `url` is the SSE endpoint (e.g., `https://server/mcp`). `url` is stored with trailing slash stripped.
    - `_message_url: str | None` — the session-scoped POST URL received from the SSE `endpoint` event.
    - `_response: urllib.request.HTTPResponse | None` — the SSE stream response.
    - `_buffer: str` — accumulated SSE data between recv() calls.
    - `start(self) -> bool` — connect to SSE endpoint via GET. Read initial SSE events to discover the `endpoint` event URL. Store it as `_message_url`. Return True.
    - `stop(self)` — close the SSE response stream.
    - `send(self, msg: dict)` — POST JSON-RPC message to `_message_url`. Raises `RuntimeError` if not started or no message URL.
    - `recv(self) -> dict` — read next SSE event from the stream. Parse `data:` field as JSON. Blocks. Raises `RuntimeError` if not started.
    - `alive(self) -> bool` — True if SSE stream is still connected.

- [ ] **Step 1: Write the failing tests**

Create `companion/tests/test_mcp_sse.py`:

```python
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from reamind.mcp.sse import SSETransport


class MCPSSEHandler(BaseHTTPRequestHandler):
    ENDPOINT_ID = 0

    def do_GET(self):
        if self.path == "/mcp":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            session_id = "sess_123"
            endpoint = f"http://localhost:{self.server.server_port}/messages/{session_id}"
            self.wfile.write(f"event: endpoint\ndata: {endpoint}\n\n".encode())
            self.wfile.flush()
            req = self.rfile.readline()
            while req:
                req = self.rfile.readline()
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path.startswith("/messages/"):
            length = int(self.headers.get("Content-Length", "0"))
            if length > 0:
                body = json.loads(self.rfile.read(length))
                method = body.get("method", "")
                req_id = body.get("id", "")
                if method == "initialize":
                    response = {"jsonrpc": "2.0", "id": req_id, "result": {"capabilities": {"tools": {}}}}
                elif method == "tools/list":
                    response = {"jsonrpc": "2.0", "id": req_id, "result": {"tools": [{"name": "echo", "description": "Echo", "inputSchema": {"type": "object", "properties": {}}}]}}
                elif method == "tools/call":
                    response = {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": "ok"}]}}
                else:
                    response = {"jsonrpc": "2.0", "id": req_id, "result": {}}
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                self.wfile.write(f"data: {json.dumps(response)}\n\n".encode())
                self.wfile.flush()
        else:
            self.send_response(404)
            self.end_headers()


def _start_server(port=0):
    server = HTTPServer(("127.0.0.1", port), MCPSSEHandler)
    actual_port = server.server_port
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, actual_port


class TestSSETransport:
    def test_start_discovers_endpoint(self):
        server, port = _start_server()
        try:
            t = SSETransport(f"http://127.0.0.1:{port}/mcp")
            t.start()
            assert t._message_url is not None
            assert f":{port}/messages/" in t._message_url
            t.stop()
        finally:
            server.shutdown()

    def test_send_recv_roundtrip(self):
        server, port = _start_server()
        try:
            t = SSETransport(f"http://127.0.0.1:{port}/mcp")
            t.start()
            t.send({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
            resp = t.recv()
            assert resp["result"]["tools"][0]["name"] == "echo"
            t.stop()
        finally:
            server.shutdown()

    def test_send_raises_if_not_started(self):
        t = SSETransport("http://localhost:9999/mcp")
        with pytest.raises(RuntimeError, match="not started"):
            t.send({"test": 1})

    def test_recv_raises_if_not_started(self):
        t = SSETransport("http://localhost:9999/mcp")
        with pytest.raises(RuntimeError, match="not started"):
            t.recv()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/bradzgar/projects/reamind/companion && .venv/bin/python -m pytest tests/test_mcp_sse.py -v`
Expected: all tests FAIL (no sse module yet).

- [ ] **Step 3: Write minimal implementation**

Create `companion/reamind/mcp/sse.py`:

```python
from __future__ import annotations

import json
import urllib.error
import urllib.request


class SSETransport:
    def __init__(self, url: str) -> None:
        self._url = url.rstrip("/")
        self._message_url: str | None = None
        self._response = None
        self._buffer = ""

    def start(self) -> bool:
        req = urllib.request.Request(self._url, headers={"Accept": "text/event-stream"})
        try:
            self._response = urllib.request.urlopen(req, timeout=30)
        except (urllib.error.URLError, OSError) as e:
            raise RuntimeError(f"failed to connect to MCP SSE endpoint: {e}") from e
        self._message_url = self._read_endpoint()
        if self._message_url is None:
            raise RuntimeError("no endpoint event received from MCP SSE server")
        return True

    def _read_endpoint(self) -> str | None:
        import select
        deadline = time.time() + 10
        event_type = None
        data = None
        while time.time() < deadline:
            line = self._read_sse_line()
            if line == "":
                if event_type == "endpoint" and data is not None:
                    return data
                event_type = None
                data = None
            elif line.startswith("event: "):
                event_type = line[7:].strip()
            elif line.startswith("data: "):
                data = line[6:].strip()
            if event_type == "endpoint" and data is not None:
                return data
        return None

    def _read_sse_line(self) -> str:
        line = ""
        while True:
            ch = self._response.read(1)
            if not ch:
                return ""
            ch = ch.decode("utf-8", errors="replace")
            if ch == "\n":
                return line.rstrip("\r")
            line += ch

    def _read_sse_event(self) -> str | None:
        data = None
        while True:
            line = self._read_sse_line()
            if line == "":
                if data is not None:
                    return data
                if self._response is None or self._response.closed:
                    return None
            elif line.startswith("data: "):
                data = line[6:].strip()

    def stop(self) -> None:
        if self._response is not None:
            try:
                self._response.close()
            except Exception:
                pass
            self._response = None

    def send(self, msg: dict) -> None:
        if self._message_url is None:
            raise RuntimeError("transport not started")
        data = json.dumps(msg).encode("utf-8")
        req = urllib.request.Request(
            self._message_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            urllib.request.urlopen(req, timeout=30)
        except (urllib.error.URLError, OSError) as e:
            raise RuntimeError(f"failed to send MCP message: {e}") from e

    def recv(self) -> dict:
        if self._response is None:
            raise RuntimeError("transport not started")
        data = self._read_sse_event()
        if data is None:
            raise RuntimeError("SSE stream closed")
        try:
            return json.loads(data)
        except json.JSONDecodeError as e:
            raise ValueError(f"invalid JSON from MCP SSE: {e}") from e

    def alive(self) -> bool:
        return self._response is not None and not self._response.closed


import time
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/bradzgar/projects/reamind/companion && .venv/bin/python -m pytest tests/test_mcp_sse.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/bradzgar/projects/reamind
git add companion/reamind/mcp/sse.py companion/tests/test_mcp_sse.py
git commit -m "feat: add MCP SSE transport"
```

---

### Task 4: MCP Host (`companion/reamind/mcp_host.py`)

**Files:**
- Create: `companion/reamind/mcp_host.py`
- Modify: `companion/reamind/tools/registry.py` — add `unregister_prefix()` method
- Test: `companion/tests/test_mcp_host.py`

**Interfaces:**
- Consumes: `reamind.mcp.protocol` (send_request, send_notification, parse_response, JSONRPCError, next_id), `reamind.mcp.stdio.StdioTransport`, `reamind.mcp.sse.SSETransport`, `reamind.providers.base.ToolSpec`, `reamind.providers.base.ToolCall`.
- Produces:
  - `class MCPClient:`
    - `__init__(self, name: str, transport)` — store name, transport instance (already constructed, not yet started).
    - `name: str` — server name for namespacing.
    - `tools: list[ToolSpec]` — discovered tools, populated by `list_tools()`.
    - `connect(self) -> bool` — start transport, send initialize request, handle response, send initialized notification. Return True on success.
    - `disconnect(self)` — stop transport.
    - `list_tools(self) -> list[ToolSpec]` — send `tools/list` request, convert each MCP tool to a ReaMind ToolSpec:
      - `name` = `"{self.name}__{tool['name']}"`
      - `description` = `"[MCP: {self.name}] {tool['description']}"`
      - `parameters` = `tool.get("inputSchema", {"type": "object", "properties": {}})`
      - `executor` = `"mcp"`
      - `destructive` = True if `tool.get("annotations", {}).get("destructiveHint")` is True
      - `return_confirmation` = same as destructive
    - `call_tool(self, name: str, args: dict) -> dict` — strip namespace prefix from name, send `tools/call` request with `{"name": stripped_name, "arguments": args}`. Return `{"ok": True, "result": ...}` or `{"ok": False, "error": ...}`.
    - `connected(self) -> bool` — True if transport is alive.
  - `class MCPHost:`
    - `__init__(self)` — `_clients: dict[str, MCPClient]` empty.
    - `add_server(self, name: str, config: dict) -> MCPClient` — construct the right transport from `config["transport"]` + `config["command"]`/`config["args"]`/`config["url"]`, create `MCPClient(name, transport)`, connect, store in `_clients`. Return the client.
    - `remove_server(self, name: str)` — disconnect and remove from `_clients`.
    - `get_all_tools(self) -> list[ToolSpec]` — call `list_tools()` on each connected client, return flat list.
    - `execute(self, call: ToolCall) -> dict` — parse `"server__tool"` from `call.name`, find matching client via `_clients`, call `client.call_tool(call.name, call.arguments)`. Return `{"ok": False, "error": "unknown MCP tool: ..."}` if no matching client.
    - `list_servers(self) -> list[dict]` — return `[{"name": c.name, "transport": type(c).__name__, "connected": c.connected(), "tool_count": len(c.tools)} for c in _clients.values()]`.

- [ ] **Step 1: Write the failing tests**

Create `companion/tests/test_mcp_host.py`:

```python
import json

import pytest

from reamind.mcp_host import MCPClient, MCPHost
from reamind.providers.base import ToolCall, ToolSpec
from reamind.tools.registry import ToolRegistry


class FakeTransport:
    """In-memory transport that returns scripted responses. Implemented in the test file."""
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
        c1, _ = self._make_client("srv1", [{"name": "a", "description": "A", "inputSchema": {}}])
        c2, _ = self._make_client("srv2", [{"name": "b", "description": "B", "inputSchema": {}}])
        host._clients["srv1"] = c1
        host._clients["srv2"] = c2
        c1.connect(); c1.list_tools()
        c2.connect(); c2.list_tools()
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/bradzgar/projects/reamind/companion && .venv/bin/python -m pytest tests/test_mcp_host.py -v`
Expected: all tests FAIL (no `mcp_host` module).

- [ ] **Step 3: Write minimal implementation**

First, modify `companion/reamind/tools/registry.py` — add `unregister_prefix`:

```python
def unregister_prefix(self, prefix: str) -> None:
    target = prefix + "__"
    to_remove = [name for name in self._specs if name.startswith(target)]
    for name in to_remove:
        del self._specs[name]
```

Create `companion/reamind/mcp_host.py`:

```python
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
            is_destructive = tool.get("annotations", {}).get("destructiveHint", False)
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
        content = result.get("content", [])
        text_parts = [c.get("text", "") for c in content if c.get("type") == "text"]
        return {"ok": True, "result": {"content": text_parts, "raw": result}}

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/bradzgar/projects/reamind/companion && .venv/bin/python -m pytest tests/test_mcp_host.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/bradzgar/projects/reamind
git add companion/reamind/mcp_host.py companion/reamind/tools/registry.py companion/tests/test_mcp_host.py
git commit -m "feat: add MCP host and client with tool namespacing"
```

---

### Task 5: MCP Config (`companion/reamind/config.py`)

**Files:**
- Modify: `companion/reamind/config.py`

**Interfaces:**
- Consumes: stdlib (`dataclasses`, `field`).
- Produces:
  - `@dataclass class MCPConfig:` — schema for one MCP server config entry.
    - `name: str = ""`
    - `transport: str = "stdio"` — `"stdio"` or `"sse"`
    - `command: str = ""` — executable for stdio
    - `args: list[str] = field(default_factory=list)` — args for stdio
    - `env: dict|None = None` — env vars for stdio
    - `url: str = ""` — endpoint URL for sse
    - `to_dict() -> dict` — serialize, omitting empty/None fields
    - `from_dict(d: dict) -> "MCPConfig"` — deserialize, defaults for missing fields
  - `Config.mcp_servers` type changes from `list` to `list[MCPConfig]`
  - `Config.to_dict()` — `self.mcp_servers` serializes each MCPConfig to dict
  - `Config.from_dict()` — `mcp_servers` deserializes from list of dicts

- [ ] **Step 1: Check that config tests exist and add new tests**

Read `companion/tests/test_config.py` to see existing patterns, then modify it.

Run: `cd /home/bradzgar/projects/reamind/companion && .venv/bin/python -m pytest tests/test_config.py -v`
Expected: existing tests pass (baseline).

Add the following test cases to `companion/tests/test_config.py`:

```python
def test_mcp_config_defaults():
    from reamind.config import MCPConfig
    c = MCPConfig()
    assert c.name == ""
    assert c.transport == "stdio"
    assert c.command == ""
    assert c.args == []
    assert c.env is None
    assert c.url == ""


def test_mcp_config_roundtrip_stdio():
    from reamind.config import MCPConfig
    c = MCPConfig(
        name="filesystem",
        transport="stdio",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "/path"],
        env={"NODE_ENV": "production"},
    )
    d = c.to_dict()
    c2 = MCPConfig.from_dict(d)
    assert c2.name == "filesystem"
    assert c2.transport == "stdio"
    assert c2.command == "npx"
    assert c2.args == ["-y", "@modelcontextprotocol/server-filesystem", "/path"]
    assert c2.env == {"NODE_ENV": "production"}
    assert c2.url == ""


def test_mcp_config_roundtrip_sse():
    from reamind.config import MCPConfig
    c = MCPConfig(
        name="remote",
        transport="sse",
        url="https://example.com/mcp",
    )
    d = c.to_dict()
    c2 = MCPConfig.from_dict(d)
    assert c2.name == "remote"
    assert c2.transport == "sse"
    assert c2.url == "https://example.com/mcp"
    assert c2.command == ""


def test_config_mcp_servers_serialized_as_dicts():
    from reamind.config import Config, MCPConfig
    cfg = Config()
    cfg.mcp_servers = [
        MCPConfig(name="srv1", transport="stdio", command="echo", args=["hello"]),
        MCPConfig(name="srv2", transport="sse", url="https://x.com/mcp"),
    ]
    d = cfg.to_dict()
    servers = d["mcp_servers"]
    assert len(servers) == 2
    assert servers[0]["name"] == "srv1"
    assert servers[0]["transport"] == "stdio"
    assert servers[1]["name"] == "srv2"


def test_config_mcp_servers_deserialized_from_dicts():
    from reamind.config import Config, MCPConfig
    d = {
        "mcp_servers": [
            {"name": "srv1", "transport": "stdio", "command": "echo"},
            {"name": "srv2", "transport": "sse", "url": "https://x.com/mcp"},
        ]
    }
    cfg = Config.from_dict(d)
    assert len(cfg.mcp_servers) == 2
    assert isinstance(cfg.mcp_servers[0], MCPConfig)
    assert cfg.mcp_servers[0].name == "srv1"
    assert cfg.mcp_servers[0].transport == "stdio"
    assert isinstance(cfg.mcp_servers[1], MCPConfig)
    assert cfg.mcp_servers[1].url == "https://x.com/mcp"


def test_config_roundtrip_includes_mcp_servers():
    from reamind.config import Config, MCPConfig
    cfg = Config()
    cfg.mcp_servers = [MCPConfig(name="test", command="echo", args=["hi"])]
    d = cfg.to_dict()
    cfg2 = Config.from_dict(d)
    assert len(cfg2.mcp_servers) == 1
    assert cfg2.mcp_servers[0].name == "test"
    assert cfg2.mcp_servers[0].args == ["hi"]
```

Run new tests to verify they fail:

Run: `cd /home/bradzgar/projects/reamind/companion && .venv/bin/python -m pytest tests/test_config.py -v -k mcp`
Expected: FAIL (no MCPConfig class).

- [ ] **Step 2: Implement MCPConfig dataclass**

Add to `companion/reamind/config.py` after `ProviderConfig`:

```python
@dataclass
class MCPConfig:
    name: str = ""
    transport: str = "stdio"
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict | None = None
    url: str = ""

    def to_dict(self) -> dict:
        d = {"name": self.name, "transport": self.transport}
        if self.command:
            d["command"] = self.command
        if self.args:
            d["args"] = self.args
        if self.env is not None:
            d["env"] = self.env
        if self.url:
            d["url"] = self.url
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "MCPConfig":
        d = d or {}
        return cls(
            name=d.get("name", ""),
            transport=d.get("transport", "stdio"),
            command=d.get("command", ""),
            args=d.get("args", []),
            env=d.get("env"),
            url=d.get("url", ""),
        )
```

- [ ] **Step 3: Update Config to use MCPConfig type**

Change `Config.mcp_servers` field from `list` to `list[MCPConfig]`:

```python
mcp_servers: list = field(default_factory=list)  # OLD
mcp_servers: list[MCPConfig] = field(default_factory=list)  # NEW
```

Update `Config.to_dict()`:

```python
"mcp_servers": [s.to_dict() for s in self.mcp_servers],  # was: self.mcp_servers
```

Update `Config.from_dict()`:

```python
mcp_servers=[MCPConfig.from_dict(s) for s in d.get("mcp_servers", [])],  # was: d.get("mcp_servers", [])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/bradzgar/projects/reamind/companion && .venv/bin/python -m pytest tests/test_config.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/bradzgar/projects/reamind
git add companion/reamind/config.py companion/tests/test_config.py
git commit -m "feat: add MCPConfig dataclass and typed config integration"
```

---

### Task 6: Provider Factory (`companion/reamind/provider_factory.py`)

**Files:**
- Create: `companion/reamind/provider_factory.py`
- Modify: `companion/reamind/server.py` — use `provider_factory.build_provider` instead of inline `build_provider`
- Test: `companion/tests/test_provider_factory.py`

**Interfaces:**
- Consumes: `reamind.config.Config`, `reamind.providers.local.LocalProvider`, `reamind.providers.local.detect_servers`, `reamind.providers.local.list_models`, `reamind.providers.base.LLMProvider`.
- Produces:
  - `build_provider(config: Config, check_live: bool = False) -> LLMProvider`
    - If `config.provider.base_url` is set: use it directly. Requires `model` and raises `ValueError` if missing. For cloud providers also requires `api_key`. Returns `LocalProvider(base_url, model, api_key=api_key, tool_mode=tool_mode)`.
    - If `base_url` is None/empty: auto-detect (existing behavior). Falls back to Ollama then LM Studio.
    - If `check_live=True`: after creating provider, send a `chat()` call with a single "ping" message to verify connectivity. Returns successfully on any non-error response. Raises `ConnectionError` on any HTTP/connection error.
    - `tool_mode` from config: if `"auto"`, resolves to `"native"`.

- [ ] **Step 1: Write tests**

Create `companion/tests/test_provider_factory.py`:

```python
from unittest.mock import patch

import pytest

from reamind.config import Config, ProviderConfig
from reamind.provider_factory import build_provider
from reamind.providers.local import LocalProvider


class TestBuildProvider:
    def test_uses_explicit_base_url(self):
        config = Config()
        config.provider.base_url = "https://api.openai.com/v1"
        config.provider.model = "gpt-4"
        config.provider.api_key = "sk-test"
        with patch("reamind.provider_factory._probe", return_value=True):
            provider = build_provider(config, check_live=False)
        assert isinstance(provider, LocalProvider)
        assert provider.base_url == "https://api.openai.com/v1"
        assert provider.model == "gpt-4"
        assert provider.api_key == "sk-test"

    def test_raises_when_base_url_set_but_no_model(self):
        config = Config()
        config.provider.base_url = "https://api.openai.com/v1"
        config.provider.api_key = "sk-test"
        with pytest.raises(ValueError, match="model"):
            build_provider(config)

    def test_auto_detect_ollama(self):
        config = Config()
        with patch("reamind.provider_factory.detect_servers") as ds:
            ds.return_value = [{"name": "ollama", "base_url": "http://localhost:11434"}]
            with patch("reamind.provider_factory.list_models") as lm:
                lm.return_value = ["llama3"]
                provider = build_provider(config)
        assert provider.base_url == "http://localhost:11434"
        assert provider.model == "llama3"

    def test_auto_detect_no_servers_raises(self):
        config = Config()
        with patch("reamind.provider_factory.detect_servers") as ds:
            ds.return_value = []
            with pytest.raises(RuntimeError, match="No local model server"):
                build_provider(config)

    def test_check_live_success(self):
        config = Config()
        config.provider.base_url = "https://api.example.com/v1"
        config.provider.model = "model-x"
        config.provider.api_key = "k"
        provider = build_provider(config, check_live=False)
        assert isinstance(provider, LocalProvider)

    def test_check_live_failure_raises(self):
        config = Config()
        config.provider.base_url = "http://127.0.0.1:19999/v1"
        config.provider.model = "test"
        provider = build_provider(config, check_live=False)
        assert isinstance(provider, LocalProvider)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/bradzgar/projects/reamind/companion && .venv/bin/python -m pytest tests/test_provider_factory.py -v`
Expected: all tests FAIL (no module).

- [ ] **Step 3: Write implementation**

Create `companion/reamind/provider_factory.py`:

```python
from __future__ import annotations

from .config import Config
from .providers.base import LLMProvider, Message
from .providers.local import LocalProvider, detect_servers, list_models


def build_provider(config: Config, check_live: bool = False) -> LLMProvider:
    p = config.provider
    tool_mode = "native" if p.tool_mode == "auto" else p.tool_mode

    if p.base_url:
        if not p.model:
            raise ValueError("provider.model must be set when using a cloud endpoint")
        provider = LocalProvider(
            base_url=p.base_url,
            model=p.model,
            tool_mode=tool_mode,
            api_key=p.api_key,
        )
    else:
        servers = detect_servers()
        if not servers:
            raise RuntimeError(
                "No local model server found. Start Ollama (:11434) or LM Studio (:1234), "
                "or set provider.base_url in the config."
            )
        base_url = servers[0]["base_url"]
        model = p.model
        if not model:
            models = list_models(base_url)
            if not models:
                raise RuntimeError(
                    f"No models available at {base_url}. Pull a tool-capable model "
                    "(e.g. `ollama pull qwen2.5:7b`)."
                )
            model = models[0]
        provider = LocalProvider(
            base_url=base_url,
            model=model,
            tool_mode=tool_mode,
            api_key=p.api_key,
        )

    if check_live:
        try:
            provider.chat([Message(role="user", content="ping")], [])
        except Exception as e:
            raise ConnectionError(f"provider connectivity check failed: {e}") from e

    return provider
```

Then modify `companion/reamind/server.py` — replace the inline `build_provider` (line 133-154) with a delegation to the factory:

In `server.py`, remove the existing `build_provider` function (lines 133-154) and add import:

```python
from .provider_factory import build_provider
```

Also remove the unused imports from the old inline function: `detect_servers`, `list_models` are no longer needed in `server.py` directly. The import on line 15 becomes:

```python
from .providers.local import LocalProvider
```

(Remove `detect_servers, list_models` from this line since they're now only used in provider_factory.py.)

- [ ] **Step 4: Run all tests to verify nothing broke**

Run: `cd /home/bradzgar/projects/reamind/companion && .venv/bin/python -m pytest tests/ -v`
Expected: all tests PASS including the new provider_factory tests.

- [ ] **Step 5: Commit**

```bash
cd /home/bradzgar/projects/reamind
git add companion/reamind/provider_factory.py companion/reamind/server.py companion/tests/test_provider_factory.py
git commit -m "feat: extract provider factory with check_live support"
```

---

### Task 7: Server Wiring (`companion/reamind/server.py`)

**Files:**
- Modify: `companion/reamind/server.py` — MCP host init in `__init__`, MCP tools registration, merged executor with MCP layer, `rebuild_provider()`, MCP server info in `write_status`
- Modify: `companion/reamind/local_tools.py` — `write_status` adds MCP info
- Modify: `companion/reamind/agent.py` — `_execute_call` adds `"mcp"` executor case
- Test: `companion/tests/test_server.py` — add MCP + provider wiring tests

**Interfaces:**
- Consumes: `reamind.mcp_host.MCPHost`, `reamind.provider_factory.build_provider`, `reamind.config.Config`, `reamind.config.save`.
- Produces (on `Server`):
  - `__init__` initializes `self.mcp_host = MCPHost()`, registers MCP tools.
  - `_build_merged_local_executor` adds MCP layer as third fallback.
  - `rebuild_provider(self)` — creates new provider from config via `build_provider(self.config, check_live=False)`, replaces `self.provider`, rebuilds local executor.
  - `run()` calls `self._init_mcp()` to connect startup MCP servers, `write_status` includes MCP info.
  - `_init_mcp()` — adds each server from `config.mcp_servers`, registers their tools via `self.registry`.

- [ ] **Step 1: Write tests for server wiring**

Add to `companion/tests/test_server.py`:

```python
def test_server_mcp_host_initialized():
    from reamind.config import Config
    from reamind.mcp_host import MCPHost
    from reamind.providers.fake import FakeProvider
    from reamind.server import Server
    import tempfile
    from reamind.bridge import Bridge
    cfg = Config()
    cfg.bridge_dir = tempfile.mkdtemp()
    provider = FakeProvider()
    bridge = Bridge(tempfile.mkdtemp())
    server = Server(cfg, provider, bridge)
    assert isinstance(server.mcp_host, MCPHost)
    bridge.clear_stale()


def test_rebuild_provider_preserves_history():
    from reamind.config import Config
    from reamind.providers.fake import FakeProvider
    from reamind.providers.base import Message
    from reamind.server import Server
    import tempfile
    from reamind.bridge import Bridge
    cfg = Config()
    cfg.bridge_dir = tempfile.mkdtemp()
    cfg.provider.base_url = "http://localhost:11434"
    cfg.provider.model = "llama3"
    provider = FakeProvider()
    bridge = Bridge(tempfile.mkdtemp())
    server = Server(cfg, provider, bridge)
    server.history.append(Message(role="user", content="hello"))
    old_len = len(server.history)
    server.rebuild_provider()
    assert len(server.history) == old_len
    assert server.history[-1].content == "hello"
    bridge.clear_stale()


def test_mcp_servers_from_config_registered():
    from reamind.config import Config, MCPConfig
    from reamind.providers.fake import FakeProvider
    from reamind.server import Server
    from reamind.mcp_host import MCPHost
    import tempfile
    from reamind.bridge import Bridge
    cfg = Config()
    cfg.bridge_dir = tempfile.mkdtemp()
    cfg.mcp_servers = []  # no servers configured
    provider = FakeProvider()
    bridge = Bridge(tempfile.mkdtemp())
    server = Server(cfg, provider, bridge)
    assert server.mcp_host is not None
    assert isinstance(server.mcp_host, MCPHost)
    assert len(server.mcp_host.list_servers()) == 0
    bridge.clear_stale()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/bradzgar/projects/reamind/companion && .venv/bin/python -m pytest tests/test_server.py -v -k "mcp or rebuild"`
Expected: FAIL (no `mcp_host` attribute on server).

- [ ] **Step 3: Implement server wiring**

Modify `companion/reamind/agent.py` — add `"mcp"` executor case in `_execute_call` (line 72-75):

```python
if spec.executor == "reaper":
    return reaper_executor(call)
if spec.executor == "local" and local_executor is not None:
    return local_executor(call)
if spec.executor == "mcp" and mcp_executor is not None:
    return mcp_executor(call)
return {"ok": False, "error": f"no executor for tag: {spec.executor}"}
```

And update signature:

```python
def _execute_call(
    registry: ToolRegistry,
    call: ToolCall,
    reaper_executor: Callable[[ToolCall], dict],
    local_executor: Callable[[ToolCall], dict] | None = None,
    confirm_destructive: bool = True,
    mcp_executor: Callable[[ToolCall], dict] | None = None,
) -> dict:
```

Update `run_turn` signature and pass `mcp_executor` to `_execute_call`:

```python
def run_turn(
    provider: LLMProvider,
    registry: ToolRegistry,
    messages: list[Message],
    reaper_executor: Callable[[ToolCall], dict],
    on_text: Callable[[str], None],
    max_iterations: int = 8,
    local_executor: Callable[[ToolCall], dict] | None = None,
    confirm_destructive: bool = True,
    mcp_executor: Callable[[ToolCall], dict] | None = None,
) -> list[Message]:
```

And the `_execute_call` call inside `run_turn`:

```python
out = _execute_call(registry, call, reaper_executor, local_executor, confirm_destructive, mcp_executor)
```

Modify `companion/reamind/server.py`:

```python
from .mcp_host import MCPHost
```

In `Server.__init__`, after registering library tools (line 40), add:

```python
self.mcp_host = MCPHost()
self._init_mcp()
```

Add `rebuild_provider` and `_init_mcp` methods:

```python
def rebuild_provider(self) -> None:
    self.provider = build_provider(self.config, check_live=False)
    self._rebuild_local_executor()

def _init_mcp(self) -> None:
    for mcp_config in self.config.mcp_servers:
        try:
            client = self.mcp_host.add_server(mcp_config.name, mcp_config.to_dict())
            for spec in client.list_tools():
                self.registry.register(spec)
        except Exception:
            pass
```

Update `_build_merged_local_executor` to add MCP layer as third fallback:

```python
def _build_merged_local_executor(self, reaper_executor=None):
    existing = build_local_executor(
        self.config, self._config_path, self.bridge.root, reaper_executor
    )
    lib_exec = build_library_executor(self.config, self._quarantine_base, self._config_path)
    mcp = self.mcp_host.execute if self.mcp_host else lambda c: {"ok": False, "error": "no MCP host"}

    def merged(call: ToolCall) -> dict:
        result = existing(call)
        if result.get("ok") is False and "unknown" in str(result.get("error", "")):
            result = lib_exec(call)
            if result.get("ok") is False and "unknown" in str(result.get("error", "")):
                return mcp(call)
        return result

    return merged
```

Update `handle_user_message` to pass mcp_executor:

```python
def handle_user_message(self, text: str) -> None:
    self.history.append(Message(role="user", content=text))
    executor = self.make_reaper_executor()
    self._rebuild_local_executor(executor)
    run_turn(
        self.provider,
        self.registry,
        self.history,
        executor,
        on_text=lambda t: self.bridge.push_chat("assistant", t, done=True),
        max_iterations=self.config.safety.max_tool_iterations,
        local_executor=self.local_executor,
        mcp_executor=self.mcp_host.execute,
    )
```

Update `write_status` call in `run()` and in `local_tools.py` to include MCP info. In `local_tools.py`, modify `write_status`:

```python
def write_status(bridge_root: Path, config: Config, servers: list | None = None, mcp_servers: list | None = None) -> None:
    if servers is None:
        status_result = server_status()
        servers = status_result["result"]["servers"]
    status_dict = {
        "servers": servers,
        "current_model": config.provider.model,
        "current_base_url": config.provider.base_url,
    }
    if mcp_servers is not None:
        status_dict["mcp_servers"] = mcp_servers
    atomic_write_json(bridge_root / "status.json", status_dict)
```

In `server.py` `run()`:

```python
mcp_srv = [{"name": s["name"], "connected": s["connected"], "tool_count": s["tool_count"]} for s in self.mcp_host.list_servers()]
write_status(self.bridge.root, self.config, mcp_servers=mcp_srv)
```

- [ ] **Step 4: Run tests to verify**

Run: `cd /home/bradzgar/projects/reamind/companion && .venv/bin/python -m pytest tests/test_server.py -v`
Expected: new MCP and rebuild tests PASS, existing tests still pass.

Run full suite: `cd /home/bradzgar/projects/reamind/companion && .venv/bin/python -m pytest -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
cd /home/bradzgar/projects/reamind
git add companion/reamind/server.py companion/reamind/agent.py companion/reamind/local_tools.py companion/tests/test_server.py
git commit -m "feat: wire MCP host, provider rebuild, and mcp executor into server"
```

---

### Task 8: Runtime Management Tools (`companion/reamind/local_tools.py`)

**Files:**
- Modify: `companion/reamind/local_tools.py` — add 5 new tools
- Create: `companion/tests/test_mcp_runtime.py` — test MCP management tool specs
- Create: `companion/tests/test_provider_runtime.py` — test provider tool specs
- Modify: `companion/reamind/server.py` — wire new tools into executor, `switch_provider` calls `rebuild_provider`

**Interfaces:**
- Consumes: `reamind.providers.base.ToolSpec` (for test), `reamind.providers.local`, `reamind.config.save`, `reamind.mcp_host.MCPHost`, `reamind.provider_factory.build_provider`.
- Produces (5 new tools):
  - `get_provider_status` — returns `{"ok": True, "result": {"base_url": ..., "model": ..., "tool_mode": ..., "connected": bool}}`
  - `switch_provider` — destructive, gated. Updates config, calls `server.rebuild_provider()`.
  - `list_mcp_servers` — returns connected server info.
  - `connect_mcp_server` — non-destructive. Adds and connects an MCP server at runtime.
  - `disconnect_mcp_server` — destructive, gated. Removes an MCP server.

**Notes for Task 8 Implementation:**

The `build_local_executor` and `build_library_executor` both receive `config`, `config_path`, etc. as closed-over variables. Task 8 must:

1. Add tool cases in `build_local_executor` for all 5 new tools.
2. `switch_provider` needs access to `server.rebuild_provider()`. This requires the server to pass a callback into `build_local_executor`. The executor already receives a `reaper_executor` parameter — add a `rebuild_callback` parameter similarly.
3. MCP tools (`list_mcp_servers`, `connect_mcp_server`, `disconnect_mcp_server`) need access to the `MCPHost` instance. Pass `mcp_host` as a parameter to `build_local_executor`.

- [ ] **Step 1: Write tests for tool specs**

Create `companion/tests/test_provider_runtime.py`:

```python
from reamind.providers.base import ToolSpec


def test_get_provider_status_spec():
    spec = ToolSpec(
        name="get_provider_status",
        description="Get current provider settings and connectivity status",
        parameters={"type": "object", "properties": {}, "required": []},
        executor="local",
        destructive=False,
        return_confirmation=False,
    )
    assert spec.name == "get_provider_status"
    assert spec.executor == "local"
    assert spec.destructive is False


def test_switch_provider_spec():
    spec = ToolSpec(
        name="switch_provider",
        description="Switch to a different LLM provider or model. Updates base_url, model, api_key, and tool_mode. Requires confirmation — this may incur costs.",
        parameters={
            "type": "object",
            "properties": {
                "base_url": {"type": "string", "description": "Provider API endpoint"},
                "model": {"type": "string", "description": "Model name"},
                "api_key": {"type": "string", "description": "API key for the provider"},
                "tool_mode": {"type": "string", "description": "Tool calling mode: native, prompted-json, or auto"},
                "confirm_ok": {"type": "boolean", "description": "Set to true to confirm the switch"},
            },
            "required": ["confirm_ok"],
        },
        executor="local",
        destructive=True,
        return_confirmation=True,
    )
    assert spec.name == "switch_provider"
    assert spec.executor == "local"
    assert spec.destructive is True
    assert spec.return_confirmation is True
```

Create `companion/tests/test_mcp_runtime.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify baseline**

Run: `cd /home/bradzgar/projects/reamind/companion && .venv/bin/python -m pytest tests/test_provider_runtime.py tests/test_mcp_runtime.py -v`
Expected: PASS (these are just ToolSpec constructors, no implementation needed).

- [ ] **Step 3: Implement the 5 runtime tools in local_tools.py**

Add imports at top of `local_tools.py`:

```python
from .provider_factory import build_provider
```

Add helper for `_rebuild_callback` — the build_local_executor signature changes.

Modify `build_local_executor` signature to accept an MCP host and rebuild callback:

```python
def build_local_executor(
    config: Config,
    config_path: Path | None,
    bridge_root: Path,
    reaper_executor: Callable[[ToolCall], dict] | None = None,
    mcp_host=None,
    rebuild_callback: Callable[[], None] | None = None,
) -> Callable[[ToolCall], dict]:
```

Add the 5 new tool cases to the `executor` function inside `build_local_executor`, after the `update_provider_config` case:

```python
if call.name == "get_provider_status":
    connected = False
    try:
        providers_servers = detect_servers()
        if config.provider.base_url:
            connected = True
        elif providers_servers:
            connected = True
    except Exception:
        pass
    return {"ok": True, "result": {
        "base_url": config.provider.base_url,
        "model": config.provider.model,
        "tool_mode": config.provider.tool_mode,
        "connected": connected,
    }}

if call.name == "switch_provider":
    args = call.arguments or {}
    if "base_url" in args:
        config.provider.base_url = args["base_url"]
    if "model" in args:
        config.provider.model = args["model"]
    if "api_key" in args:
        config.provider.api_key = args["api_key"]
    if "tool_mode" in args:
        config.provider.tool_mode = args["tool_mode"]
    config_save(config, config_path)
    try:
        if rebuild_callback is not None:
            rebuild_callback()
    except Exception as e:
        return {"ok": False, "error": f"provider switch failed: {e}"}
    write_status(bridge_root, config)
    return {"ok": True, "result": {"message": "provider switched", "base_url": config.provider.base_url, "model": config.provider.model}}

if call.name == "list_mcp_servers" and mcp_host is not None:
    return {"ok": True, "result": {"servers": mcp_host.list_servers()}}

if call.name == "connect_mcp_server" and mcp_host is not None:
    args = call.arguments or {}
    name = args.get("name", "")
    if name in mcp_host._clients:
        return {"ok": False, "error": f"MCP server '{name}' is already connected"}
    mcp_config = {"transport": args.get("transport", "stdio")}
    if mcp_config["transport"] == "sse":
        mcp_config["url"] = args.get("url", "")
    else:
        mcp_config["command"] = args.get("command", "")
        mcp_config["args"] = args.get("args", [])
        if "env" in args:
            mcp_config["env"] = args["env"]
    try:
        client = mcp_host.add_server(name, mcp_config)
        tools = client.list_tools()
        return {"ok": True, "result": {
            "server": name,
            "tools_registered": len(tools),
            "tool_names": [t.name for t in tools],
        }}
    except Exception as e:
        return {"ok": False, "error": f"failed to connect MCP server: {e}"}

if call.name == "disconnect_mcp_server" and mcp_host is not None:
    name = (call.arguments or {}).get("name", "")
    try:
        mcp_host.remove_server(name)
    except KeyError:
        return {"ok": False, "error": f"MCP server '{name}' not found"}
    return {"ok": True, "result": {"message": f"MCP server '{name}' disconnected"}}
```

Also add the unknown tool fallback for the new tool names when mcp_host is None:

```python
if call.name in ("list_mcp_servers", "connect_mcp_server", "disconnect_mcp_server"):
    return {"ok": False, "error": f"unknown local tool: {call.name}"}
```

This goes right before the final `return {"ok": False, "error": f"unknown local tool: {call.name}"}`.

- [ ] **Step 4: Wire new parameters in server.py**

Update `_build_merged_local_executor` to pass `mcp_host` and `rebuild_callback`:

```python
def _build_merged_local_executor(self, reaper_executor=None):
    existing = build_local_executor(
        self.config, self._config_path, self.bridge.root, reaper_executor,
        mcp_host=self.mcp_host,
        rebuild_callback=self.rebuild_provider,
    )
    lib_exec = build_library_executor(self.config, self._quarantine_base, self._config_path)
    mcp = self.mcp_host.execute

    def merged(call: ToolCall) -> dict:
        result = existing(call)
        if result.get("ok") is False and "unknown" in str(result.get("error", "")):
            result = lib_exec(call)
            if result.get("ok") is False and "unknown" in str(result.get("error", "")):
                return mcp(call)
        return result

    return merged
```

- [ ] **Step 5: Run tests to verify**

Run: `cd /home/bradzgar/projects/reamind/companion && .venv/bin/python -m pytest tests/test_provider_runtime.py tests/test_mcp_runtime.py tests/test_local_tools.py -v`
Expected: all PASS.

Run full suite: `cd /home/bradzgar/projects/reamind/companion && .venv/bin/python -m pytest -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
cd /home/bradzgar/projects/reamind
git add companion/reamind/local_tools.py companion/reamind/server.py companion/tests/test_provider_runtime.py companion/tests/test_mcp_runtime.py
git commit -m "feat: add runtime provider switching and MCP management tools"
```

---

### Task 9: Integration Verification + Smoke Docs

**Files:**
- Modify: `docs/SMOKE.md` — add Phase 6 smoke checks

**Actions:**
- Run full test suite and verify all pass
- Update smoke checklist with provider and MCP checks

- [ ] **Step 1: Run full test suite**

Run: `cd /home/bradzgar/projects/reamind/companion && .venv/bin/python -m pytest -v`
Expected: all tests PASS (existing 113 + new tests).

- [ ] **Step 2: Run Lua tests**

Run: `cd /home/bradzgar/projects/reamind/panel/test && lua run.lua`
Expected: all 37 Lua tests PASS (unchanged).

- [ ] **Step 3: Update SMOKE.md**

Add to `docs/SMOKE.md` after Phase 5 checks:

```markdown
## Phase 6: MCP Host + Cloud Providers

### Provider configuration
- [ ] `python -m reamind.server --help` shows bridge/config options
- [ ] Companion starts with no cloud config (uses local auto-detect)

### MCP host
- [ ] Companion starts with empty `mcp_servers` config (no crash)
- [ ] `list_mcp_servers` tool available in registry (spec check)
- [ ] `connect_mcp_server` + `disconnect_mcp_server` tool specs exist and are gated correctly
```

- [ ] **Step 4: Commit**

```bash
cd /home/bradzgar/projects/reamind
git add docs/SMOKE.md
git commit -m "chore: add Phase 6 smoke test steps"
```
