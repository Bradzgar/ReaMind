# ReaMind Construction Tools — Design Spec

**Date:** 2026-07-15
**Status:** Approved design; ready for implementation planning
**Parent spec:** [ReaMind Design](2026-07-14-reamind-design.md) §4.1

## 1. Overview

Phase 2 adds 12 REAPER construction tools to ReaMind: track/folder creation, sends/routing/sidechain, stock FX insertion with parameter control, and a template system for composed workflows, plus destructive-operation confirmation gating.

All tools follow the existing read-only tool pattern: Python `ToolSpec` definitions, Lua implementations with the same `(ok, result_or_error)` return convention, `reaper` executor tag, undo-wrapped execution in the panel.

## 2. Architecture

New files:

```
companion/reamind/tools/
  reaper_construction.py    # ToolSpec defs for all 12 tools
  fx_map.py                 # friendly-name → FX identifier, built from panel scan
panel/tools/
  construction.lua          # Lua implementations of all construction tools
  fx_scanner.lua            # enumerate installed FX into fx_map
templates/                  # user-expandable JSON template library
  drum_kit_7mic.json        # first template
```

The panel loads `tools.construction` at startup alongside `tools.readonly`. All tool specs from all loaded modules are merged into a single dispatch table. Adding a future tool requires only: (1) a `ToolSpec` in a Python file + registry registration, (2) a Lua function in a panel tools module + entry in its `tool_specs` table. No plumbing changes.

```
 ┌─────────────┐     ToolSpec (reaper)     ┌──────────────┐
 │  companion   │ ──────────────────────▶ │  Lua panel    │
 │  agent.py    │                          │  poll_requests│
 │              │ ◀──────────────────────  │               │
 │  _execute_   │     result JSON          │  run_tool()   │
 │  _call()     │                          │  ┌───────────┐│
 └─────────────┘                          │  │construction││
                                          │  │.lua        ││
                                          │  └───────────┘│
                                          └──────────────┘
```

## 3. Tool Schemas

### 3.1 Track & Folder Construction

| Tool | executor | Params | Returns |
|------|----------|--------|---------|
| `create_track` | reaper | `name` (str), `color` (int, optional), `position` (int, optional, -1=last), `parent_guid` (str, optional) | `{track_guid, index}` |
| `create_folder` | reaper | `name` (str), `child_guids` (list of str, tracks to move into folder) | `{folder_guid, child_count}` |
| `set_track_props` | reaper | `track_guid` (str, required), `name` (str, optional), `color` (int, optional), `volume_db` (float, optional), `pan` (float, optional, -1..1), `record_arm` (bool, optional), `input` (str, optional) | `{track_guid}` |
| `delete_track` | reaper | `track_guid` (str) | `{track_guid}` |
| | | **destructive: true** | confirmation-gated |

### 3.2 Routing

| Tool | executor | Params | Returns |
|------|----------|--------|---------|
| `add_send` | reaper | `src_guid` (str), `dst_guid` (str), `gain_db` (float, optional, default 0), `is_pre_fader` (bool, optional, default false) | `{src_guid, dst_guid, send_index}` |
| `add_receive` | reaper | `src_guid` (str), `dst_guid` (str), `gain_db` (float, optional, default 0) | `{src_guid, dst_guid, receive_index}` |
| `create_sidechain` | reaper | `source_guid` (str), `target_guid` (str), `target_fx_index` (int, optional, default -1=last) | `{source_guid, target_guid, channels: "3/4"}` |

### 3.3 Stock FX

| Tool | executor | Params | Returns |
|------|----------|--------|---------|
| `insert_fx` | reaper | `track_guid` (str), `fx_name` (str — friendly name resolved by fx_map), `position` (int, optional, default -1=last) | `{track_guid, fx_index}` |
| `set_fx_param` | reaper | `track_guid` (str), `fx_index` (int), `param` (str or int — name or index), `value` (float) | `{track_guid, fx_index, param}` |
| `list_available_fx` | local | (none) | `{fx_list: [{name, identifier}, ...]}` |

### 3.4 Templates + Meta

| Tool | executor | Params | Returns |
|------|----------|--------|---------|
| `apply_template` | mixed | `template_name` (str) | `{template_name, steps: [...], steps_completed: int}` |
| `undo_point` | reaper | `name` (str) | `{name}` |

`apply_template` is a **mixed executor**: the companion reads the template JSON, sends each primitive step to the panel as individual tool invocations. The companion orchestrates the sequence; the panel never loads templates directly.

A template is a JSON array of tool invocations:

```json
[
  {"tool": "create_folder", "args": {"name": "DRUMS"}},
  {"tool": "create_track", "args": {"name": "Kick", "parent_guid": "<FOLDER_GUID>"}},
  ...
]
```

