# ReaMind — MCP Host + Cloud Providers Design Spec

**Date:** 2026-07-15
**Status:** Draft — pending review
**Phase:** 6 of 6 (per root spec §8)

## 1. Overview

Phase 6 adds two capabilities to the Python companion:

**A) Flexible provider configuration** — the existing `LocalProvider` already
speaks OpenAI-compatible (Ollama, LM Studio, OpenAI, OpenRouter). The gap is
that `build_provider()` hardcodes local auto-detection instead of using config.
This phase makes the provider fully config-driven with runtime switching.

**B) MCP host** — connect to external MCP servers over stdio (subprocess) or
HTTP/SSE, discover their tools, expose them namespaced in the ToolRegistry, and
route calls through a new `mcp` executor tag.

Both share the same config file and runtime lifecycle — the server wires them up
at startup and re-wires on runtime changes.

### Guiding principles
- **Stdlib-only**: no new dependencies. Subprocess, urllib, JSON-RPC — all stdlib.
- **Pluggable**: provider interface remains open for future Anthropic/etc.
- **Namespaced**: MCP tools use `server_name__tool_name` to avoid collisions.
- **Safety-first**: cloud switches and MCP disconnects use existing confirmation
  gating; MCP tools that declare themselves destructive inherit `return_confirmation`.

## 2. Architecture

```
companion/reamind/
  provider_factory.py     # build_provider() — factory from config
  mcp_host.py             # MCPHost — manages MCPClient instances, exposes tools
  mcp/
    __init__.py
    protocol.py           # JSON-RPC 2.0 (send/receive, request/response/notification)
    stdio.py              # StdioTransport — subprocess, line-delimited JSON-RPC
    sse.py                # SSETransport — HTTP POST + SSE stream
  local_tools.py          # (modified) — 5 new runtime tools
  server.py               # (modified) — factory, MCP init, merged executor, rebuild
  config.py               # (modified) — MCPConfig dataclass
  tools/
    registry.py           # (modified) — unregister_prefix()
```

**No Lua changes.** All work is companion-side.

### Data flow

```
Startup:
  config.json → provider_factory.build_provider() → LocalProvider
  config.json → mcp_host.add_server() × N → ToolSpecs registered

Chat:
  LLM → tool call → merged executor:
    1. standard local executor (config tools)
    2. library executor (Phase 5)
    3. mcp_host.execute()  ← NEW

Runtime switch:
  LLM → switch_provider → local executor → update config → rebuild provider
  LLM → connect_mcp_server → local executor → mcp_host.add_server() → register tools
```

## 3. Provider Configuration

### Config

`ProviderConfig` already has `base_url`, `model`, `api_key`, `tool_mode`. No
new fields are added. The change is behavioral: `build_provider()` actually reads
them instead of ignoring them.

### provider_factory.py

```
build_provider(config: Config, check_live: bool = False) -> LLMProvider
```

1. If `config.provider.base_url` is set: use it directly. Requires `model`
   (and `api_key` for cloud endpoints). Returns `LocalProvider(base_url, model,
   api_key=api_key, tool_mode=tool_mode)`.
2. If `base_url` is null/empty: auto-detect local servers (current behavior
   fallback). Tries Ollama at `:11434`, then LM Studio at `:1234`.
3. `check_live=True`: after creating provider, sends a minimal chat request
   (single user message `"ping"` with no tools) to verify the endpoint responds.
   If the response is an HTTP error or the JSON is malformed, raises
   `ConnectionError`. Used by `switch_provider` to fail fast before replacing
   the active provider. Note: this does consume a small amount of tokens on
   cloud providers — acceptable for an explicit user-initiated switch.
4. `tool_mode` from config: `"native"`, `"prompted-json"`, or `"auto"`.

Config example for OpenRouter:
```json
{
  "provider": {
    "base_url": "https://openrouter.ai/api/v1",
    "model": "anthropic/claude-sonnet-4",
    "api_key": "sk-or-...",
    "tool_mode": "native"
  }
}
```

### Runtime switching

Two new tools exposed to the LLM (executor = `"local"`):

