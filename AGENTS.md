# ReaMind — Agent Quickstart

## Architecture

Two independent sides communicating through atomic JSON files in `bridge/`:

| Side | Language | Location | Role |
|------|----------|----------|------|
| Panel | Lua (ReaImGui) | `panel/` | Chat UI, ReaScript tool executors — **only code with REAPER API access** |
| Companion | Python 3.11+ | `companion/` | LLM agent loop, tool registry, MCP host, library mgmt |

No other IPC — everything goes through `bridge/{inbox,chat,requests,results,status.json,heartbeat.json}`.

## Commands

```bash
# Python tests
cd companion && .venv/bin/python -m pytest -v

# Python single test
cd companion && .venv/bin/python -m pytest tests/test_server.py::test_name -v

# Lua tests (run from panel/ dir, NOT panel/test/)
cd panel && lua test/construction_spec.lua
cd panel && lua test/helpers_spec.lua
cd panel && lua test/json_spec.lua
cd panel && lua test/theme_spec.lua
```

## Constraints

- **Stdlib-only for runtime** — `pytest` is the ONLY dev dependency. No `requests`, `httpx`, `aiohttp`, etc.
- **Python 3.11+** — `str | None` syntax used throughout.
- **No Lua changes needed** for companion-only features — most work is Python-side.
- **Conventional Commits** — `feat:`, `fix:`, `docs:`, `chore:`, `test:`.
- Branch from `master`, merge back when done.

## Key files to know

| File | What |
|------|------|
| `companion/reamind/server.py` | Companion entrypoint (`python -m reamind.server`). Wires provider, registry, bridge, MCP host. |
| `companion/reamind/agent.py` | `run_turn()` — LLM loop; `_execute_call()` — confirmation gating + executor routing |
| `companion/reamind/providers/base.py` | `ToolSpec`, `ToolCall`, `Message`, `ChatResult`, `LLMProvider` ABC |
| `companion/reamind/providers/local.py` | `LocalProvider` — OpenAI-compatible (Ollama, LM Studio, OpenRouter). `detect_servers()`, `list_models()` |
| `companion/reamind/providers/fake.py` | `FakeProvider` — scripted responses for tests |
| `companion/reamind/config.py` | `Config`, `ProviderConfig`, `MCPConfig`, `SafetyConfig` — `load()`/`save()` to `~/.config/reamind/config.json` |
| `companion/reamind/tools/registry.py` | `ToolRegistry.register()`/`unregister_prefix()` — all tools live here |
| `companion/reamind/bridge.py` | `Bridge` — atomic JSON file I/O in `bridge/` |
| `companion/reamind/mcp_host.py` | `MCPHost` + `MCPClient` — external tool servers, `{server}__{tool}` namespacing |
| `panel/reamind_panel.lua` | ReaImGui panel — chat UI, settings, companion launcher |
| `panel/ipc.lua` | `write_json_atomic()`/`read_json()`/`push_inbox()`/`write_result()` |

## Gotchas

- **ReaImGui Lua API is NOT 1:1 with C++ ImGui** — there is no `ImGui_GetStyle` or `ImGui_GetIO`. Use `ImGui_PushStyleColor`/`ImGui_PopStyleColor`. Combos need null-terminated items (`"a\0b\0"`).
- **`os.rename()` on Windows fails if target exists** — must `os.remove` first.
- **Concurrent bridge file access** — both sides may read/write same files. `atomic_write_json` retries `os.replace` on `PermissionError`. Lua side uses `pcall(os.remove)`.
- **Tests use FakeProvider** — no live LLM needed for the test suite.
- **`next_id()` counter is global** — tests that check absolute values will fail when run in full suite. Test relative increments instead.
- **Config path is platform-aware** — `~/.config/reamind/` on Linux/macOS, `%APPDATA%/reamind/` on Windows. Use `config.load()`/`config.save()` at runtime; hardcode only in the detection block.
- **Lua test runner** is a zero-dep assert module (`panel/test/run.lua`). Tests use `require("test.run")`, so run from `panel/` dir (not `panel/test/`). No busted/luatest.