GUID references between steps are resolved by the companion (e.g. `"<FOLDER_GUID>"` becomes the GUID from step 1's result).

`undo_point` is a no-op convenience — the panel already wraps every tool execution in `Undo_BeginBlock`/`Undo_EndBlock`. This tool exists so the LLM can name undo steps explicitly without the panel needing to interpret the name (it is informational only in v1).

## 4. FX Mapping

`companion/reamind/tools/fx_map.py` defines a static mapping of friendly names to REAPER internal FX identifiers. On startup, the companion calls `list_available_fx` (a local tool) which the panel resolves via `fx_scanner.lua` — enumerating all installed FX. The companion merges this scanned list into the static map for entries the user's system has.

Static map covers stock REAPER plugins:

```
eq          → "ReaEQ (Cockos)"
compressor  → "ReaComp (Cockos)"
gate        → "ReaGate (Cockos)"
de_esser    → "ReaXComp (Cockos)" with de-esser preset
reverb      → "ReaVerb (Cockos)"
delay       → "ReaDelay (Cockos)"
pitch       → "ReaPitch (Cockos)"
tuner       → "ReaTune (Cockos)"
synth       → "ReaSynth (Cockos)"
sampler     → "ReaSamplOmatic5000 (Cockos)"
```

The `insert_fx` Lua tool receives either a friendly name (resolved by companion before dispatch, passed as the REAPER identifier string) or a raw identifier from the scanned list. The companion resolves the name, sends the actual identifier to the panel.

`list_available_fx` is tagged `local` (executor `local`) because the companion calls it once at startup to seed the mapping. The panel implements it as `fx_scanner.lua` and exposes it via the same tool dispatch path — but since it's tagged `local`, the companion's in-process local executor runs it by calling through the bridge just like a reaper tool. **Correction:** `list_available_fx` is tagged `reaper` (it needs REAPER's plugin enumeration API). The companion's local executor does not run `reaper` tools — those always go through the bridge. For convenience, the companion calls `list_available_fx` once at startup via the bridge during initialization, caches the result, and uses it to augment `fx_map.py`'s static entries.

## 5. Confirmation Gating

`delete_track` is the only destructive tool in this phase. `ToolSpec` gains an optional field:

```python
@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict
    executor: str
    destructive: bool = False      # NEW
    return_confirmation: bool = False  # NEW — tool needs user OK
```

**Flow for destructive tools:**

1. Agent calls `delete_track` → `_execute_call` sees `spec.destructive == True`
2. If `config.safety.confirm_destructive` is enabled, companion emits a `confirm_action` message:
   ```json
   {"ok": false, "confirm_required": true, "tool": "delete_track", "args": {...}, "message": "Delete track 'Kick'? Reply 'yes' to confirm."}
   ```
3. This result goes to the LLM as a tool response. The LLM is expected to ask the user for confirmation. The panel does NOT show a dialog — confirmation flows through the chat conversation.
4. When the LLM re-calls `delete_track`, the companion checks that a `confirm_ok` field is present in the arguments. If present and truthful, the tool executes. If absent, the confirm loop repeats.
5. The companion tracks pending confirmations per call ID to prevent replay.

The `Undo_BeginBlock`/`Undo_EndBlock` wrapping in the panel provides an additional safety net — every destructive operation is undoable via REAPER's built-in undo.

## 6. Testing

- **Python unit tests:** `test_reaper_construction.py` — verifies all 12 ToolSpecs have correct schemas, required fields, executor tags, and destructive flags. Verifies template JSON is valid and parsable.
- **Lua unit tests:** `panel/test/construction_spec.lua` — tests all pure-logic helpers (GUID string validation, color clamping, gain dB conversion) using standalone `lua` and the existing `test.run` runner.
- **FX map tests:** `test_fx_map.py` — verifies static map entries are well-formed, that friendly-name lookup works, and that scanning/merge logic is correct.
- **Confirmation tests:** `test_agent.py` additions — verifies that destructive tools trigger the confirm loop, that confirmed tools execute, and that unconfirmed tools are rejected.
- **REAPER-integration tools** (`create_track`, `insert_fx`, etc.) are not unit-testable — they call `reaper.*` APIs. Covered by smoke test manual steps.
- **End-to-end:** scripted scenario "build a 7-mic drum kit, add a compressor to the buss" using a fake provider → verifies full agent loop through tool execution.

## 7. Future Expansion

Adding a new tool requires no plumbing changes:

1. Add a `ToolSpec(...)` entry in the appropriate Python file + `reg.register(spec)`
2. Add a Lua function in a panel tools module + entry in its `tool_specs` table
3. That's it — the agent loop and panel dispatch discover it automatically

Adding a new template: drop a `.json` file in `templates/`. No code changes.

Adding a new FX friendly name: add one line to `fx_map.py`'s static dict. Scanned user FX are discovered automatically on startup.

## 8. Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| FX map location | Python (`fx_map.py`) | LLM can reference friendly names; REAPER identifiers are opaque |
| Template storage | Shared JSON (`templates/`) | LLM sees content for reasoning; users can add templates without code |
| Confirmation method | Confirmation tool via LLM | LLM-aware; single confirmation mechanism for all future destructive tools |
| Panel dispatch pattern | Same as readonly tools | No new bridge protocol; tools are data, not new architecture |
| FX scanning | Startup-only bridge call | Plugin list doesn't change during session; cache once |

## 9. Self-Review

- **Placeholder scan:** No TBDs, TODOs, or incomplete sections.
- **Internal consistency:** All 12 tools use the same executor tag, return format, and dispatch path. Template orchestration is companion-side. FX map is companion-side with bridge-based initial scan.
- **Scope:** Focused on §4.1 construction tools. Library management (§4.2) is a separate phase. No scope creep.
- **Ambiguity:** `list_available_fx` executor tag resolved: it's `reaper` (needs REAPER API), called via bridge at startup. Confirmation flow specified completely — confirm result → LLM re-calls → execute.
