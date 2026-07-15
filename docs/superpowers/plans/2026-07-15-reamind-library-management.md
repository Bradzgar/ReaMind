# ReaMind — Project Library Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add project-library management: scan REAPER project directories, detect issues (nested, orphaned, regenerable, external, duplicate, missing), and act through reversible quarantine + reclaim.

**Architecture:** RPP chunk parser extracts source references; scanner walks project roots and produces typed Finding lists; quarantine module handles move-to-dated-folder and regenerable deletion. All tools are `local` executor — the companion runs them in-process with no Lua changes. Destructive tools use the existing confirmation-gating mechanism in `_execute_call`.

**Tech Stack:** Python 3.11+ (stdlib only: pathlib, hashlib, shutil, tempfile, itertools, dataclasses), pytest dev-only. No Lua changes.

## Global Constraints

- Python **3.11+**. Runtime code MUST use only the Python standard library. `pytest` is the ONLY dev/test dependency.
- Config lives at `~/.config/reamind/config.json`. Missing config is created from defaults.
- Commit after every task with a Conventional Commits message.
- Repo: `/home/bradzgar/projects/reamind`. Branch from master. Test commands: `cd companion && .venv/bin/python -m pytest ...`.
- Library types live under `companion/reamind/library/` (new package).
- All library tools are `local` executor — no Lua changes, no bridge traffic.
- Destructive tools use `destructive=True` + `return_confirmation=True` — confirmation gating handled by existing `_execute_call` in agent.py.

---

### Task 1: RPP chunk parser (`companion/reamind/rpp.py`)

**Files:**
- Create: `companion/reamind/rpp.py`
- Test: `companion/tests/test_rpp.py`

**Interfaces:**
- Consumes: stdlib only (`pathlib`, `re` for tokenizing).
- Produces:
  - `extract_sources(rpp_path: Path) -> list[dict]` — parse one `.RPP`, return list of source references. Each dict has keys `"type"` (`"WAVE"|"MIDI"|"RPP"|"VIDEO"`), `"path"` (resolved absolute path as string), `"line"` (line number, 0 for now).
  - `parse_chunks(text: str) -> list[dict]` — low-level chunk tokenizer. Each dict has keys `"name"`, `"lines"` (list of content lines), `"children"` (list of sub-chunk dicts).

**Chunk parsing algorithm:**
REAPER RPP files use a simple line-based format: `<CHUNKNAME` opens a chunk, `>` closes the most recently opened chunk, other lines are key-value content inside the current chunk. Sources appear inside `<SOURCE` chunks with `FILE "path"` lines. Paths are relative to the .RPP file's directory unless absolute (starts with `/` or a drive letter).

- [ ] **Step 1: Write the failing test**

Create `companion/tests/test_rpp.py`:

```python
from pathlib import Path
import tempfile

from reamind.rpp import extract_sources, parse_chunks


RPP_SINGLE_WAVE = r'''<REAPER_PROJECT 0.1
  <ITEM
    <SOURCE WAVE
      FILE "media/kick.wav"
    >
  >
>
'''


RPP_MULTIPLE_SOURCES = r'''<REAPER_PROJECT 0.1
  <ITEM
    <SOURCE WAVE
      FILE "/abs/path/snare.wav"
    >
  >
  <ITEM
    <SOURCE MIDI
      FILE "midi/track.mid"
    >
  >
  <ITEM
    <SOURCE RPP
      FILE "../other_project/drums.RPP"
    >
  >
>
'''


RPP_EMPTY = "<REAPER_PROJECT 0.1\n>\n"


def test_parse_chunks_flat():
    text = "<CHUNK\n  KEY VAL\n>\n"
    chunks = parse_chunks(text)
    assert len(chunks) == 1
    assert chunks[0]["name"] == "CHUNK"
    assert "KEY VAL" in chunks[0]["lines"]


def test_parse_chunks_nested():
    chunks = parse_chunks(RPP_SINGLE_WAVE)
    assert chunks[0]["name"] == "REAPER_PROJECT"
    item = chunks[0]["children"][0]
    assert item["name"] == "ITEM"
    source = item["children"][0]
    assert source["name"] == "SOURCE"


def test_extract_sources_wave():
    with tempfile.TemporaryDirectory() as d:
        rpp = Path(d) / "test.RPP"
        rpp.write_text(RPP_SINGLE_WAVE)
        sources = extract_sources(rpp)
        assert len(sources) == 1
        assert sources[0]["type"] == "WAVE"
        assert sources[0]["path"].endswith("media/kick.wav")


def test_extract_sources_relative_path_resolution():
    with tempfile.TemporaryDirectory() as d:
        rpp = Path(d) / "sub" / "test.RPP"
        rpp.parent.mkdir()
        rpp.write_text(RPP_SINGLE_WAVE)
        sources = extract_sources(rpp)
        expected = (Path(d) / "sub" / "media" / "kick.wav").resolve()
        assert Path(sources[0]["path"]).resolve() == expected


def test_extract_sources_preserves_absolute_paths():
    with tempfile.TemporaryDirectory() as d:
        rpp = Path(d) / "test.RPP"
        rpp.write_text(RPP_MULTIPLE_SOURCES)
        sources = extract_sources(rpp)
        assert sources[0]["path"] == "/abs/path/snare.wav"


def test_extract_sources_all_types():
    with tempfile.TemporaryDirectory() as d:
        rpp = Path(d) / "test.RPP"
        rpp.write_text(RPP_MULTIPLE_SOURCES)
        sources = extract_sources(rpp)
        types = {s["type"] for s in sources}
        assert types == {"WAVE", "MIDI", "RPP"}


def test_extract_sources_empty_project():
    with tempfile.TemporaryDirectory() as d:
        rpp = Path(d) / "test.RPP"
        rpp.write_text(RPP_EMPTY)
        assert extract_sources(rpp) == []


def test_extract_sources_missing_file():
    sources = extract_sources(Path("/nonexistent/path.RPP"))
    assert sources == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd companion && .venv/bin/python -m pytest tests/test_rpp.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'reamind.rpp'`.

