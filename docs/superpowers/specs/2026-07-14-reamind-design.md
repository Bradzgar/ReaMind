# ReaMind — Design Spec

**Date:** 2026-07-14
**Status:** Approved design; ready for implementation planning
**Working name:** ReaMind (rename freely)

## 1. Overview

ReaMind is a chat-driven assistant that lives **inside REAPER** as a docked panel and
automates REAPER workflows through natural language. The near-term product (v1) focuses on
**session construction, routing, stock-FX insertion**, and **REAPER project-library
cleanup/organization**. The long-term vision is a deep "audio engineer" assistant (WAV
analysis, quantize/align, mixing help, LUFS/gain-staging advice); the architecture is chosen
to grow into that without rework.

### Guiding principles
- **User customization is core**, cross-cutting: pluggable LLM providers, user-editable theme,
  templates, system prompt, projects roots, and user-registered tools/MCP servers.
- **Local-first onboarding**: works out of the box against a running local model server with no
  API keys; cloud is supported but optional.
- **Safety first**: undo-wrapped actions, confirmation gating for destructive ops, and
  reversible (quarantine-only) filesystem cleanup.
- **Thin panel, fat companion**: push all real logic into the testable Python companion; keep
  the Lua panel a thin executor.

## 2. Architecture & Components

Chosen approach: **Lua panel (UI + executor) + Python companion (brain), file-based JSON IPC.**

Rationale over alternatives: REAPER's Lua has full ReaScript API access but no HTTP/networking;
the LLM brain needs async HTTP, MCP, and audio libraries. Splitting responsibilities lets each
side do what it's good at. Running everything in REAPER's embedded Python (rejected) is fragile
and can block REAPER's UI thread. Driving REAPER only via the built-in web remote/OSC (rejected)
is too limited and contradicts the native docked-panel requirement.

### Repo layout
```
reamind/
  panel/                    # ReaScript Lua — runs INSIDE REAPER
    reamind_panel.lua        # ReaImGui docked chat UI + executor defer-loop
    tools/                   # Lua implementations of each REAPER tool
    ipc.lua                  # read/write JSON files in the bridge dir
    theme.lua                # map user theme config onto ImGui style
  companion/                # Python — the "brain", external process
    reamind/
      agent.py               # agent/tool-calling loop
      providers/             # pluggable LLM: cloud (Anthropic/OpenAI) + local (Ollama/LM Studio)
      tools/                 # tool schemas (JSON) + local-executor tool impls
      library/               # project-library scan/report/quarantine
      rpp.py                 # .RPP parser (media reference extraction)
      mcp_host.py            # connect to external MCP servers, expose their tools
      bridge.py              # write requests / read results via the IPC dir
      config.py              # load/validate config
      server.py              # process entrypoint + session mgmt + heartbeat
    tests/
    pyproject.toml
  bridge/                   # shared IPC dir (JSON files); runtime-only, git-ignored
  docs/superpowers/specs/   # this spec
```

### Roles
- **Panel (Lua, in REAPER):** the *only* component that touches the ReaScript API. Renders chat,
  captures input, and each frame checks the bridge for pending tool calls, executes them (wrapped
  in undo blocks), writes results back. Launches the companion on startup via `reaper.ExecProcess`.
- **Companion (Python, external):** the brain. Holds conversation state, calls the selected LLM
  with tool schemas, receives tool calls, routes them (REAPER tools → bridge → panel; local tools
  → in-process), feeds results back to the LLM, and streams assistant text to the panel. Hosts MCP
  clients so external toolsets appear as additional tools.
- **Bridge (files):** a shared folder of small JSON files. No sockets/HTTP anywhere.

### Data direction
UI input → companion → LLM → tool calls → (panel executes on REAPER **or** companion executes
locally) → results → companion → LLM → assistant reply → panel displays.

## 3. IPC Protocol & Data Flow

The bridge dir holds small JSON files across two channels.

**Chat channel (companion → panel):** assistant text + status; panel renders it.

**Tool channel (round-trip):**

Request (companion → panel):
```json
{ "id": "call_8f2a", "seq": 12, "tool": "create_track",
  "args": { "name": "Kick In", "color": "#C0392B", "parent": "DRUMS" } }
```

Result (panel → companion):
```json
{ "id": "call_8f2a", "ok": true, "result": { "track_guid": "{AB12...}", "index": 4 } }
```
On failure: `{ "id": "...", "ok": false, "error": "reason" }`.

**Message shapes (schemas):**
- Request: `id` (string), `seq` (int, monotonic), `tool` (string), `args` (object; per-tool).
- Result: `id` (string), `ok` (bool), then `result` (object) **or** `error` (string).

