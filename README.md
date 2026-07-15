# ReaMind

An AI assistant for the [REAPER](https://www.reaper.fm/) digital audio
workstation. Chat with an LLM to inspect your sessions, create tracks, wire
routing, insert FX, manage your sample library, and more — all from a
ReaImGui panel inside REAPER.

**Runs 100% locally** — uses Ollama or LM Studio by default. OpenRouter/OpenAI
cloud providers are optional. Zero runtime Python dependencies beyond the
standard library.

## Features

- **Chat interface** inside REAPER via ReaImGui
- **30+ tools** for session construction, routing, FX insertion, and library management
- **Track management** — create, delete, rename, recolor, organize into folders
- **Routing** — sends, receives, sidechain compression
- **FX insertion** — insert stock REAPER effects by name
- **Templates** — one-command multi-step session setups
- **Project library management** — scan for orphaned media, duplicates, nested projects; quarantine and reclaim
- **MCP support** — connect to external tool servers over stdio or HTTP/SSE
- **Pluggable LLM providers** — Ollama, LM Studio, OpenRouter, OpenAI, any OpenAI-compatible API
- **Safety-first** — every action is undo-wrapped; destructive actions require explicit confirmation
- **Customizable theme** — dark and light presets with color overrides
- **Windows, macOS, Linux** — all platform paths handled

## Quick Start

### Prerequisites

- REAPER with [ReaImGui](https://github.com/cfillion/reaimgui) (via ReaPack) and SWS Extension
- Python 3.11+
- A local LLM server (Ollama recommended) or an API key for OpenRouter/OpenAI

### Install Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:7b
```

### Set up the companion

**Linux/macOS:**

```bash
git clone https://github.com/bradzgar/reamind.git
cd reamind/companion
python -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

**Windows:**

```powershell
git clone https://github.com/bradzgar/reamind.git
cd reamind\companion
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

### Install the Lua panel

```bash
python scripts/install_panel.py
```

This copies the panel files into REAPER's `Scripts/ReaMind/` directory.

Then in REAPER: **Actions → Show action list → ReaScript: Load...** and
select `reamind_panel.lua`. Optionally add it to `__startup.lua` for
auto-launch.

### Launch

**Linux/macOS:**
```bash
cd reamind/companion
.venv/bin/python -m reamind.server
```

**Windows:**
```powershell
cd reamind\companion
.venv\Scripts\activate
python -m reamind.server
```

Open the panel in REAPER. The companion auto-detects Ollama and picks the
first available model. Config is auto-created at `~/.config/reamind/config.json`.

## Architecture

```
┌──────────┐   JSON bridge   ┌───────────┐   HTTP/Ollama   ┌──────┐
│ Lua      │ ←─────────────→ │ Python    │ ←─────────────→ │ LLM  │
│ ReaImGui │   /bridge/      │ companion │                 │      │
│ panel    │                  │           │                 └──────┘
└────┬─────┘                  └─────┬─────┘
     │                              │
     │ REAPER API                   │ MCP
     ▼                              ▼
┌──────────┐                 ┌──────────────┐
│ REAPER   │                 │ External MCP │
│ session  │                 │ tool servers │
└──────────┘                 └──────────────┘
```

- **Lua panel** — the only code with REAPER API access. Thin layer that relays tool calls.
- **Python companion** — LLM agent loop, tool registry, MCP host, library management.
- **JSON bridge** — atomic file-based communication under `bridge/`.
- **MCP servers** — optional external tool providers (filesystem, databases, custom plugins).

## Configuration

All settings in `~/.config/reamind/config.json` (or `%APPDATA%/reamind/` on Windows). Auto-created on first launch.

Full reference in [USER_GUIDE.md](USER_GUIDE.md).

## Running Tests

**Linux/macOS:**
```bash
cd companion
.venv/bin/python -m pytest -v
```

**Windows:**
```powershell
cd companion
.venv\Scripts\activate
python -m pytest -v
```

**Lua tests (all platforms):**
```bash
cd panel
lua test/json_spec.lua && lua test/helpers_spec.lua
```

## Docs

- [USER_GUIDE.md](USER_GUIDE.md) — full reference with all 31 tools, configuration, MCP setup
- [docs/SMOKE.md](docs/SMOKE.md) — manual smoke test checklist
- [docs/superpowers/specs/](docs/superpowers/specs/) — design specifications for each phase

## License

MIT — see [LICENSE](LICENSE)