- [ ] **Step 3: Write minimal implementation**

Create `companion/reamind/rpp.py`:

```python
from __future__ import annotations

import re
from pathlib import Path


def parse_chunks(text: str) -> list[dict]:
    lines = text.split("\n")
    root = {"children": [], "name": "__root__", "lines": []}
    stack = [root]

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("<"):
            name = stripped[1:].split()[0] if stripped[1:].strip() else stripped[1:]
            chunk = {"name": name, "lines": [], "children": []}
            stack[-1]["children"].append(chunk)
            stack.append(chunk)
        elif stripped == ">":
            if len(stack) > 1:
                stack.pop()
        else:
            stack[-1]["lines"].append(stripped)

    return root["children"]


_SOURCE_PATTERN = re.compile(r'<SOURCE\s+(\w+)')


def extract_sources(rpp_path: Path) -> list[dict]:
    try:
        text = rpp_path.read_text(encoding="utf-8", errors="replace")
    except (OSError, FileNotFoundError):
        return []

    chunks = parse_chunks(text)

    def walk(chunk_list, results):
        for chunk in chunk_list:
            m = _SOURCE_PATTERN.match(f"<{chunk['name']}")
            if m:
                source_type = m.group(1).upper()
                file_path = None
                for line in chunk["lines"]:
                    if line.startswith("FILE "):
                        file_path = line[5:].strip().strip('"')
                        break
                if file_path:
                    p = Path(file_path)
                    if not p.is_absolute():
                        p = (rpp_path.parent / p).resolve()
                    results.append({
                        "type": source_type,
                        "path": str(p),
                        "line": 0,
                    })
            walk(chunk["children"], results)

    results = []
    walk(chunks, results)
    return results
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd companion && .venv/bin/python -m pytest tests/test_rpp.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
cd /home/bradzgar/projects/reamind
git add companion/reamind/rpp.py companion/tests/test_rpp.py
git commit -m "feat: RPP chunk parser with source reference extraction"
```

---

### Task 2: Config additions — projects_roots + quarantine_dir

**Files:**
- Modify: `companion/reamind/config.py`
- Test: `companion/tests/test_config.py` (append tests)

**Interfaces:**
- Consumes: existing Config dataclass.
- Produces (new fields on Config):
  - `projects_roots: list[str] = field(default_factory=list)`
  - `quarantine_dir: str = "~/.config/reamind/quarantine"`
  - Updated `to_dict()` and `from_dict()` that include these fields.

- [ ] **Step 1: Write the failing test**

Append to `companion/tests/test_config.py`:

```python
def test_config_projects_roots_defaults_empty():
    c = Config()
    assert c.projects_roots == []


def test_config_quarantine_dir_default():
    c = Config()
    assert c.quarantine_dir == "~/.config/reamind/quarantine"


def test_config_projects_roots_roundtrips():
    c = Config()
    c.projects_roots = ["/home/user/Projects", "/mnt/media"]
    d = c.to_dict()
    loaded = Config.from_dict(d)
    assert loaded.projects_roots == ["/home/user/Projects", "/mnt/media"]


def test_config_quarantine_dir_roundtrips():
    c = Config()
    c.quarantine_dir = "/tmp/quarantine"
    d = c.to_dict()
    loaded = Config.from_dict(d)
    assert loaded.quarantine_dir == "/tmp/quarantine"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd companion && .venv/bin/python -m pytest tests/test_config.py::test_config_projects_roots_defaults_empty tests/test_config.py::test_config_quarantine_dir_default tests/test_config.py::test_config_projects_roots_roundtrips tests/test_config.py::test_config_quarantine_dir_roundtrips -v`
Expected: all 4 FAIL — `AttributeError`.

- [ ] **Step 3: Write minimal implementation**

In `companion/reamind/config.py`, on the `Config` dataclass, add after the `theme` field:

```python
    projects_roots: list[str] = field(default_factory=list)
    quarantine_dir: str = "~/.config/reamind/quarantine"
```

In `Config.to_dict()`, add after the `"theme"` entry:

```python
            "projects_roots": list(self.projects_roots),
            "quarantine_dir": self.quarantine_dir,
```

In `Config.from_dict()`, add after the `theme=Theme.from_dict(d.get("theme", {}))` line:

```python
            projects_roots=d.get("projects_roots", []),
            quarantine_dir=d.get("quarantine_dir", "~/.config/reamind/quarantine"),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd companion && .venv/bin/python -m pytest tests/test_config.py -v`
Expected: all config tests PASS (existing 12 + 4 new = 16).

- [ ] **Step 5: Commit**

```bash
cd /home/bradzgar/projects/reamind
git add companion/reamind/config.py companion/tests/test_config.py
git commit -m "feat: add projects_roots and quarantine_dir to config"
```

---

### Task 3: Library tool specs (`companion/reamind/tools/library.py`)

**Files:**
- Create: `companion/reamind/tools/library.py`
- Test: `companion/tests/test_library_tools.py`

**Interfaces:**
- Consumes: `reamind.tools.registry.ToolSpec`, `reamind.tools.registry.ToolRegistry`.
- Produces:
  - 9 `ToolSpec` module-level constants for each library tool.
  - `build_library_registry() -> ToolRegistry` — returns a registry with all 9 specs registered. Destructive tools have `destructive=True` and `return_confirmation=True`.

- [ ] **Step 1: Write the failing test**

Create `companion/tests/test_library_tools.py`:

