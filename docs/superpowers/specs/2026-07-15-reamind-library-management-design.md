# ReaMind — Project Library Management Design Spec

**Date:** 2026-07-15
**Status:** Draft — pending review
**Phase:** 5 of 6 (per root spec §8)

## 1. Overview

Phase 5 adds project-library management to ReaMind: scan REAPER project
directories, detect issues (nested projects, orphaned media, duplicates,
regenerable files, non-self-contained projects), and act on them through
quarantine (reversible) and reclaim (regenerable-only deletion). Runs entirely
in the Python companion (executor tag `local`) — no Lua changes needed.

### Guiding principles
- **Safety-first**: nothing is ever hard-deleted except truly regenerable files
  (`.reapeaks`, `.RPP-UNDO`, `.RPP-bak`); everything else moves to a dated
  quarantine folder.
- **Report-then-confirm**: every action is preceded by a scan report; destructive
  actions use the existing confirmation-gating mechanism.
- **Stdlib-only**: no new dependencies. RPP parsing, file walking, hashing — all
  standard library.

## 2. Architecture

```
companion/reamind/
  rpp.py              # .RPP parser (media/extract source references)
  library/
    __init__.py
    scanner.py         # walk project roots, detect issues, produce reports
    quarantine.py      # reversible move-to-dated-folder, reclaim regenerable files
  local_tools.py       # (modified) — register library tool executor
```

**No Lua changes.** All library tools are `local` executor — the companion runs
them in-process. The panel has no project-library awareness.

### Data flow
```
LLM → "scan my projects" → local executor → scanner.walk() → findings dict
    → LLM → "quarantine orphans in /path" → confirmation round-trip
    → local executor → quarantine.move(files) → result
```

### Config additions
```json
{
  "projects_roots": ["/home/user/REAPER Projects"],
  "quarantine_dir": "~/.config/reamind/quarantine"
}
```

## 3. RPP Parser (`rpp.py`)

### Format

REAPER project files are plain text with a chunk-based structure:

```
<CHUNKCHUNKNAME
  KEY VALUE
  <SUBCHUNK
    ...
  >
>
```

Media references appear in `<SOURCE` subsections inside item chunks.
Subprojects appear as `<SOURCE RPP` referencing another `.RPP` file.

### Interface

- `extract_sources(rpp_path: Path) -> list[dict]` — parse one `.RPP`, return
  list of source references with fields:
  - `type`: `"WAVE" | "MIDI" | "RPP" | "VIDEO"`
  - `path`: resolved absolute path (relative paths made absolute against the RPP's
    directory)
  - `line`: line number in the RPP file (for diagnostics)
- `parse_chunks(text: str) -> list[dict]` — low-level: tokenize chunk structure
  into `{name, content, children}`.

### Detection capabilities

- **Subprojects**: `<SOURCE RPP path=...>` references that point to other `.RPP`
  files within the same project root.
- **External media**: `SOURCE WAVE path=...` pointing outside the project's own
  directory.
- **All referenced files**: complete set of media files an `.RPP` depends on.

## 4. Scanner (`library/scanner.py`)

Walks `projects_roots` from config, aggregates per-project and cross-project
findings.

### Interface

- `scan_root(root: Path) -> ScanResult` — scan one project root directory,
  return a `ScanResult` dataclass.
- `ScanResult` fields:
  - `root: Path`
  - `projects: list[ProjectInfo]` — one per `.RPP` found
  - `findings: list[Finding]`
  - `summary: dict` — `{project_count, media_count, total_size_bytes, orphaned_count, regenerable_count, duplicate_count, nested_count, external_count, missing_count}`
- `ProjectInfo` fields:
  - `path: Path` — absolute .RPP path
  - `source_count: int` — number of source references found
  - `sources: list[dict]` — raw source references from rpp.extract_sources()
- `Finding` fields:
  - `type: str` — one of the six detection types
  - `path: Path` — file or directory this finding is about
  - `reason: str` — human-readable explanation
  - `size_bytes: int`
  - `related: list[Path] | None` — for duplicates: other copies; for external: the .RPP referencing it

### Detection types

Each `Finding` has `{type, path, reason, size_bytes, related}`:

| Type | Detection |
|------|-----------|
| `nested_project` | `.RPP` inside another `.RPP`'s project directory |
| `orphaned_media` | media file in a project folder not referenced by any `.RPP` |
| `regenerable` | `.reapeaks`, `.RPP-UNDO`, `*.RPP-bak` files |
| `external_media` | media referenced by an `.RPP` but outside its own directory |
| `duplicate` | same file hash in two or more locations within scanned roots |
| `missing_media` | source reference resolves to a path that doesn't exist on disk |

### Duplicate detection

Two-pass algorithm:
1. Group all media files by byte size. Skip groups of size 1.
2. For groups of 2+, hash first 64KB of each file. If still ambiguous, hash
   the full file.
3. Report hash-colliding groups.

Uses `hashlib.sha256` (stdlib).

## 5. Quarantine & Actions (`library/quarantine.py`)

### Safety model

- **Quarantine** (orphans, duplicates, subprojects): moves files to
  `quarantine_dir/YYYY-MM-DD/` preserving relative directory structure. Fully
  reversible — user moves files back manually.
- **Reclaim** (regenerable files): hard-deletes `.reapeaks`, `.RPP-UNDO`,
  `*.RPP-bak`. No quarantine needed — these are truly regenerable by REAPER on
  next project open.
