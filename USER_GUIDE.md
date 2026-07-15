# ReaMind User Guide

ReaMind is an AI assistant embedded in the REAPER digital audio workstation. It
helps you build sessions, route tracks, inspect projects, manage your sample
library, and more — all through natural language chat. ReaMind connects to a
local LLM (Ollama, LM Studio) or a cloud provider (OpenRouter, OpenAI) and
executes actions inside REAPER through a companion process.

**ReaMind never hard-deletes your files.** Destructive actions require explicit
confirmation, and all operations are undo-wrapped inside REAPER.

---

## Table of Contents

1. [Installation](#installation)
2. [First Launch](#first-launch)
3. [Configuration](#configuration)
4. [Chat Interface](#chat-interface)
5. [Tool Reference](#tool-reference)
6. [LLM Providers](#llm-providers)
7. [MCP Servers](#mcp-servers)
8. [Library Management](#library-management)
9. [Theming](#theming)
10. [Templates](#templates)
11. [Troubleshooting](#troubleshooting)

---

## Installation

### Prerequisites

- **REAPER** with **ReaImGui** installed (via ReaPack) and **SWS Extension**
- **Python 3.11+** (only stdlib required — no pip dependencies for runtime)
- **A model server** — Ollama or LM Studio (free, local) or an API key for
  OpenRouter / OpenAI

### Install Ollama (recommended)

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:7b    # or any tool-capable model
```

### Set up the companion

**Linux/macOS:**

```bash
git clone https://github.com/bradzgar/reamind.git ~/projects/reamind
cd ~/projects/reamind/companion
python -m venv .venv
.venv/bin/pip install -e ".[dev]"   # pytest is the only dev dependency
```

**Windows:**

```powershell
git clone https://github.com/bradzgar/reamind.git %USERPROFILE%\projects\reamind
cd %USERPROFILE%\projects\reamind\companion
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"   # pytest is the only dev dependency
```

### Install the Lua panel

Run the installer script from the repo root:

```bash
python scripts/install_panel.py
```

This copies the panel files into REAPER's `Scripts/ReaMind/` directory. It
auto-detects the REAPER resource path for your platform.

Then in REAPER:

1. **Actions → Show action list**
2. Click **ReaScript: Load...**
3. Select `reamind_panel.lua` from `Scripts/ReaMind/`
4. Add the action to REAPER's `__startup.lua` or run it manually

---

## First Launch

### 1. Start your model server

```bash
ollama serve    # usually auto-starts with systemd, or run manually
```

### 2. Start the companion

**Linux/macOS:**
```bash
cd ~/projects/reamind/companion
.venv/bin/python -m reamind.server
```

**Windows:**
```powershell
cd %USERPROFILE%\projects\reamind\companion
.venv\Scripts\activate
python -m reamind.server
```

The companion auto-detects Ollama on `:11434` and LM Studio on `:1234`. It
picks the first available server and model. Config is auto-created at
`~/.config/reamind/config.json` if it doesn't exist.

### 3. Open the panel in REAPER

Run the ReaMind panel — it will show connection status, active model, and a
chat input. Type a message to begin.

---

## Configuration

Config lives at `~/.config/reamind/config.json` (Linux/macOS) or
`%APPDATA%/reamind/config.json` (Windows). It's auto-created on first launch
with sensible defaults.

### Full config example

```json
{
  "provider": {
    "name": "local",
    "model": null,
    "base_url": null,
    "api_key": null,
    "tool_mode": "auto"
  },
  "theme": {
    "preset": "dark",
    "colors": {}
  },
  "projects_roots": [],
  "quarantine_dir": "~/.config/reamind/quarantine",
  "mcp_servers": [],
  "templates_dir": "",
  "safety": {
    "confirm_destructive": true,
    "max_tool_iterations": 8,
    "tool_timeout_s": 30.0
  },
  "bridge_dir": ""
}
```

### `provider`

| Key | Default | Description |
|-----|---------|-------------|
| `name` | `"local"` | Provider label (informational) |
| `model` | `null` | Model name. When `null`, auto-detects from the server. |
| `base_url` | `null` | API endpoint. When `null`, auto-detects Ollama (:11434) then LM Studio (:1234). Set for cloud providers. |
| `api_key` | `null` | API key for cloud providers. Not needed for local Ollama/LM Studio. |
| `tool_mode` | `"auto"` | Tool-calling mode. `"auto"` resolves to `"native"`. Also accepts `"prompted-json"`. |

### `safety`

| Key | Default | Description |
|-----|---------|-------------|
| `confirm_destructive` | `true` | Require `confirm_ok: true` before destructive actions execute. |
| `max_tool_iterations` | `8` | Maximum tool calls per chat turn. Prevents infinite loops. |
| `tool_timeout_s` | `30.0` | Seconds to wait for a REAPER-side tool response. |

### `mcp_servers`

List of MCP server configurations to connect at startup. See [MCP Servers](#mcp-servers) for details.

### `projects_roots`

List of directories containing REAPER projects. Used by library scanning. Add
paths here or via the `set_projects_root` tool.

### `quarantine_dir`

Where quarantined files go. Each quarantine action creates a date-stamped
subdirectory (e.g. `2026-07-15/`). Files are moved, never deleted.

### `bridge_dir`

Directory for the JSON file bridge between panel and companion. Defaults to
`bridge/` alongside the companion source. Usually doesn't need changing.

---

## Chat Interface

The ReaMind panel is a ReaImGui window with:

- **Status bar** — shows the active model, connection health, MCP server count
- **Chat area** — conversation scrollback
- **Input field** — type a message and press Enter
- **Settings** (in status panel) — theme controls, model info

### How conversations work

1. You type a message in the panel
2. The companion sends it to the LLM along with a list of available tools
3. The LLM may respond directly or call tools to inspect/modify your session
4. Tool calls are executed and results fed back to the LLM
5. The final response appears in the chat window

### Confirmation gating

Destructive tools require confirmation. When ReaMind wants to call a
destructive tool (e.g. `delete_track`, `quarantine_files`), it must provide
`"confirm_ok": true` in the arguments. The first attempt without confirmation
is blocked, and ReaMind asks you to confirm before re-invoking.

Tools requiring confirmation:

| Tool | Category |
|------|----------|
| `delete_track` | Track construction |
| `quarantine_files` | Library management |
| `reclaim_space` | Library management |
| `consolidate_project` | Library management |
| `unnest_project` | Library management |
| `switch_provider` | System |
| `disconnect_mcp_server` | MCP management |

### Undo safety

Every REAPER-side tool call is automatically wrapped in an Undo point. Use
Ctrl+Z in REAPER to undo any single action or chain of actions.

---

## Tool Reference

ReaMind has 30+ tools organized by category. The LLM chooses which tools to
call based on your request.

### Read-Only Tools

These inspect your project — they never modify anything.

**`get_project_summary`** — Returns track count, tempo, sample rate, and current selection.

*No parameters.*

**`list_tracks`** — Lists all tracks with index, name, GUID, color, parent/folder
depth, FX names, and sends/receives. Use this before making changes.

*No parameters.*

**`get_track`** — Returns detailed info for one track, addressed by its GUID.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `track_guid` | string | Yes | Track GUID, e.g. `{AB12C345-...}` |

---

### Construction Tools

These create, modify, or delete tracks and routing. Most are REAPER-side and
undo-wrapped.

**`create_track`** — Create a new track. Optionally set its name, color, position,
and parent folder.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | Yes | Track name |
| `color` | integer | No | REAPER color code (0xRRGGBB) |
| `position` | integer | No | Insert position (0-based, -1 for last) |
| `parent_guid` | string | No | GUID of parent folder track |

**`create_folder`** — Create a folder track containing the given child tracks.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | Yes | Folder name |
| `child_guids` | array of string | No | GUIDs of tracks to move into this folder |

**`set_track_props`** — Update properties of an existing track. Only specified
fields are changed.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `track_guid` | string | Yes | Track GUID |
| `name` | string | No | New track name |
| `color` | integer | No | REAPER color code |
| `volume_db` | number | No | Volume in dB |
| `pan` | number | No | Pan (-1.0 to 1.0) |
| `record_arm` | boolean | No | Arm track for recording |
| `input` | string | No | Input assignment, e.g. `"Input: Mono"` |

**`delete_track`** — Delete a track by GUID. **Destructive — requires confirmation.**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `track_guid` | string | Yes | Track GUID to delete |
| `confirm_ok` | boolean | — | Set to `true` to confirm |

**`add_send`** — Create a send from a source track to a destination track.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `src_guid` | string | Yes | Source track GUID |
| `dst_guid` | string | Yes | Destination track GUID |
| `gain_db` | number | No | Send gain in dB (default 0) |
| `is_pre_fader` | boolean | No | Pre-fader send |

**`add_receive`** — Add a receive on a destination track from a source track.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `src_guid` | string | Yes | Source track GUID |
| `dst_guid` | string | Yes | Destination track GUID |
| `gain_db` | number | No | Receive gain in dB (default 0) |

**`create_sidechain`** — Wire a source track into channels 3/4 of a target
track's FX instance.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `source_guid` | string | Yes | Source track GUID |
| `target_guid` | string | Yes | Target track GUID (where FX lives) |
| `target_fx_index` | integer | No | FX index on target track (-1 for last) |

**`insert_fx`** — Insert a stock REAPER effect on a track by friendly name.
Examples: `"eq"`, `"compressor"`, `"reverb"`, `"delay"`, `"gate"`.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `track_guid` | string | Yes | Target track GUID |
| `fx_name` | string | Yes | Friendly name or REAPER identifier |
| `position` | integer | No | Insert position (-1 for last) |

**`set_fx_param`** — Set a named or indexed parameter on a track's FX instance.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `track_guid` | string | Yes | Track GUID |
| `fx_index` | integer | Yes | FX instance index |
| `param` | string | Yes | Parameter name or numeric index |
| `value` | number | Yes | Parameter value |

**`list_available_fx`** — List all installed FX plugins available in REAPER.
Results are cached on startup.

*No parameters.*

**`undo_point`** — Name the current undo point. Each tool call is already
undo-wrapped; this lets ReaMind add descriptive names for multi-step
operations.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | Yes | Descriptive name for this undo point |

**`apply_template`** — Apply a named session template. Templates are JSON files
in the `templates/` directory. See [Templates](#templates).

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `template_name` | string | Yes | Template file name without `.json` extension |

---

### Library Management Tools

These scan your project directories, detect issues, and help you clean up.
See [Library Management](#library-management) for workflow details.

**`scan_root`** — Scan a REAPER project root directory for issues: nested
projects, orphaned media, duplicates, regenerable files, external media,
missing media. Returns summary counts.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | Yes | Absolute path to the project root directory |

**`list_findings`** — List detailed findings from a scanned project root.
Optionally filter by finding type.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `root` | string | Yes | Project root path that was scanned |
| `type` | string | No | Filter: `nested_project`, `orphaned_media`, `regenerable`, `external_media`, `duplicate`, `missing_media` |

**`get_file_details`** — Get detailed info about a file: size, modification
date, SHA-256 hash, and whether it exists.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | Yes | Absolute path to the file |

**`list_quarantine_batches`** — List past quarantine batches with date, file
count, and total size. Quarantine is date-stamped — each batch is a
subdirectory under `quarantine_dir`.

*No parameters.*

**`quarantine_files`** — Move files to a dated quarantine folder. Files are
**NOT deleted** — they can be restored manually. **Requires confirmation.**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `paths` | array of string | Yes | Absolute paths to files to quarantine |
| `confirm_ok` | boolean | — | Set to `true` to confirm |

**`reclaim_space`** — Delete regenerable files: `.reapeaks`, `.RPP-UNDO`,
`*.RPP-bak`. These are automatically regenerated by REAPER. **Requires
confirmation.**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `root` | string | No | Project root to scan. If omitted, uses all configured `projects_roots`. |
| `confirm_ok` | boolean | — | Set to `true` to confirm |

**`consolidate_project`** — Copy externally-referenced media files into the
project directory. Does NOT modify the `.RPP` file — save from REAPER with
"Copy media" checked afterward. **Requires confirmation.**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_path` | string | Yes | Path to the `.RPP` file to consolidate |
| `confirm_ok` | boolean | — | Set to `true` to confirm |

**`unnest_project`** — Copy a nested `.RPP` to its own top-level folder under
`projects_root`. The original is left in place for verification. **Requires
confirmation.**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_path` | string | Yes | Path to the nested `.RPP` file |
| `confirm_ok` | boolean | — | Set to `true` to confirm |

**`set_projects_root`** — Add a directory to the configured project roots for
library scanning.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `path` | string | Yes | Absolute path to add to `projects_roots` |

---

### System Tools

**`server_status`** — Returns available model servers and their models. Detects
Ollama and LM Studio on localhost.

*No parameters.*

**`get_provider_status`** — Returns current provider configuration:
`base_url`, `model`, `tool_mode`, and whether the provider appears connected.

*No parameters.*

**`update_provider_config`** — Update the provider configuration. Changes are
persisted to `config.json`. Existing connections are not disrupted — restart
or call `switch_provider` to apply.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `model` | string | No | New model name |
| `base_url` | string | No | New API endpoint |
| `api_key` | string | No | New API key |
| `tool_mode` | string | No | Tool mode: `native`, `prompted-json`, or `auto` |

**`switch_provider`** — Switch to a different LLM provider or model. Updates
config, verifies the new endpoint is reachable, and rebuilds the provider
live — no restart needed. **Destructive — requires confirmation (this
may incur costs on cloud providers).**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `base_url` | string | No | Provider API endpoint |
| `model` | string | No | Model name |
| `api_key` | string | No | API key for the provider |
| `tool_mode` | string | No | Tool calling mode |
| `confirm_ok` | boolean | Yes | Set to `true` to confirm the switch |

---

### MCP Management Tools

These manage connections to external MCP (Model Context Protocol) servers.
See [MCP Servers](#mcp-servers) for setup.

**`list_mcp_servers`** — List all connected MCP servers with name, transport
type, connection status, and tool count.

*No parameters.*

**`connect_mcp_server`** — Connect to an MCP server at runtime and register
its tools. New tools become immediately available to the LLM.

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | Yes | Name for this MCP server (used as tool prefix) |
| `transport` | string | Yes | `"stdio"` or `"sse"` |
| `command` | string | No | Executable (stdio transport only) |
| `args` | array of string | No | Arguments (stdio transport only) |
| `env` | object | No | Environment variables (stdio transport only) |
| `url` | string | No | SSE endpoint URL (sse transport only) |

**`disconnect_mcp_server`** — Disconnect from an MCP server and unregister
its tools. **Destructive — requires confirmation.**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `name` | string | Yes | Name of the MCP server to disconnect |
| `confirm_ok` | boolean | Yes | Set to `true` to confirm disconnection |

---

## LLM Providers

ReaMind uses any OpenAI-compatible API. The companion auto-detects local
servers; cloud providers need explicit config.

### Local: Ollama (default)

No config needed. The companion detects Ollama on `localhost:11434`
automatically. Pull a model first:

```bash
ollama pull qwen2.5:7b
ollama pull llama3.1:8b
```

Any model that supports function/tool calling works.

### Local: LM Studio

Start LM Studio, load a model, enable the local server on port `1234`. The
companion detects it automatically if Ollama isn't running.

### Cloud: OpenRouter

Edit `~/.config/reamind/config.json`:

```json
{
  "provider": {
    "base_url": "https://openrouter.ai/api/v1",
    "model": "anthropic/claude-sonnet-4",
    "api_key": "sk-or-v1-..."
  }
}
```

Restart the companion, or use `switch_provider` from within the chat:

> "Switch to OpenRouter using model anthropic/claude-sonnet-4"

### Cloud: OpenAI

```json
{
  "provider": {
    "base_url": "https://api.openai.com/v1",
    "model": "gpt-4o",
    "api_key": "sk-..."
  }
}
```

### Switching providers mid-session

Use `switch_provider`:

> "Switch to my local Ollama with model llama3.1:8b"

ReaMind verifies the new endpoint before switching. If the new endpoint is
unreachable, the change is rejected and the current provider stays active.
Chat history is preserved.

### Tool calling modes

| Mode | Description |
|------|-------------|
| `auto` (default) | Resolves to `native` for OpenAI-compatible APIs |
| `native` | Standard OpenAI function-calling format |
| `prompted-json` | Prompts the model to output JSON (for models without native tool support) |

Change via config or `switch_provider` tool.

---

## MCP Servers

MCP (Model Context Protocol) servers expose external tools to ReaMind —
filesystem access, database queries, web searches, or custom plugins. Tools
are namespaced: a server named `"filesystem"` with a tool `"read"` becomes
`filesystem__read`.

### Supported transports

| Transport | Description |
|-----------|-------------|
| `stdio` | Spawns a subprocess. Most common. Command + args. |
| `sse` | Connects to an HTTP endpoint via Server-Sent Events. |

### Configuring startup MCP servers

Add entries to `config.json`:

```json
{
  "mcp_servers": [
    {
      "name": "filesystem",
      "transport": "stdio",
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-filesystem", "/home/user/projects"]
    }
  ]
}
```

Servers connect at companion startup. Connection failures log a warning to
stderr but don't prevent startup — other servers still load.

### Runtime MCP management

Connect to a new MCP server mid-session:

> "Connect to a filesystem MCP server using npx that gives access to /home/user/samples"

Disconnect:

> "Disconnect the filesystem MCP server"

### Tool namespacing

MCP tools are prefixed with the server name to avoid collisions with built-in
ReaMind tools. A tool `read_file` from server `"fs"` appears as
`fs__read_file`. Descriptions are prefixed with `[MCP: fs]` so you can
identify which server provides which tools.

MCP tools that declare themselves destructive (via `annotations.destructiveHint`)
automatically inherit confirmation gating — same as built-in destructive tools.

---

## Library Management

ReaMind can scan your REAPER project directories and help you clean up.

### Setup

Add your project directories to `projects_roots` in config or use the tool:

> "Add /home/user/REAPER Projects to my project roots"

### Scanning

> "Scan my project root /home/user/REAPER Projects"

Returns a summary with file counts and issue counts.

### Finding types

| Type | Description |
|------|-------------|
| `nested_project` | A `.RPP` inside another project's directory |
| `orphaned_media` | Media files not referenced by any `.RPP` |
| `regenerable` | `.reapeaks`, `.RPP-UNDO`, `*.RPP-bak` — auto-regenerated by REAPER |
| `external_media` | Media files outside the project directory |
| `duplicate` | Identical files (same SHA-256 hash) |
| `missing_media` | Files referenced by an `.RPP` but not found on disk |

### Typical workflow

1. **Scan** a project root: `scan_root("/path/to/projects")`
2. **Inspect findings**: `list_findings("/path/to/projects", "duplicate")`
3. **Quarantine** unwanted files: moves them to a date-stamped folder (safe, reversible)
4. **Reclaim space**: deletes only regenerable files (`.reapeaks`, `.RPP-UNDO`, `*.RPP-bak`)
5. **Consolidate**: copies external media into the project directory
6. **Unnest**: moves nested projects to their own top-level folders

### Safety

- **Quarantine never deletes** — files go to `~/.config/reamind/quarantine/YYYY-MM-DD/`
- **Reclaim only deletes regenerable files** — REAPER rebuilds them automatically
- **All destructive library actions require confirmation** (`confirm_ok: true`)
- **Quarantine batches are tracked** — use `list_quarantine_batches` to review history

---

## Theming

ReaMind includes a dark theme (default) and a light theme. Theme settings are
in `config.json` under the `theme` key.

```json
{
  "theme": {
    "preset": "dark",
    "colors": {}
  }
}
```

| `preset` | Description |
|----------|-------------|
| `"dark"` | Dark background, light text (default) |
| `"light"` | Light background, dark text |

Override specific colors by adding entries to `colors`. Keys follow the
ReaImGui color constant names. Changes take effect on next panel reload.

The panel's settings pane (accessible from the status area) also allows
toggling between presets.

---

## Templates

Templates are JSON files that describe multi-step session setups. They live
in the `templates/` directory alongside the companion source.

### Template format

```json
[
  {"tool": "create_track", "args": {"name": "Kick", "color": 0xFF4444}},
  {"tool": "create_track", "args": {"name": "Snare", "color": 0x44FF44}},
  {"tool": "add_send", "args": {"src_guid": "...", "dst_guid": "...", "gain_db": -6}}
]
```

Each step is a tool name + arguments object. Steps execute sequentially. If a
step fails, remaining steps still execute but the result reports completion
count vs total.

### Using templates

> "Apply the drum_kit_7mic template"

ReaMind looks for `templates/drum_kit_7mic.json`.

### Built-in templates

Check `companion/templates/` for included templates. Create your own by
adding `.json` files to that directory.

---

## Troubleshooting

### Companion won't start

```
RuntimeError: No local model server found
```

Start Ollama or LM Studio first, then retry.

```
RuntimeError: No models available at http://localhost:11434
```

Pull a model: `ollama pull qwen2.5:7b`

### Panel shows "Disconnected"

1. Check the companion process is running
2. Verify the bridge directory exists (default: `bridge/` next to companion source)
3. Check `bridge/status.json` — should show server info

### Tool calls time out

Increase `safety.tool_timeout_s` in config (default 30 seconds). Some REAPER
operations take longer.

### LLM calls wrong tools

- Make sure your model supports tool/function calling
- Try setting `tool_mode` to `"prompted-json"` if native mode produces poor results
- Smaller models (7B) work well for simple operations; complex multi-step
  workflows benefit from larger models (70B+ or cloud models)

### MCP server won't connect

- Check the command is available: `which npx` or `which python`
- For stdio servers, verify the command + args work when run manually
- For SSE servers, verify the URL is reachable: `curl https://myserver/mcp`
- Connection errors are logged to stderr on companion startup

### Quarantined files — how to recover

Files moved to `~/.config/reamind/quarantine/YYYY-MM-DD/` can be moved back
manually:

```bash
mv ~/.config/reamind/quarantine/2026-07-15/some_file.wav /original/location/
```

### Changing config

Edit `~/.config/reamind/config.json` directly with any text editor, or use
ReaMind's chat:

> "Update my provider config to use OpenRouter"
> "Add /home/user/New Projects to my project roots"

### Logs and debugging

- Companion output goes to stdout/stderr — run in a terminal to see errors
- Bridge files are in `bridge/` — `status.json` shows current state
- Chat history is in-memory only (not persisted across restarts)