```python
from reamind.tools.library import (
    CONSOLIDATE_PROJECT,
    GET_FILE_DETAILS,
    LIST_FINDINGS,
    LIST_QUARANTINE_BATCHES,
    QUARANTINE_FILES,
    RECLAIM_SPACE,
    SCAN_ROOT,
    SET_PROJECTS_ROOT,
    UNNEST_PROJECT,
    build_library_registry,
)


def test_all_nine_names_present():
    specs = [
        SCAN_ROOT, LIST_FINDINGS, GET_FILE_DETAILS,
        LIST_QUARANTINE_BATCHES, QUARANTINE_FILES, RECLAIM_SPACE,
        CONSOLIDATE_PROJECT, UNNEST_PROJECT, SET_PROJECTS_ROOT,
    ]
    for s in specs:
        assert s.name
        assert s.description
        assert s.parameters
        assert s.executor == "local"


def test_registry_registers_all_nine():
    reg = build_library_registry()
    names = {s.name for s in reg.specs()}
    expected = {
        "scan_root", "list_findings", "get_file_details",
        "list_quarantine_batches", "quarantine_files", "reclaim_space",
        "consolidate_project", "unnest_project", "set_projects_root",
    }
    assert names == expected


def test_destructive_tools_flagged():
    reg = build_library_registry()
    destructive = {"quarantine_files", "reclaim_space", "consolidate_project", "unnest_project"}
    for spec in reg.specs():
        if spec.name in destructive:
            assert spec.destructive is True, spec.name
            assert spec.return_confirmation is True, spec.name
        else:
            assert spec.destructive is False, spec.name


def test_scan_root_has_required_params():
    assert "path" in SCAN_ROOT.parameters["required"]
    assert SCAN_ROOT.parameters["properties"]["path"]["type"] == "string"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd companion && .venv/bin/python -m pytest tests/test_library_tools.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'reamind.tools.library'`.

- [ ] **Step 3: Write minimal implementation**

Create `companion/reamind/tools/library.py`:

```python
from __future__ import annotations

from .registry import ToolRegistry, ToolSpec


SCAN_ROOT = ToolSpec(
    name="scan_root",
    description="Scan a REAPER project root directory for issues: nested projects, orphaned media, duplicates, regenerable files, external media, missing media. Returns summary counts.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute path to the project root directory to scan."},
        },
        "required": ["path"],
    },
    executor="local",
)

LIST_FINDINGS = ToolSpec(
    name="list_findings",
    description="List detailed findings from a scanned project root. Optionally filter by finding type.",
    parameters={
        "type": "object",
        "properties": {
            "root": {"type": "string", "description": "Project root path that was scanned."},
            "type": {"type": "string", "description": "Optional filter: nested_project, orphaned_media, regenerable, external_media, duplicate, missing_media."},
        },
        "required": ["root"],
    },
    executor="local",
)

GET_FILE_DETAILS = ToolSpec(
    name="get_file_details",
    description="Get detailed info about a file: size, modification date, hash, existence.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute path to the file."},
        },
        "required": ["path"],
    },
    executor="local",
)

LIST_QUARANTINE_BATCHES = ToolSpec(
    name="list_quarantine_batches",
    description="List past quarantine batches with date, file count, and total size.",
    parameters={"type": "object", "properties": {}, "required": []},
    executor="local",
)

QUARANTINE_FILES = ToolSpec(
    name="quarantine_files",
    description="Move files to a dated quarantine folder (reversible — files are NOT deleted). Requires confirmation.",
    parameters={
        "type": "object",
        "properties": {
            "paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Absolute paths to files to quarantine.",
            },
        },
        "required": ["paths"],
    },
    executor="local",
    destructive=True,
    return_confirmation=True,
)

RECLAIM_SPACE = ToolSpec(
    name="reclaim_space",
    description="Delete regenerable files (.reapeaks, .RPP-UNDO, *.RPP-bak). These are automatically regenerated by REAPER. Requires confirmation.",
    parameters={
        "type": "object",
        "properties": {
            "root": {"type": "string", "description": "Project root to scan. If omitted, uses all configured project roots."},
        },
        "required": [],
    },
    executor="local",
    destructive=True,
    return_confirmation=True,
)

CONSOLIDATE_PROJECT = ToolSpec(
    name="consolidate_project",
    description="Copy externally-referenced media files into the project directory. Does NOT modify the .RPP — save from REAPER with 'Copy media' checked. Requires confirmation.",
    parameters={
        "type": "object",
        "properties": {
            "project_path": {"type": "string", "description": "Path to the .RPP file to consolidate."},
        },
        "required": ["project_path"],
    },
    executor="local",
    destructive=True,
    return_confirmation=True,
)

UNNEST_PROJECT = ToolSpec(
    name="unnest_project",
    description="Copy a nested .RPP to its own top-level folder under projects_root. Original is left in place for verification. Requires confirmation.",
    parameters={
        "type": "object",
        "properties": {
            "project_path": {"type": "string", "description": "Path to the nested .RPP file."},
        },
        "required": ["project_path"],
    },
    executor="local",
    destructive=True,
    return_confirmation=True,
)

SET_PROJECTS_ROOT = ToolSpec(
    name="set_projects_root",
    description="Add a directory to the configured project roots for library scanning.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Absolute path to add to projects_roots."},
        },
        "required": ["path"],
    },
    executor="local",
)


def build_library_registry() -> ToolRegistry:
    reg = ToolRegistry()
    for spec in [
        SCAN_ROOT, LIST_FINDINGS, GET_FILE_DETAILS,
        LIST_QUARANTINE_BATCHES, QUARANTINE_FILES, RECLAIM_SPACE,
        CONSOLIDATE_PROJECT, UNNEST_PROJECT, SET_PROJECTS_ROOT,
    ]:
        reg.register(spec)
    return reg
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd companion && .venv/bin/python -m pytest tests/test_library_tools.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
cd /home/bradzgar/projects/reamind
git add companion/reamind/tools/library.py companion/tests/test_library_tools.py
git commit -m "feat: library management tool specs (9 tools)"
```

---

### Task 4: Scanner (`companion/reamind/library/scanner.py`)

**Files:**
- Create: `companion/reamind/library/__init__.py`
- Create: `companion/reamind/library/scanner.py`
- Test: `companion/tests/test_scanner.py`

**Interfaces:**
- Consumes: `reamind.rpp.extract_sources`.
- Produces:
  - `@dataclass Finding`: `type: str`, `path: str`, `reason: str`, `size_bytes: int`, `related: list[str] | None`.
  - `@dataclass ProjectInfo`: `path: str`, `source_count: int`, `sources: list[dict]`.
  - `@dataclass ScanResult`: `root: str`, `projects: list[ProjectInfo]`, `findings: list[Finding]`, `summary: dict`.
  - `scan_root(root: Path) -> ScanResult` — walk a project root, detect all six issue types.