**The loop:**
1. User types → panel appends to `inbox.json` → companion picks it up.
2. Companion sends history + tool schemas to the LLM.
3. LLM returns text (→ panel) or tool call(s).
4. Companion writes each REAPER tool call to `requests/` (local tools run in-process instead).
5. Panel defer loop (~30 fps) reads new requests, executes via ReaScript in an **undo block**,
   writes to `results/`.
6. Companion reads results, feeds them back to the LLM; repeat until final text.

**Why files:** zero networking in Lua; survives either process restarting; trivially
inspectable/debuggable; serializes REAPER access to the main thread.

**Concurrency/safety:** unique `id` per call; panel tracks processed ids (no double-exec);
`seq` preserves ordering; stale files cleared on session start.

## 4. MVP Tool Catalog

### 4.1 REAPER tools (executor tag: `reaper` → bridge → panel)

**Project awareness (read-only)**
- `get_project_summary` — track count, tempo, sample rate, selection.
- `list_tracks` — index, name, GUID, color, parent/folder, FX names, sends/receives.
- `get_track` — detail for one track.

**Track & folder construction**
- `create_track` — name, color, position, parent folder.
- `create_folder` — folder track with children (e.g. "DRUMS").
- `set_track_props` — rename, recolor, volume/pan, record-arm, input assignment.
- `delete_track` (destructive → confirmation-gated).

**Routing**
- `add_send` / `add_receive` — src→dst, pre/post, gain.
- `create_sidechain` — wire source (kick) into dst channels 3/4 of a target FX and arm it.

**Stock FX**
- `insert_fx` — friendly name → stock plugin (e.g. "de-esser" → ReaFIR/ReaXComp preset,
  "eq" → ReaEQ, "compressor" → ReaComp).
- `set_fx_param` — set named/indexed parameter.
- `list_available_fx` — installed plugins (so it can use plugins the user owns).

**Templates (composed workflows)**
- `apply_template` — high-level, e.g. `drum_kit_7mic` builds
  Kick/Snare/HiHat/RackTom/FloorTom/OH-L/OH-R in a DRUMS folder, colored, with a parent buss.
  Templates are data (JSON/Lua) → easy to add; the LLM can also compose primitives ad hoc.

**Meta**
- `undo_point` — name an undo step (panel wraps each tool run in undo anyway).

Design principles: **primitives + templates**; **GUID-based addressing** so references stay
valid as the project changes.

### 4.2 Project Library Management (executor tag: `local` → companion; works with REAPER closed)