- **Consolidate**: copies external media into the project directory. Does NOT
  modify the `.RPP` file — the `.RPP` still references the old absolute paths.
  The user must open the project in REAPER and use "File → Save project as..."
  with "Copy all media into project directory" checked for the change to take
  effect. This is a v1 limitation; future versions may edit RPP chunk
  references directly. The tool response includes this guidance.
- **Un-nest**: copies a nested `.RPP` to a sibling directory under
  `projects_root`, leaves the original in place (manual removal by user).

### Interface

- `quarantine_files(paths: list[Path], quarantine_base: Path) -> dict` — move
  files to `quarantine_base/YYYY-MM-DD/`. Returns `{moved_count, quarantine_path}`.
- `reclaim_regenerable(files: list[Path]) -> dict` — delete regenerable files.
  Returns `{deleted_count, bytes_freed}`.
- `consolidate_project(project_path: Path) -> dict` — copy external media
  references into project directory. Returns `{moved_count, dest_dir}`.
- `unnest_project(rpp_path: Path, projects_root: Path) -> dict` — move nested
  `.RPP` to a new top-level directory. Returns `{new_path}`.

All quarantine operations use `shutil.move` (atomic on same filesystem) and
preserve relative paths so the user can restore by moving back from the dated
folder.

## 6. Tool Specs (local executor)

All tools use executor tag `"local"`. Destructive tools set `destructive=True`
and `return_confirmation=True` to use the existing confirmation gating.

### Read-only

| Tool | Args | Returns |
|------|------|---------|
| `scan_root` | `path: str` | `{root, project_count, media_count, finding_counts}` |
| `list_findings` | `root: str, type: str?` | `[{type, path, reason, size_bytes}]` |
| `get_file_details` | `path: str` | `{size, modified, hash, referenced_by, is_orphan}` |
| `list_quarantine_batches` | (none) | `[{date, file_count, total_bytes}]` |

### Destructive (confirmation-gated)

| Tool | Args | Returns |
|------|------|---------|
| `quarantine_files` | `paths: [str]` | `{moved_count, quarantine_path}` |
| `reclaim_space` | `type: str?` | `{deleted_count, bytes_freed}` |
| `consolidate_project` | `project_path: str` | `{moved_count, dest_dir}` |
| `unnest_project` | `project_path: str` | `{new_path}` |

### Utility

| Tool | Args | Returns |
|------|------|---------|
| `set_projects_root` | `path: str` | `{ok, message}` |

## 7. Integration into Local Tools

`local_tools.py` gains a new `build_library_executor()` function (parallel
to the existing `build_local_executor()`) that routes library tool names.

The library executor is built in `Server.__init__` and merged into the
combined executor chain (alongside the existing local executor).

## 8. Confirmation Gating

All destructive library tools use the same pattern as construction tools:
- `destructive=True` on `ToolSpec`
- `return_confirmation=True` triggers the `confirm_required` response
- LLM must re-issue the call with `confirm_ok: true`
- `_execute_call` in `agent.py` handles this — no changes needed

## 9. Testing Strategy

### Unit — Python (pytest)

- **RPP parser** (`tests/test_rpp.py`): fixture `.RPP` snippets with WAVE,
  MIDI, RPP (subproject), and VIDEO sources. Test path resolution (relative
  → absolute), missing files, empty projects, nested subchunks.
- **Scanner** (`tests/test_scanner.py`): temp directories with fake project
  trees. Test each detection type: nested, orphaned, regenerable, external,
  duplicate (via identical content files), missing media.
- **Quarantine** (`tests/test_quarantine.py`): temp directories, verify files
  move to correct `YYYY-MM-DD/rel/path` under quarantine dir. Verify nothing
  is hard-deleted (quarantine only moves). Verify `reclaim_regenerable` only
  deletes `.reapeaks`/`.RPP-UNDO`/`*.RPP-bak` patterns.
- **Duplicate detection**: identical files in different directories, non-duplicates
  (different content same name), size-only collisions (different content same
  size), large files streaming.

### Integration — Python (pytest)

- End-to-end scan → report → quarantine cycle in a temp project tree.
  Assert findings list before and after quarantine.

### No Lua changes

Library management runs entirely in the companion. No Lua tests needed.

## 10. Design Decisions

| Decision | Rationale |
|----------|-----------|
| Full chunk parser (not regex) | Handles subprojects, per-track media, frozen tracks correctly |
| Two-pass duplicate detection (size → hash) | Fast for large libraries; hash only candidates |
| Dated quarantine folders | Fully reversible, stdlib-only, no new dependencies |
| Consolidate copies files, not modifies .RPP | Safe; REAPER's own "Copy media to project" is the authoritative path |
| Hard-delete regenerable files | Truly regenerable; quarantining `.reapeaks` would just waste space |
| No Lua changes | Library management has no UI surface — chat-driven only |

## 11. Self-Review

- **RPP parser**: covers WAVE, MIDI, RPP (subproject), VIDEO sources. Handles
  relative path resolution. Nested chunks supported.
- **Scanner**: all 6 detection types covered. Duplicate detection uses two-pass
  size→hash. Scan results are dataclasses with summary fields.
- **Quarantine**: moves to dated folder preserving structure. Reclaim targets
  specific file patterns. Never hard-deletes non-regenerable files.
- **Tools**: 9 tool specs (4 read-only, 4 destructive, 1 utility). Confirmation
  gating reuses existing mechanism.
- **Testing**: all components testable with temp directories and fixture RPP
  content. No new dependencies.
- **Scope**: focused on library management. No RPP modification, no audio DSP.
  Matches spec §8 phase 5.