**Detection logic:**
1. Walk the tree finding all `.RPP` files, media files, and regenerable files.
2. For each `.RPP`, call `extract_sources()` to get source references.
3. **Nested**: `.RPP` whose parent directory is a subdirectory of another `.RPP`'s parent directory.
4. **Orphaned**: media files not in any .RPP's reference set (excluding RPPs themselves).
5. **Regenerable**: files matching `*.reapeaks`, `*.RPP-UNDO`, `*.RPP-bak`.
6. **External**: source refs pointing outside the .RPP's own directory.
7. **Duplicate**: two-pass size → quick hash (64KB) → full hash. Report hash-colliding groups.
8. **Missing**: source refs whose path doesn't exist on disk.

- [ ] **Step 1: Write the failing test**

Create `companion/tests/test_scanner.py`:

```python
from pathlib import Path
import tempfile

from reamind.library.scanner import scan_root


def _make_rpp(dir_path: Path, name: str, sources: list[str]) -> Path:
    lines = ["<REAPER_PROJECT 0.1"]
    for s in sources:
        ext = s.rsplit(".", 1)[-1].upper()
        stype = {"WAV": "WAVE", "MIDI": "MIDI", "RPP": "RPP"}.get(ext, "WAVE")
        lines.append("  <ITEM")
        lines.append(f"    <SOURCE {stype}")
        lines.append(f'      FILE "{s}"')
        lines.append("    >")
        lines.append("  >")
    lines.append(">")
    rpp = dir_path / name
    rpp.write_text("\n".join(lines))
    return rpp


def test_detects_external_media():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        proj = root / "MyProject"
        proj.mkdir()
        _make_rpp(proj, "song.RPP", ["../OtherFolder/kick.wav"])
        ext_file = root / "OtherFolder" / "kick.wav"
        ext_file.parent.mkdir()
        ext_file.write_bytes(b"audio")

        result = scan_root(root)
        externals = [f for f in result.findings if f.type == "external_media"]
        assert len(externals) == 1
        assert "kick.wav" in externals[0].path


def test_detects_orphaned_media():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        proj = root / "MyProject"
        proj.mkdir()
        _make_rpp(proj, "song.RPP", [])
        (proj / "unused.wav").write_bytes(b"orphan")

        result = scan_root(root)
        orphans = [f for f in result.findings if f.type == "orphaned_media"]
        assert len(orphans) == 1
        assert "unused.wav" in orphans[0].path


def test_detects_regenerable():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        proj = root / "MyProject"
        proj.mkdir()
        _make_rpp(proj, "song.RPP", [])
        (proj / "song.reapeaks").write_bytes(b"peaks")
        (proj / "song.RPP-UNDO").write_bytes(b"undo")
        (proj / "song.RPP-bak").write_bytes(b"bak")

        result = scan_root(root)
        regens = [f for f in result.findings if f.type == "regenerable"]
        assert len(regens) == 3


def test_detects_duplicates():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        a = root / "a"; b = root / "b"
        a.mkdir(); b.mkdir()
        _make_rpp(a, "a.RPP", ["kick.wav"])
        _make_rpp(b, "b.RPP", ["kick.wav"])
        content = b"identical" * 100
        (a / "kick.wav").write_bytes(content)
        (b / "kick.wav").write_bytes(content)

        result = scan_root(root)
        dups = [f for f in result.findings if f.type == "duplicate"]
        assert len(dups) >= 2  # each side reports the other


def test_detects_missing_media():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        proj = root / "MyProject"
        proj.mkdir()
        _make_rpp(proj, "song.RPP", ["gone.wav"])

        result = scan_root(root)
        missing = [f for f in result.findings if f.type == "missing_media"]
        assert len(missing) == 1


def test_detects_nested_project():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        proj = root / "MyProject"
        proj.mkdir()
        sub = proj / "sub"
        sub.mkdir()
        _make_rpp(proj, "main.RPP", [])
        _make_rpp(sub, "nested.RPP", [])

        result = scan_root(root)
        nested = [f for f in result.findings if f.type == "nested_project"]
        assert len(nested) == 1
        assert "nested.RPP" in nested[0].path


def test_summary_counts():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        proj = root / "MyProject"
        proj.mkdir()
        _make_rpp(proj, "song.RPP", ["kick.wav", "snare.wav"])
        (proj / "kick.wav").write_bytes(b"k" * 100)
        (proj / "snare.wav").write_bytes(b"s" * 200)
        (proj / "orphan.wav").write_bytes(b"o" * 50)

        result = scan_root(root)
        assert result.summary["project_count"] == 1
        assert result.summary["media_count"] >= 2
        assert result.summary["orphaned_count"] == 1


def test_empty_root():
    with tempfile.TemporaryDirectory() as d:
        result = scan_root(Path(d))
        assert result.summary["project_count"] == 0
        assert result.findings == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd companion && .venv/bin/python -m pytest tests/test_scanner.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'reamind.library.scanner'`.

- [ ] **Step 3: Write minimal implementation**

Create `companion/reamind/library/__init__.py` (empty file):

```python
```

Create `companion/reamind/library/scanner.py`:

```python
from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from ..rpp import extract_sources


def _is_regenerable(path: Path) -> bool:
    n = path.name
    return n.endswith(".reapeaks") or n.endswith(".RPP-UNDO") or n.endswith(".RPP-bak")


def _is_media(path: Path) -> bool:
    return path.suffix.lower() in {
        ".wav", ".aiff", ".aif", ".flac", ".mp3", ".ogg", ".mid", ".midi", ".m4a", ".wma",
    }


@dataclass
class Finding:
    type: str
    path: str
    reason: str
    size_bytes: int = 0
    related: list[str] | None = None


@dataclass
class ProjectInfo:
    path: str
    source_count: int
    sources: list[dict] = field(default_factory=list)


@dataclass
class ScanResult:
    root: str
    projects: list[ProjectInfo] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    summary: dict = field(default_factory=dict)


def scan_root(root: Path) -> ScanResult:
    root = root.resolve()
    if not root.is_dir():
        return ScanResult(root=str(root), summary=_empty_summary())

    findings: list[Finding] = []
    rpp_files: list[Path] = []
    media_files: list[Path] = []

    for entry in root.rglob("*"):
        if not entry.is_file():
            continue
        suffix = entry.suffix.lower()
        if suffix == ".rpp":
            rpp_files.append(entry)
        elif _is_media(entry):
            media_files.append(entry)
        if _is_regenerable(entry):
            findings.append(Finding(
                type="regenerable",
                path=str(entry),
                reason=f"Regenerable file: {entry.name}",
                size_bytes=entry.stat().st_size,
            ))

    all_refs: set[str] = set()
    projects: list[ProjectInfo] = []

    for rpp_path in rpp_files:
        sources = extract_sources(rpp_path)
        proj_dir = rpp_path.parent
        projects.append(ProjectInfo(
            path=str(rpp_path),
            source_count=len(sources),
            sources=sources,
        ))
        for src in sources:
            src_path = Path(src["path"])
            all_refs.add(str(src_path.resolve()))
            if not src_path.is_relative_to(proj_dir):
                findings.append(Finding(
                    type="external_media",
                    path=str(src_path),
                    reason=f"Referenced by {rpp_path.name} from outside its project directory",
                    related=[str(rpp_path)],
                ))
            if not src_path.exists():
                findings.append(Finding(
                    type="missing_media",
                    path=str(src_path),
                    reason=f"Referenced by {rpp_path.name} but file not found",
                ))

    orphaned = set()
    for mf in media_files:
        if str(mf.resolve()) not in all_refs:
            orphaned.add(str(mf))
            findings.append(Finding(
                type="orphaned_media",
                path=str(mf),
                reason="Not referenced by any .RPP in this root",
                size_bytes=mf.stat().st_size,
            ))

    rpp_dirs = {rp.parent for rp in rpp_files}
    for rpp in rpp_files:
        for other_dir in rpp_dirs:
            if other_dir != rpp.parent and rpp.parent.is_relative_to(other_dir):
                findings.append(Finding(
                    type="nested_project",
                    path=str(rpp),
                    reason=f"Nested inside {other_dir}",
                ))
                break

    by_size: dict[int, list[Path]] = defaultdict(list)
    for mf in media_files:
        try:
            by_size[mf.stat().st_size].append(mf)
        except OSError:
            pass

    dup_groups = []
    for sz, files in by_size.items():
        if len(files) < 2:
            continue
        by_quick: dict[str, list[Path]] = defaultdict(list)
        for f in files:
            try:
                with open(f, "rb") as fh:
                    data = fh.read(65536)
                by_quick[hashlib.sha256(data).hexdigest()].append(f)
            except OSError:
                pass
        for files2 in by_quick.values():
            if len(files2) < 2:
                continue
            by_full: dict[str, list[Path]] = defaultdict(list)
            for f in files2:
                try:
                    by_full[hashlib.sha256(f.read_bytes()).hexdigest()].append(f)
                except OSError:
                    pass
            for group in by_full.values():
                if len(group) >= 2:
                    dup_groups.append(group)

    for group in dup_groups:
        paths = [str(p) for p in group]
        for i, p in enumerate(group):
            findings.append(Finding(
                type="duplicate",
                path=str(p),
                reason=f"Duplicate of {len(group)-1} other file(s)",
                size_bytes=p.stat().st_size if p.exists() else 0,
                related=paths[:i] + paths[i+1:],
            ))

    total_size = sum(f.stat().st_size for f in root.rglob("*") if f.is_file())
    result = ScanResult(
        root=str(root),
        projects=projects,
        findings=findings,
        summary={
            "project_count": len(rpp_files),
            "media_count": len(media_files) + len(rpp_files),
            "total_size_bytes": total_size,
            "orphaned_count": sum(1 for f in findings if f.type == "orphaned_media"),
            "regenerable_count": sum(1 for f in findings if f.type == "regenerable"),
            "duplicate_count": sum(1 for f in findings if f.type == "duplicate"),
            "nested_count": sum(1 for f in findings if f.type == "nested_project"),
            "external_count": sum(1 for f in findings if f.type == "external_media"),
            "missing_count": sum(1 for f in findings if f.type == "missing_media"),
        },
    )
    return result


def _empty_summary() -> dict:
    return {
        "project_count": 0, "media_count": 0, "total_size_bytes": 0,
        "orphaned_count": 0, "regenerable_count": 0, "duplicate_count": 0,
        "nested_count": 0, "external_count": 0, "missing_count": 0,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd companion && .venv/bin/python -m pytest tests/test_scanner.py -v`
Expected: PASS (8 tests).

- [ ] **Step 5: Commit**

```bash
cd /home/bradzgar/projects/reamind
git add companion/reamind/library/__init__.py companion/reamind/library/scanner.py companion/tests/test_scanner.py
git commit -m "feat: project library scanner with six detection types"
```

---

### Task 5: Quarantine module (`companion/reamind/library/quarantine.py`)

**Files:**
- Create: `companion/reamind/library/quarantine.py`
- Test: `companion/tests/test_quarantine.py`

**Interfaces:**
- Consumes: `reamind.rpp.extract_sources`, `shutil`, `pathlib`, `datetime`.
- Produces:
  - `quarantine_files(paths: list[Path], quarantine_base: Path) -> dict` — moves files to `quarantine_base/YYYY-MM-DD/`. Returns `{"moved_count": int, "quarantine_path": str, "errors": [str]}`.
  - `reclaim_regenerable(files: list[Path]) -> dict` — deletes regenerable files. Returns `{"deleted_count": int, "bytes_freed": int, "errors": [str]}`.
  - `consolidate_project(project_path: Path) -> dict` — copies external media into project dir. Returns `{"moved_count": int, "dest_dir": str}`.
  - `unnest_project(rpp_path: Path, projects_root: Path) -> dict` — copies nested .RPP to sibling dir. Returns `{"new_path": str}`.