**Scan & analyze (read-only):**
- Walk `projects_roots`, index every `.RPP` and referenced media (parse refs from project text).
- Detect: **nested projects** (`.RPP` inside another project's folder); **orphaned media**
  (files in a project folder no `.RPP` references); **regenerable files** (`.reapeaks`,
  `.RPP-UNDO`, old timestamped `.RPP-bak`); **non-self-contained projects** (media referenced
  outside their own folder); **duplicates** (same media by hash across projects).
- Produce a report: space used, space reclaimable, per-issue findings.

**Fix (actioned; strong safety — see §6):**
- **Consolidate/collect** media into a project's own folder (self-contained).
- **Reclaim space** by clearing regenerable caches/old backups.
- **Un-nest** projects into their own top-level folders, fixing references.
- **Quarantine** orphans/dupes (never hard-delete).

**Safety model (decided): Report + quarantine (reversible).** Nothing is ever hard-deleted;
regenerable files, orphans, and dupes are moved to a dated quarantine folder (or OS trash) the
user reviews/empties. Every batch is preceded by a report and explicit confirm. Fully reversible.

## 5. LLM & Agent Layer

**Provider abstraction:** one `LLMProvider` interface — `chat(messages, tools) -> text | tool_calls`,
streaming-capable. Implementations: `AnthropicProvider`, `OpenAIProvider` (cloud, native
tool-calling); `LocalProvider` for Ollama / LM Studio (both OpenAI-compatible → mostly one
adapter). Selectable/switchable mid-session.

**Local-first onboarding (priority):**
- Auto-detect local servers: probe Ollama (`:11434`) and LM Studio (`:1234`) on startup; query
  their model lists; present a dropdown (no manual endpoint typing).
- **Zero-key default:** if a local server is running, ReaMind works with no API keys.
- Friendly setup hint + a recommended tool-capable model when nothing is running.

**Tool-calling strategy (for local-model reliability):** two modes — `native` (cloud + capable
local) and `prompted-JSON` (model emits a parseable JSON tool block). Auto-selected per model,
user-overridable.

**Agent loop (`agent.py`):**
1. Send system prompt + history + tool schemas.
2. Tool calls → route by executor tag (`reaper` → bridge → panel; `local` → in-process) →
   append results → repeat.
3. Text → stream to panel, done.
4. Guardrails: max tool-iterations per turn; timeouts; destructive actions must pass through a
   confirmation tool before executing.

**Tool routing:** tools tagged `reaper` or `local`; LLM sees one unified list; companion routes.

**MCP host (`mcp_host.py`):** connect to MCP servers listed in config, pull their tool
definitions, expose them to the LLM namespaced (e.g. `mymcp__do_thing`). This is how users add
toolsets (e.g. for plugins they own) without touching core code.

**System prompt:** describes REAPER context, tools, conventions (GUID addressing; propose a plan
for multi-step/destructive work), and injects a live project summary each turn.

## 6. Config, Safety & Error Handling

**Config file** (`~/.config/reamind/config.json`; editable in-panel and by hand):
- `provider`: active provider + model; per-provider settings (endpoints, optional keys);
  tool-calling mode override.
- `theme`: colors, font, size, presets.
- `projects_roots`: folders to scan; `quarantine_dir`.
- `mcp_servers`: external MCP servers to load.
- `templates_dir`: user templates.
- `safety`: confirm-before-destructive (default on), max tool-iterations, timeouts.

**Theming (user-configurable, never automatic):** presets (neutral dark/light) + a settings pane
for window/bg, text, accent, and user/assistant bubble colors, font, and size. Applied to the
ImGui style live. Optional "sample REAPER theme colors" button (via `reaper.GetThemeColor`) as a
starting point only.

**Safety model:**
- Every REAPER tool run wrapped in a named **undo block** (one-click undo in REAPER).
- Destructive ops (delete track, project cleanup) require a **confirmation tool** round-trip;
  panel shows a clear confirm first.
- Filesystem cleanup is **quarantine-only**, always report-then-confirm.

**Error handling:**
- Tool errors → `{ok:false, error}` fed back to the LLM (to adjust/explain) and shown in panel.
- Provider/network errors → panel message + retry; timeouts prevent silent hangs.
- Bridge robustness: unique ids + processed-id tracking; stale files cleared on startup;
  companion crash detected by panel via heartbeat file → offer restart.
- Malformed LLM tool args validated against each tool's schema before execution; invalid →
  error back to the model to retry.

## 7. Testing Strategy

**Companion (Python) — bulk of logic:**
- **Unit** (pytest): `.RPP` parser; library scanner (nested/orphan/dupe/regenerable detection on
  fixture trees); quarantine (dry-run + reversibility); config load/validate; tool-schema
  validation; provider abstraction.
- **Agent loop:** a **fake LLM provider** returning scripted tool calls → assert routing,
  iteration limits, confirmation gating. No network.
- **Bridge:** write requests, simulate panel read/write → assert id/ordering/no-double-exec.
- **Library management:** fixture directory trees (tiny fake projects + media) in temp dirs.

**Panel (Lua) — keep thin:**
- Pure helpers (JSON IPC parsing, theme mapping, arg coercion) extracted into modules testable
  with a plain Lua interpreter (busted) outside REAPER.
- REAPER-touching tools verified via a manual smoke checklist + a `selftest` action that runs
  each tool against a scratch project and reports pass/fail in the panel.

**End-to-end:** scripted scenario ("build a 7-mic drum kit, sidechain kick→OH") driven by the
fake provider through the bridge against a live REAPER — release smoke test.

**Principle:** all real logic in the Python companion where it's cleanly testable; Lua panel is a
thin, mostly-declarative executor.

## 8. Suggested Build Phasing

1. Bridge + panel skeleton + companion skeleton (echo round-trip).
2. Local provider + agent loop + read-only tools (project awareness).
3. Track/folder/routing/FX tools + templates.
4. Theming + settings + local-model onboarding.
5. Project Library Management (scan → report → quarantine).
6. MCP host + cloud providers.

## 9. Dependencies & Prerequisites

- REAPER with **ReaImGui** (via ReaPack) for the panel GUI. (User already has ReaPack + SWS.)
- Python 3.11+ for the companion; audio libs deferred to the end-game phase
  (`numpy`, `soundfile`, `librosa`, `pyloudnorm`).
- Optional: a local model server (Ollama or LM Studio — user already has both) and/or cloud API
  keys.

## 10. Out of Scope (v1)

- Audio DSP analysis (WAV peaks/RMS/LUFS, transient detection, quantize/align) — end-game phase.
- AI-generated DSP effects (JSFX) — separate future subsystem.
- Cross-DAW support.