| Tool | Destructive | Args |
|------|-------------|------|
| `get_provider_status` | No | — (returns current base_url, model, tool_mode, connected) |
| `switch_provider` | Yes (money) | base_url, model, api_key, tool_mode, confirm_ok |

`switch_provider` flow:
1. Receives args → updates `config.provider` fields → persists config
2. Calls `provider_factory.build_provider(config, check_live=True)`
3. If live check fails → returns error, does NOT update the active provider
4. If live check passes → calls `server.rebuild_provider(new_provider)`
5. Returns success with new provider details

### Server.rebuild_provider()

Creates a new `LocalProvider` from current config, replaces `self.provider`.
Chat history is preserved (messages are stored on Server, not on Provider).
No restart needed.

## 4. MCP Host

### MCPClient

One instance per MCP server connection.

```
class MCPClient:
    def __init__(self, name: str, transport: Transport)
    def connect(self) -> bool              # Establish connection + initialize
    def disconnect(self)
    def list_tools(self) -> list[ToolSpec] # Call tools/list, convert to ToolSpecs
    def call_tool(self, name: str, args: dict) -> dict  # Call tools/call
```

Tool name conversion: MCP server tool `"read_file"` from server `"filesystem"`
becomes `"filesystem__read_file"` in ReaMind. Description prefixed with
`[MCP: filesystem]`. Executor tag = `"mcp"`.

**Destructive detection:** MCP's `tools/list` response may include
`annotations.destructiveHint: true` on a tool. When present, the ReaMind
ToolSpec gets `destructive=True, return_confirmation=True`. When absent,
the tool is treated as non-destructive (safer default for external tools).

### MCPHost

Singleton owned by `Server`. Manages the collection of MCP clients.

```
class MCPHost:
    def add_server(self, name: str, config: dict) -> MCPClient
    def remove_server(self, name: str)
    def get_all_tools(self) -> list[ToolSpec]
    def execute(self, call: ToolCall) -> dict
    def list_servers(self) -> list[dict]
```

`execute()` parses the namespace prefix from `call.name`, finds the matching
client, strips the prefix, and calls `client.call_tool()`.

### MCP Protocol (`mcp/protocol.py`)

Minimal JSON-RPC 2.0 — only the methods needed for tool use:

```
def send_request(id: int, method: str, params: dict) -> dict
def send_notification(method: str, params: dict) -> dict
def parse_response(data: dict) -> dict | None   # None for notifications
```

Methods used:
- `initialize` — sent at connect, returns server capabilities
- `notifications/initialized` — sent after initialize
- `tools/list` — discover tools
- `tools/call` — invoke a tool

### Transport: Stdio (`mcp/stdio.py`)

Uses `subprocess.Popen`. JSON-RPC messages are line-delimited (one JSON object
per line) over stdin/stdout.

```
class StdioTransport:
    def __init__(self, command: str, args: list[str], env: dict | None)
    def start(self)        # Spawn subprocess
    def stop(self)         # Terminate subprocess
    def send(self, msg: dict)   # Write JSON line to stdin
    def recv(self) -> dict      # Read JSON line from stdout (blocking)
```

Example config:
```json
{
  "name": "filesystem",
  "transport": "stdio",
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-filesystem", "/path"],
  "env": {}
}
```

### Transport: SSE (`mcp/sse.py`)

Connects to an HTTP endpoint using `urllib.request`. Requests are sent via HTTP
POST to a message endpoint. Responses arrive via SSE stream from a separate GET
endpoint.

```
class SSETransport:
    def __init__(self, url: str)
    def start(self)        # Open SSE connection, get message endpoint URL
    def stop(self)         # Close connection
    def send(self, msg: dict)    # POST JSON to message endpoint
    def recv(self) -> dict       # Read next SSE event (blocking)
```

The SSE transport follows the MCP Streamable HTTP transport pattern:
1. GET the SSE endpoint → receives `endpoint` event with a session-scoped POST URL
2. POST JSON-RPC messages to that URL
3. Receive responses via the SSE stream

Example config:
```json
{
  "name": "remote_tools",
  "transport": "sse",
  "url": "https://my-mcp.example.com/mcp"
}
```

### Config schema (`config.py`)