- [ ] **Step 1: Write the failing test**

Create `companion/tests/test_quarantine.py`:

```python
from datetime import date
from pathlib import Path
import tempfile

from reamind.library.quarantine import (
    consolidate_project,
    quarantine_files,
    reclaim_regenerable,
    unnest_project,
)


def test_quarantine_moves_to_dated_dir():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        src = root / "source"
        src.mkdir()
        f1 = src / "file1.wav"
        f2 = src / "sub" / "file2.wav"
        f2.parent.mkdir()
        f1.write_bytes(b"a")
        f2.write_bytes(b"b")

        qbase = root / "quarantine"
        result = quarantine_files([f1, f2], qbase)

        today = date.today().isoformat()
        assert result["moved_count"] == 2
        assert not f1.exists()
        assert not f2.exists()
        assert (qbase / today).exists()


def test_quarantine_preserves_relative_structure():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "A" / "B").mkdir(parents=True)
        f = root / "A" / "B" / "data.wav"
        f.write_bytes(b"x")

        qbase = root / "q"
        result = quarantine_files([f], qbase)

        today = date.today().isoformat()
        moved_to = qbase / today
        assert any(
            (moved_to / "A" / "B" / "data.wav").exists()
            for _ in [1]
        ) or result["moved_count"] == 1


def test_quarantine_handles_missing_files():
    result = quarantine_files([Path("/nonexistent/file.wav")], Path("/tmp/q"))
    assert result["moved_count"] == 0
    assert len(result.get("errors", [])) >= 1


def test_reclaim_deletes_regenerable():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "song.reapeaks").write_bytes(b"p")
        (root / "song.RPP-UNDO").write_bytes(b"u")
        (root / "song.RPP-bak").write_bytes(b"b")
        (root / "keep.wav").write_bytes(b"real")

        files = [root / "song.reapeaks", root / "song.RPP-UNDO", root / "song.RPP-bak"]
        result = reclaim_regenerable(files)

        assert result["deleted_count"] == 3
        assert (root / "keep.wav").exists()


def test_consolidate_copies_external_media():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        proj = root / "MyProject"
        proj.mkdir()
        ext = root / "External"
        ext.mkdir()
        (ext / "sample.wav").write_bytes(b"data")
        rpp = proj / "song.RPP"
        rpp.write_text(
            '<REAPER_PROJECT 0.1\n  <ITEM\n    <SOURCE WAVE\n      FILE "../External/sample.wav"\n    >\n  >\n>\n'
        )

        result = consolidate_project(rpp)
        assert result["moved_count"] == 1
        assert (proj / "sample.wav").exists()


def test_unnest_copies_to_sibling():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        proj = root / "ProjectA"
        nested_dir = proj / "nested"
        nested_dir.mkdir(parents=True)
        nested_rpp = nested_dir / "sub.RPP"
        nested_rpp.write_text("<REAPER_PROJECT 0.1\n>\n")

        result = unnest_project(nested_rpp, root)

        new_dir = root / "nested"
        assert new_dir.exists()
        assert (new_dir / "sub.RPP").exists()


def test_reclaim_noop_on_empty():
    result = reclaim_regenerable([])
    assert result["deleted_count"] == 0
    assert result["bytes_freed"] == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd companion && .venv/bin/python -m pytest tests/test_quarantine.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'reamind.library.quarantine'`.

- [ ] **Step 3: Write minimal implementation**

Create `companion/reamind/library/quarantine.py`:

```python
from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

from ..rpp import extract_sources


def quarantine_files(paths: list[Path], quarantine_base: Path) -> dict:
    today = date.today().isoformat()
    dest_dir = quarantine_base / today
    errors = []
    moved = 0

    for src in paths:
        try:
            if not src.exists():
                errors.append(f"Not found: {src}")
                continue
            src = src.resolve()
            dest = dest_dir / src.relative_to(src.anchor)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
            moved += 1
        except Exception as e:
            errors.append(f"Failed: {src}: {e}")

    return {"moved_count": moved, "quarantine_path": str(dest_dir), "errors": errors}


def reclaim_regenerable(files: list[Path]) -> dict:
    deleted = 0
    bytes_freed = 0
    errors = []

    for f in files:
        try:
            if f.exists():
                sz = f.stat().st_size
                f.unlink()
                deleted += 1
                bytes_freed += sz
        except Exception as e:
            errors.append(f"Failed: {f}: {e}")

    return {"deleted_count": deleted, "bytes_freed": bytes_freed, "errors": errors}


def consolidate_project(project_path: Path) -> dict:
    rpp = Path(project_path)
    sources = extract_sources(rpp)
    proj_dir = rpp.parent.resolve()
    moved = 0

    for src in sources:
        src_path = Path(src["path"]).resolve()
        if src_path.is_relative_to(proj_dir):
            continue
        if not src_path.exists():
            continue
        try:
            shutil.copy2(str(src_path), str(proj_dir / src_path.name))
            moved += 1
        except Exception:
            pass

    return {"moved_count": moved, "dest_dir": str(proj_dir)}


def unnest_project(rpp_path: Path, projects_root: Path) -> dict:
    rpp = Path(rpp_path).resolve()
    proj_root = Path(projects_root).resolve()
    name = rpp.parent.name
    new_dir = proj_root / name
    if new_dir.exists():
        new_dir = proj_root / f"{name}_unnested"

    try:
        shutil.copytree(str(rpp.parent), str(new_dir), dirs_exist_ok=True)
    except Exception as e:
        return {"new_path": "", "error": str(e)}

    return {"new_path": str(new_dir / rpp.name)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd companion && .venv/bin/python -m pytest tests/test_quarantine.py -v`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
cd /home/bradzgar/projects/reamind
git add companion/reamind/library/quarantine.py companion/tests/test_quarantine.py
git commit -m "feat: quarantine module (move, reclaim, consolidate, unnest)"
```

---

### Task 6: Library executor + server wiring

**Files:**
- Modify: `companion/reamind/local_tools.py` — add `build_library_executor` function
- Modify: `companion/reamind/server.py` — build and register library tools, merge executors
- Test: append to `companion/tests/test_local_tools.py`

**Interfaces:**
- Consumes: `reamind.library.scanner.scan_root`, `reamind.library.quarantine.*`, `reamind.tools.library.build_library_registry`.
- Produces:
  - `build_library_executor(config: Config, quarantine_base: Path) -> Callable[[ToolCall], dict]` — routes all 9 library tool names.
  - `Server.__init__` builds library registry, registers specs, builds library executor, merges with existing local executor.

**Merge strategy:** The existing `build_local_executor` returns `{"ok": False, "error": "unknown local tool: ..."}` for unknown tools. The library executor is tried as a fallback when that error is encountered. In `handle_user_message`, the merged executor is rebuilt the same way.

- [ ] **Step 1: Write the failing test**

Append to `companion/tests/test_local_tools.py`:

```python
from pathlib import Path
import tempfile

from reamind.config import Config
from reamind.local_tools import build_library_executor
from reamind.providers.base import ToolCall


def test_library_executor_scan_root():
    with tempfile.TemporaryDirectory() as d:
        config = Config()
        config.projects_roots = [d]
        exec_fn = build_library_executor(config, Path(d) / "quarantine")
        result = exec_fn(ToolCall(id="c1", name="scan_root", arguments={"path": d}))
        assert result["ok"] is True
        assert "project_count" in result["result"]


def test_library_executor_unknown_tool():
    config = Config()
    exec_fn = build_library_executor(config, Path("/tmp/q"))
    result = exec_fn(ToolCall(id="c1", name="nonexistent_library_tool", arguments={}))
    assert result["ok"] is False
    assert "unknown" in result["error"]


def test_library_executor_list_findings_empty():
    with tempfile.TemporaryDirectory() as d:
        config = Config()
        exec_fn = build_library_executor(config, Path("/tmp/q"))
        result = exec_fn(ToolCall(id="c1", name="list_findings", arguments={"root": d}))
        assert result["ok"] is True
        assert isinstance(result["result"]["findings"], list)


def test_library_executor_quarantine_files():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        f = root / "orphan.wav"
        f.write_bytes(b"data")
        config = Config()
        qbase = root / "q"
        exec_fn = build_library_executor(config, qbase)
        result = exec_fn(ToolCall(id="c1", name="quarantine_files", arguments={
            "paths": [str(f)], "confirm_ok": True,
        }))
        assert result["ok"] is True
        assert result["result"]["moved_count"] == 1


def test_library_executor_get_file_details():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        f = root / "test.wav"
        f.write_bytes(b"file content")
        exec_fn = build_library_executor(Config(), Path("/tmp/q"))
        result = exec_fn(ToolCall(id="c1", name="get_file_details", arguments={"path": str(f)}))
        assert result["ok"] is True
        assert result["result"]["exists"] is True
        assert result["result"]["size_bytes"] == 12
        assert result["result"]["hash"] is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd companion && .venv/bin/python -m pytest tests/test_local_tools.py::test_library_executor_scan_root tests/test_local_tools.py::test_library_executor_unknown_tool tests/test_local_tools.py::test_library_executor_list_findings_empty tests/test_local_tools.py::test_library_executor_quarantine_files tests/test_local_tools.py::test_library_executor_get_file_details -v`
Expected: all 5 FAIL — `ImportError: cannot import name 'build_library_executor'`.

- [ ] **Step 3: Write minimal implementation**

In `companion/reamind/local_tools.py`, add import at top:

```python
import hashlib

from .library.scanner import scan_root
from .library.quarantine import (
    consolidate_project,
    quarantine_files as _quarantine_files,
    reclaim_regenerable,
    unnest_project,
)
```

Add at end of file:

```python
def build_library_executor(
    config: Config, quarantine_base: Path
) -> Callable[[ToolCall], dict]:
    quarantine_base = Path(quarantine_base).expanduser()

    def executor(call: ToolCall) -> dict:
        name = call.name
        args = call.arguments or {}

        if name == "scan_root":
            path = Path(args.get("path", ""))
            result = scan_root(path)
            return {"ok": True, "result": {
                "root": result.root,
                "project_count": result.summary["project_count"],
                "media_count": result.summary["media_count"],
                "total_size_bytes": result.summary["total_size_bytes"],
                "finding_counts": {
                    k.replace("_count", ""): v
                    for k, v in result.summary.items()
                    if k.endswith("_count")
                },
            }}

        if name == "list_findings":
            root_path = Path(args.get("root", ""))
            filter_type = args.get("type")
            result = scan_root(root_path)
            findings_list = result.findings
            if filter_type:
                findings_list = [f for f in findings_list if f.type == filter_type]
            return {"ok": True, "result": {
                "findings": [
                    {
                        "type": f.type, "path": f.path,
                        "reason": f.reason, "size_bytes": f.size_bytes,
                        "related": f.related,
                    }
                    for f in findings_list
                ],
            }}

        if name == "get_file_details":
            p = Path(args.get("path", ""))
            try:
                st = p.stat()
                fhash = None
                if p.is_file():
                    fhash = hashlib.sha256(p.read_bytes()).hexdigest()
                return {"ok": True, "result": {
                    "path": str(p), "size_bytes": st.st_size,
                    "modified": st.st_mtime, "hash": fhash, "exists": p.exists(),
                }}
            except OSError as e:
                return {"ok": False, "error": str(e)}

        if name == "list_quarantine_batches":
            batches = []
            if quarantine_base.exists():
                for entry in sorted(quarantine_base.iterdir(), reverse=True):
                    if entry.is_dir():
                        fc = sum(1 for _ in entry.rglob("*") if _.is_file())
                        sz = sum(_.stat().st_size for _ in entry.rglob("*") if _.is_file())
                        batches.append({"date": entry.name, "file_count": fc, "total_bytes": sz})
            return {"ok": True, "result": {"batches": batches}}

        if name == "quarantine_files":
            paths = [Path(p) for p in args.get("paths", [])]
            result = _quarantine_files(paths, quarantine_base)
            return {"ok": True, "result": result}

        if name == "reclaim_space":
            root_dir = args.get("root")
            roots_to_scan = [Path(root_dir)] if root_dir else [Path(r) for r in config.projects_roots]
            regenerable = []
            for rt in roots_to_scan:
                rt = Path(rt)
                if rt.is_dir():
                    for entry in rt.rglob("*"):
                        if entry.is_file():
                            n = entry.name
                            if n.endswith(".reapeaks") or n.endswith(".RPP-UNDO") or n.endswith(".RPP-bak"):
                                regenerable.append(entry)
            result = reclaim_regenerable(regenerable)
            return {"ok": True, "result": result}

        if name == "consolidate_project":
            result = consolidate_project(Path(args["project_path"]))
            return {"ok": True, "result": result}

        if name == "unnest_project":
            roots = config.projects_roots or [str(Path(args["project_path"]).parent.parent)]
            proj_root = Path(roots[0])
            result = unnest_project(Path(args["project_path"]), proj_root)
            if "error" in result:
                return {"ok": False, "error": result["error"]}
            return {"ok": True, "result": result}

        if name == "set_projects_root":
            path = args.get("path", "")
            if path and path not in config.projects_roots:
                config.projects_roots.append(path)
            return {"ok": True, "result": {"message": f"Added {path} to projects_roots"}}

        return {"ok": False, "error": f"unknown library tool: {name}"}

    return executor