New `MCPConfig` dataclass:

```python
@dataclass
class MCPConfig:
    name: str = ""
    transport: str = "stdio"      # "stdio" | "sse"
    command: str = ""             # stdio: executable
    args: list[str] = field(default_factory=list)  # stdio: args
    env: dict = field(default_factory=dict)        # stdio: env vars
    url: str = ""                 # sse: endpoint URL
```

`Config.mcp_servers` changes from `list` to `list[MCPConfig]`.

## 5. Runtime MCP Management

### New local tools

| Tool | Destructive | Args |
|------|-------------|------|
| `list_mcp_servers` | No | — (returns name, transport, status, tool_count per server) |
| `connect_mcp_server` | No | name, transport, command/args/env (stdio) or url (sse) |
| `disconnect_mcp_server` | Yes | name, confirm_ok |

### Server integration

On startup, `Server.__init__()`:
1. Creates `self.mcp_host = MCPHost()`
2. For each entry in `config.mcp_servers`: `mcp_host.add_server()` + register tools
3. MCP tools are registered in the same `ToolRegistry` as core tools

The merged executor in `handle_user_message()` adds MCP as third fallback:
```
def merged(call):
    result = standard_local_executor(call)      # config tools
    if not result["ok"] and is_unknown_error(result):
        result = library_executor(call)          # Phase 5 tools
        if not result["ok"] and is_unknown_error(result):
            result = mcp_host_executor(call)     # MCP tools
    return result
```

### Tool registry changes

`ToolRegistry` gains:
- `unregister_prefix(prefix: str)` — removes all tools whose name starts with
  `prefix__`. Used when disconnecting an MCP server.

### Safety

- MCP tools that declare themselves destructive in `tools/list` response get
  `destructive=True, return_confirmation=True` on the ReaMind ToolSpec.
- `disconnect_mcp_server` is gated with `return_confirmation=True`.
- `connect_mcp_server` is NOT gated — adding tools is always safe.

## 6. Testing

All tests in Python companion test suite. No Lua changes.

### New test files

| File | What it covers |
|------|---------------|
| `test_provider_factory.py` | Factory resolves config; explicit base_url takes priority over auto-detect; error on missing model/api_key for cloud; auto-detect fallback when base_url is null; `check_live=True` connectivity test |
| `test_mcp_protocol.py` | JSON-RPC 2.0 encode/decode; request/response ID matching; notification (no ID); error response parsing |
| `test_mcp_stdio.py` | Spawn with command+args; send/receive line-delimited JSON; handle subprocess exit; initialize handshake |
| `test_mcp_sse.py` | HTTP POST sends request; SSE stream parsing; endpoint URL normalization; connection error handling |
| `test_mcp_host.py` | Add/remove servers (memory transport, no real subprocess); tool namespacing (`server__tool_name`); executor routing parses namespace; `get_all_tools()` merged list; unregister on remove |
| `test_mcp_runtime.py` | `list_mcp_servers`, `connect_mcp_server`, `disconnect_mcp_server` tool specs; confirmation gate on disconnect |
| `test_provider_runtime.py` | `get_provider_status`, `switch_provider` tool specs; switch is destructive+gated; live check failure prevents switch |

### Modified test files

| File | Change |
|------|--------|
| `test_config.py` | Add MCPConfig serialization/deserialization test |
| `test_server.py` | MCP host init, merged executor MCP routing, provider rebuild preserves history |

## 7. Scope Boundaries

### In scope
- MCP host with stdio and SSE transports
- Tool discovery, namespacing, and routing
- Runtime MCP server add/remove via LLM tools
- Flexible provider configuration via `build_provider()` factory
- Runtime provider switching via LLM tools
- OpenRouter support (via flexible config + LocalProvider)

### Out of scope
- Anthropic/OpenAI native provider classes (interface stays open)
- Model listing/discovery (complex, unreliable across backends — config-value only)
- Streaming SSE from providers (future enhancement)
- MCP resource/prompt capabilities (tools only)
- MCP server auto-discovery (user explicitly configures)
- Lua panel changes (no UI for MCP or provider switching)
- Persistent MCP connections across companion restarts (always fresh connect)