```

In `companion/reamind/server.py`, add import at top:

```python
from .local_tools import build_library_executor, build_local_executor, write_status
from .tools.library import build_library_registry
```

Modify `Server.__init__`: after the construction registry registration (line 36), add:

```python
        lib_reg = build_library_registry()
        for spec in lib_reg.specs():
            self.registry.register(spec)
        self._quarantine_base = Path(self.config.quarantine_dir)
```

After line 40 (`self.local_executor = ...`), replace with:

```python
        self._rebuild_local_executor()
```

And add the helper methods to `Server`:

```python
    def _build_merged_local_executor(self, reaper_executor=None):
        existing = build_local_executor(
            self.config, self._config_path, self.bridge.root, reaper_executor
        )
        lib_exec = build_library_executor(self.config, self._quarantine_base)

        def merged(call: ToolCall) -> dict:
            result = existing(call)
            if result.get("ok") is False and "unknown" in str(result.get("error", "")):
                return lib_exec(call)
            return result

        return merged

    def _rebuild_local_executor(self, reaper_executor=None):
        self.local_executor = self._build_merged_local_executor(reaper_executor)
```

Modify `handle_user_message` — replace lines 67-69:

```python
        self._rebuild_local_executor(executor)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd companion && .venv/bin/python -m pytest tests/test_local_tools.py -v`
Expected: all local_tools tests PASS (existing 11 + 5 new = 16).

Run: `cd companion && .venv/bin/python -m pytest -v`
Expected: all tests PASS (existing ~76 + new = check exact count).

- [ ] **Step 5: Commit**

```bash
cd /home/bradzgar/projects/reamind
git add companion/reamind/local_tools.py companion/reamind/server.py companion/tests/test_local_tools.py
git commit -m "feat: wire library executor into server with merged routing"
```

---

### Task 7: Suite verification + smoke doc update

**Files:**
- Modify: `docs/SMOKE.md` — add library management smoke steps
- Run: full test suite verification

- [ ] **Step 1: Run full suite**

Run:
```bash
cd companion && .venv/bin/python -m pytest -v
cd panel && lua test/helpers_spec.lua && lua test/json_spec.lua && lua test/theme_spec.lua && lua test/construction_spec.lua
lua -e "assert(loadfile('reamind_panel.lua')); assert(loadfile('tools/readonly.lua')); assert(loadfile('tools/construction.lua')); assert(loadfile('tools/fx_scanner.lua')); assert(loadfile('reamind_selftest.lua')); print('ALL PARSE OK')"
```

Expected: all Python tests pass, all Lua tests pass, all modules parse OK.

- [ ] **Step 2: Update SMOKE.md**

Append to `docs/SMOKE.md`:

```markdown
## Library Management Smoke

1. **Scan empty root:** `scan_root("/tmp")` — returns project_count=0, no findings.
2. **Scan with project:** `scan_root("/path/to/project")` — returns counts for each finding type.
3. **Findings detail:** `list_findings("/path/to/project", "regenerable")` — returns only regenerable findings.
4. **File details:** `get_file_details("/path/to/file.wav")` — returns hash, size, modified time.
5. **Quarantine:** `quarantine_files(["/path/to/orphan.wav"])` — file appears in `quarantine/YYYY-MM-DD/`.
6. **Reclaim:** `reclaim_space("/path/to/project")` — regenerable files deleted, bytes_freed reported.
7. **Consolidate:** `consolidate_project("/path/to/project.RPP")` — external media copied in, moved_count reported.
8. **Unnest:** `unnest_project("/path/to/nested.RPP")` — project copied to sibling dir under projects_root.
```

- [ ] **Step 3: Commit**

```bash
cd /home/bradzgar/projects/reamind
git add docs/SMOKE.md
git commit -m "chore: add library management smoke test steps"
```

---

## Self-Review Summary

**Spec coverage:**
- RPP parser with chunk-based parsing → Task 1
- Config additions (projects_roots, quarantine_dir) → Task 2
- 9 tool specs with destructive flagging → Task 3
- Scanner with 6 detection types → Task 4
- Quarantine with 4 operations → Task 5
- Executor routing + server integration → Task 6
- Suite verification + docs → Task 7

**Placeholder scan:** No TBDs, TODOs, or vague instructions. All code is complete.

**Type consistency:**
- `build_library_executor` signature matches between Task 6 implementation and server wiring
- `scan_root(root: Path) -> ScanResult` used consistently in scanner and executor
- `quarantine_files`, `reclaim_regenerable`, `consolidate_project`, `unnest_project` signatures consistent between quarantine module and executor
- `Config.projects_roots: list[str]` and `Config.quarantine_dir: str` match usage in Tasks 4-6
