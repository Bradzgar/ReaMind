# ReaMind Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the ReaMind foundation — a docked ReaImGui chat panel in REAPER that launches a Python "brain" companion, talks to a local LLM, and lets the LLM call read-only REAPER tools over a file-based JSON bridge, streaming replies back to the panel.

**Architecture:** Two processes. A thin Lua panel inside REAPER (UI + the only code that touches the ReaScript API) and a Python companion (LLM provider, agent loop, tool routing). They communicate exclusively through small JSON files in a shared `bridge/` directory (no sockets, no HTTP between them). This plan implements spec phases 1–2 (bridge + skeletons + local provider + agent loop + read-only project-awareness tools).

**Tech Stack:** Python 3.11 (stdlib only at runtime; `urllib` for LLM HTTP; `pytest` dev-only), Lua 5.x (standalone `lua` for helper tests), REAPER + ReaImGui (via ReaPack), OpenAI-compatible local model servers (Ollama `:11434`, LM Studio `:1234`).

## Global Constraints

- Python **3.11+**. Runtime code MUST use only the Python standard library (LLM HTTP via `urllib.request`). `pytest` is the ONLY dev/test dependency.
- Lua panel is **thin**: all non-trivial logic lives in the Python companion. Only pure Lua helpers (JSON, formatting, arg coercion) get unit tests; they run under standalone `lua` with a zero-dependency assert runner (NOT busted).
- IPC is **files only** — JSON files written atomically (write temp file, then `os.rename`). No sockets/HTTP between panel and companion.
- Bridge directory layout is fixed: `inbox/`, `chat/`, `requests/`, `results/` (each holds zero-padded `%09d.json` or `<id>.json` files), plus `heartbeat.json` and `session.json`. The `bridge/` dir is runtime-only and git-ignored.
- Config lives at `~/.config/reamind/config.json`. Missing config is created from defaults.
- REAPER tools are addressed by **track GUID** wherever a track is referenced (never bare index) so references stay valid as the project changes.
- Every REAPER tool executed by the panel is wrapped in a named **undo block** (`reaper.Undo_BeginBlock` / `reaper.Undo_EndBlock`).
- Tool call `id` values are unique per call; the panel tracks processed ids to prevent double execution.
- Repo root: `/home/bradzgar/projects/reamind`. Git identity already set (user.name=Brad, user.email=bradzgar@cachyos.local).
- Commit after every task with a Conventional Commits message.

---

## File Structure

```
reamind/
  .gitignore                         # ignores bridge/, venv, caches
  panel/                             # Lua — runs INSIDE REAPER
    reamind_panel.lua                # ReaImGui docked UI + defer loop + executor (manual smoke)
    ipc.lua                          # bridge file read/write helpers (uses reaper API for dir list)
    json.lua                         # vendored pure-Lua JSON encode/decode
    tools/
      readonly.lua                   # get_project_summary, list_tracks, get_track impls
    helpers.lua                      # pure helpers: seq formatting, color/arg coercion (tested)
    test/
      run.lua                        # zero-dep assert runner
      json_spec.lua                  # JSON round-trip tests
      helpers_spec.lua               # helpers tests
  companion/
    pyproject.toml
    reamind/
      __init__.py                    # __version__
      jsonio.py                      # atomic_write_json, read_json
      bridge.py                      # Bridge: inbox/chat/requests/results, heartbeat, stale clear
      config.py                      # dataclasses + load/save/validate
      providers/
        __init__.py
        base.py                      # Message, ToolCall, ToolSpec, ChatResult, LLMProvider
        fake.py                      # FakeProvider (scripted; tests)
        local.py                     # LocalProvider (OpenAI-compatible) + detect/list_models
      tools/
        __init__.py
        registry.py                  # ToolRegistry + arg validation
        reaper_readonly.py           # ToolSpec definitions for the 3 read-only tools
      agent.py                       # run_turn agent loop
      server.py                      # entrypoint: wires everything, main loop
    tests/
      test_jsonio.py
      test_bridge.py
      test_config.py
      test_providers.py
      test_local_provider.py
      test_registry.py
      test_agent.py
      test_server.py
  docs/superpowers/                  # specs + this plan
```

---

### Task 1: Repo scaffolding & Python package skeleton

**Files:**
- Create: `.gitignore`
- Create: `companion/pyproject.toml`
- Create: `companion/reamind/__init__.py`
- Test: `companion/tests/test_jsonio.py` (placeholder import test replaced in Task 2 — here we add a version test)

**Interfaces:**
- Consumes: nothing.
- Produces: importable package `reamind` with `reamind.__version__` (str).

- [ ] **Step 1: Write the failing test**

Create `companion/tests/test_version.py`:

```python
import reamind


def test_version_is_string():
    assert isinstance(reamind.__version__, str)
    assert reamind.__version__
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd companion && python -m pytest tests/test_version.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'reamind'` (or pytest not installed → install it first, see Step 3).

- [ ] **Step 3: Create scaffolding**

Create `.gitignore`:

```gitignore
# ReaMind
bridge/
__pycache__/
*.pyc
.pytest_cache/
.venv/
venv/
*.egg-info/
dist/
build/
```

Create `companion/pyproject.toml`:

```toml
[project]
name = "reamind"
version = "0.1.0"
description = "ReaMind companion — the AI brain for the REAPER assistant panel"
requires-python = ">=3.11"
dependencies = []

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["."]
include = ["reamind*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

Create `companion/reamind/__init__.py`:

```python
__version__ = "0.1.0"
```

Set up the dev environment (creates a venv and installs pytest + the package in editable mode):

```bash
cd companion && python -m venv .venv && .venv/bin/pip install -e ".[dev]"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd companion && .venv/bin/python -m pytest tests/test_version.py -v`
Expected: PASS.

> For all later tasks, "run pytest" means `cd companion && .venv/bin/python -m pytest ...`.

- [ ] **Step 5: Commit**

```bash
cd /home/bradzgar/projects/reamind
git add .gitignore companion/pyproject.toml companion/reamind/__init__.py companion/tests/test_version.py
git commit -m "chore: scaffold companion python package"
```

---

### Task 2: Atomic JSON file I/O (`jsonio.py`)

**Files:**
- Create: `companion/reamind/jsonio.py`
- Test: `companion/tests/test_jsonio.py`

**Interfaces:**
- Consumes: stdlib only.
- Produces:
  - `atomic_write_json(path: pathlib.Path, obj: Any) -> None` — serialize `obj` to JSON, write to `path` atomically (temp file in same dir + `os.replace`).
  - `read_json(path: pathlib.Path) -> Any` — parse JSON file; raises `FileNotFoundError` if missing, `json.JSONDecodeError` if corrupt.

- [ ] **Step 1: Write the failing test**

Create `companion/tests/test_jsonio.py`:

```python
import json
import pathlib

import pytest

from reamind.jsonio import atomic_write_json, read_json


def test_write_then_read_roundtrip(tmp_path: pathlib.Path):
    p = tmp_path / "x.json"
    atomic_write_json(p, {"a": 1, "b": [1, 2, 3]})
    assert read_json(p) == {"a": 1, "b": [1, 2, 3]}


def test_write_leaves_no_temp_files(tmp_path: pathlib.Path):
    p = tmp_path / "x.json"
    atomic_write_json(p, {"a": 1})
    names = [f.name for f in tmp_path.iterdir()]
    assert names == ["x.json"]


def test_read_missing_raises(tmp_path: pathlib.Path):
    with pytest.raises(FileNotFoundError):
        read_json(tmp_path / "nope.json")


def test_write_is_valid_json_on_disk(tmp_path: pathlib.Path):
    p = tmp_path / "x.json"
    atomic_write_json(p, {"k": "v"})
    assert json.loads(p.read_text()) == {"k": "v"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd companion && .venv/bin/python -m pytest tests/test_jsonio.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'reamind.jsonio'`.

- [ ] **Step 3: Write minimal implementation**

Create `companion/reamind/jsonio.py`:

```python
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_json(path: Path, obj: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_json(path: Path) -> Any:
    with open(Path(path), "r", encoding="utf-8") as f:
        return json.load(f)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd companion && .venv/bin/python -m pytest tests/test_jsonio.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
cd /home/bradzgar/projects/reamind
git add companion/reamind/jsonio.py companion/tests/test_jsonio.py
git commit -m "feat: atomic json file io"
```

---

### Task 3: The Bridge (`bridge.py`)

**Files:**
- Create: `companion/reamind/bridge.py`
- Test: `companion/tests/test_bridge.py`

**Interfaces:**
- Consumes: `reamind.jsonio.atomic_write_json`, `reamind.jsonio.read_json`.
- Produces a `Bridge` class (companion's view of the shared dir):
  - `Bridge(root: pathlib.Path)` — sets `self.root`, `self.inbox`, `self.chat`, `self.requests`, `self.results` (Paths), `self.heartbeat` (file), `self.session` (file).
  - `ensure_dirs() -> None`
  - `clear_stale() -> None` — remove all files in the 4 channel dirs + heartbeat + session; recreate empty dirs; reset internal seq counters to 0.
  - `write_session(session_id: str) -> None` — write `{"session_id": ..., "started": <epoch float>}`.
  - `write_heartbeat(pid: int) -> None` — write `{"pid": pid, "ts": <epoch float>}`.
  - `push_chat(role: str, text: str, done: bool = False) -> int` — write `chat/%09d.json` with `{"seq", "role", "text", "done"}`; return the seq used. Monotonic per Bridge instance.
  - `drain_inbox() -> list[dict]` — read+delete `inbox/*.json` sorted by name; return list of parsed dicts.
  - `send_request(tool: str, args: dict, seq: int) -> str` — generate a unique `id` (`"call_" + 8 hex`), write `requests/<id>.json` = `{"id", "seq", "tool", "args"}`, return `id`.
  - `read_result(call_id: str) -> dict | None` — if `results/<call_id>.json` exists, read+delete it, return parsed dict; else `None`.

- [ ] **Step 1: Write the failing test**

Create `companion/tests/test_bridge.py`:

```python
import pathlib

from reamind.bridge import Bridge
from reamind.jsonio import atomic_write_json, read_json


def make(tmp_path: pathlib.Path) -> Bridge:
    b = Bridge(tmp_path / "bridge")
    b.ensure_dirs()
    return b


def test_ensure_dirs_creates_channels(tmp_path):
    b = make(tmp_path)
    for d in (b.inbox, b.chat, b.requests, b.results):
        assert d.is_dir()


def test_push_chat_is_monotonic_and_readable(tmp_path):
    b = make(tmp_path)
    s0 = b.push_chat("assistant", "hello")
    s1 = b.push_chat("status", "thinking", done=False)
    assert s1 == s0 + 1
    files = sorted(b.chat.iterdir())
    assert len(files) == 2
    first = read_json(files[0])
    assert first == {"seq": s0, "role": "assistant", "text": "hello", "done": False}


def test_drain_inbox_reads_in_order_and_deletes(tmp_path):
    b = make(tmp_path)
    atomic_write_json(b.inbox / "000000001.json", {"seq": 1, "text": "first"})
    atomic_write_json(b.inbox / "000000002.json", {"seq": 2, "text": "second"})
    msgs = b.drain_inbox()
    assert [m["text"] for m in msgs] == ["first", "second"]
    assert list(b.inbox.iterdir()) == []


def test_send_request_writes_unique_ids(tmp_path):
    b = make(tmp_path)
    id1 = b.send_request("list_tracks", {}, seq=5)
    id2 = b.send_request("list_tracks", {}, seq=6)
    assert id1 != id2
    payload = read_json(b.requests / f"{id1}.json")
    assert payload["tool"] == "list_tracks"
    assert payload["seq"] == 5
    assert payload["id"] == id1


def test_read_result_returns_none_when_absent_then_consumes(tmp_path):
    b = make(tmp_path)
    assert b.read_result("call_x") is None
    atomic_write_json(b.results / "call_x.json", {"id": "call_x", "ok": True, "result": {"n": 1}})
    got = b.read_result("call_x")
    assert got == {"id": "call_x", "ok": True, "result": {"n": 1}}
    assert b.read_result("call_x") is None


def test_clear_stale_empties_channels_and_resets_seq(tmp_path):
    b = make(tmp_path)
    b.push_chat("assistant", "x")
    atomic_write_json(b.inbox / "000000001.json", {"seq": 1, "text": "y"})
    b.clear_stale()
    assert list(b.chat.iterdir()) == []
    assert list(b.inbox.iterdir()) == []
    assert b.push_chat("assistant", "again") == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd companion && .venv/bin/python -m pytest tests/test_bridge.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'reamind.bridge'`.

- [ ] **Step 3: Write minimal implementation**

Create `companion/reamind/bridge.py`:

```python
from __future__ import annotations

import secrets
import shutil
import time
from pathlib import Path

from .jsonio import atomic_write_json, read_json


class Bridge:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.inbox = self.root / "inbox"
        self.chat = self.root / "chat"
        self.requests = self.root / "requests"
        self.results = self.root / "results"
        self.heartbeat = self.root / "heartbeat.json"
        self.session = self.root / "session.json"
        self._chat_seq = 0

    def ensure_dirs(self) -> None:
        for d in (self.inbox, self.chat, self.requests, self.results):
            d.mkdir(parents=True, exist_ok=True)

    def clear_stale(self) -> None:
        for d in (self.inbox, self.chat, self.requests, self.results):
            if d.exists():
                shutil.rmtree(d)
        for f in (self.heartbeat, self.session):
            try:
                f.unlink()
            except FileNotFoundError:
                pass
        self._chat_seq = 0
        self.ensure_dirs()

    def write_session(self, session_id: str) -> None:
        atomic_write_json(self.session, {"session_id": session_id, "started": time.time()})

    def write_heartbeat(self, pid: int) -> None:
        atomic_write_json(self.heartbeat, {"pid": pid, "ts": time.time()})

    def push_chat(self, role: str, text: str, done: bool = False) -> int:
        seq = self._chat_seq
        self._chat_seq += 1
        atomic_write_json(
            self.chat / f"{seq:09d}.json",
            {"seq": seq, "role": role, "text": text, "done": done},
        )
        return seq

    def drain_inbox(self) -> list[dict]:
        out: list[dict] = []
        for f in sorted(self.inbox.glob("*.json")):
            try:
                out.append(read_json(f))
            except (ValueError, OSError):
                pass
            finally:
                try:
                    f.unlink()
                except FileNotFoundError:
                    pass
        return out

    def send_request(self, tool: str, args: dict, seq: int) -> str:
        call_id = "call_" + secrets.token_hex(4)
        atomic_write_json(
            self.requests / f"{call_id}.json",
            {"id": call_id, "seq": seq, "tool": tool, "args": args},
        )
        return call_id

    def read_result(self, call_id: str) -> dict | None:
        f = self.results / f"{call_id}.json"
        if not f.exists():
            return None
        try:
            data = read_json(f)
        except (ValueError, OSError):
            return None
        finally:
            try:
                f.unlink()
            except FileNotFoundError:
                pass
        return data
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd companion && .venv/bin/python -m pytest tests/test_bridge.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
cd /home/bradzgar/projects/reamind
git add companion/reamind/bridge.py companion/tests/test_bridge.py
git commit -m "feat: file-based ipc bridge (companion side)"
```

---

### Task 4: Config (`config.py`)

**Files:**
- Create: `companion/reamind/config.py`
- Test: `companion/tests/test_config.py`

**Interfaces:**
- Consumes: `reamind.jsonio`.
- Produces:
  - `@dataclass ProviderConfig`: `name: str = "local"`, `model: str | None = None`, `base_url: str | None = None`, `api_key: str | None = None`, `tool_mode: str = "auto"`.
  - `@dataclass SafetyConfig`: `confirm_destructive: bool = True`, `max_tool_iterations: int = 8`, `tool_timeout_s: float = 30.0`.
  - `@dataclass Config`: `provider: ProviderConfig`, `theme: dict`, `projects_roots: list[str]`, `quarantine_dir: str`, `mcp_servers: list`, `templates_dir: str`, `safety: SafetyConfig`, `bridge_dir: str`.
  - `DEFAULT_CONFIG_PATH: Path` = `~/.config/reamind/config.json`.
  - `default_config() -> Config`.
  - `Config.to_dict() -> dict` / `Config.from_dict(d: dict) -> Config`.
  - `load(path: Path | None = None) -> Config` — if missing, write defaults then return them.
  - `save(cfg: Config, path: Path | None = None) -> None`.

- [ ] **Step 1: Write the failing test**

Create `companion/tests/test_config.py`:

```python
import pathlib

from reamind.config import Config, default_config, load, save


def test_default_config_has_local_provider():
    cfg = default_config()
    assert cfg.provider.name == "local"
    assert cfg.safety.max_tool_iterations == 8


def test_roundtrip_to_from_dict():
    cfg = default_config()
    cfg.provider.model = "qwen2.5:7b"
    again = Config.from_dict(cfg.to_dict())
    assert again.provider.model == "qwen2.5:7b"
    assert again.safety.confirm_destructive is True


def test_load_creates_default_when_missing(tmp_path: pathlib.Path):
    p = tmp_path / "sub" / "config.json"
    cfg = load(p)
    assert p.exists()
    assert cfg.provider.name == "local"


def test_save_then_load_preserves_changes(tmp_path: pathlib.Path):
    p = tmp_path / "config.json"
    cfg = default_config()
    cfg.projects_roots = ["/music/projects"]
    save(cfg, p)
    assert load(p).projects_roots == ["/music/projects"]


def test_from_dict_tolerates_missing_keys():
    cfg = Config.from_dict({})
    assert cfg.provider.name == "local"
    assert cfg.mcp_servers == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd companion && .venv/bin/python -m pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'reamind.config'`.

- [ ] **Step 3: Write minimal implementation**

Create `companion/reamind/config.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .jsonio import atomic_write_json, read_json

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "reamind" / "config.json"


@dataclass
class ProviderConfig:
    name: str = "local"
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    tool_mode: str = "auto"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "model": self.model,
            "base_url": self.base_url,
            "api_key": self.api_key,
            "tool_mode": self.tool_mode,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ProviderConfig":
        d = d or {}
        return cls(
            name=d.get("name", "local"),
            model=d.get("model"),
            base_url=d.get("base_url"),
            api_key=d.get("api_key"),
            tool_mode=d.get("tool_mode", "auto"),
        )


@dataclass
class SafetyConfig:
    confirm_destructive: bool = True
    max_tool_iterations: int = 8
    tool_timeout_s: float = 30.0

    def to_dict(self) -> dict:
        return {
            "confirm_destructive": self.confirm_destructive,
            "max_tool_iterations": self.max_tool_iterations,
            "tool_timeout_s": self.tool_timeout_s,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SafetyConfig":
        d = d or {}
        return cls(
            confirm_destructive=d.get("confirm_destructive", True),
            max_tool_iterations=d.get("max_tool_iterations", 8),
            tool_timeout_s=d.get("tool_timeout_s", 30.0),
        )


@dataclass
class Config:
    provider: ProviderConfig = field(default_factory=ProviderConfig)
    theme: dict = field(default_factory=dict)
    projects_roots: list[str] = field(default_factory=list)
    quarantine_dir: str = ""
    mcp_servers: list = field(default_factory=list)
    templates_dir: str = ""
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    bridge_dir: str = ""

    def to_dict(self) -> dict:
        return {
            "provider": self.provider.to_dict(),
            "theme": self.theme,
            "projects_roots": self.projects_roots,
            "quarantine_dir": self.quarantine_dir,
            "mcp_servers": self.mcp_servers,
            "templates_dir": self.templates_dir,
            "safety": self.safety.to_dict(),
            "bridge_dir": self.bridge_dir,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Config":
        d = d or {}
        return cls(
            provider=ProviderConfig.from_dict(d.get("provider", {})),
            theme=d.get("theme", {}),
            projects_roots=d.get("projects_roots", []),
            quarantine_dir=d.get("quarantine_dir", ""),
            mcp_servers=d.get("mcp_servers", []),
            templates_dir=d.get("templates_dir", ""),
            safety=SafetyConfig.from_dict(d.get("safety", {})),
            bridge_dir=d.get("bridge_dir", ""),
        )


def default_config() -> Config:
    return Config()


def load(path: Path | None = None) -> Config:
    path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if not path.exists():
        cfg = default_config()
        save(cfg, path)
        return cfg
    return Config.from_dict(read_json(path))


def save(cfg: Config, path: Path | None = None) -> None:
    path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    atomic_write_json(path, cfg.to_dict())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd companion && .venv/bin/python -m pytest tests/test_config.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
cd /home/bradzgar/projects/reamind
git add companion/reamind/config.py companion/tests/test_config.py
git commit -m "feat: config load/save with defaults"
```

---

### Task 5: Provider abstraction + FakeProvider (`providers/base.py`, `providers/fake.py`)

**Files:**
- Create: `companion/reamind/providers/__init__.py`
- Create: `companion/reamind/providers/base.py`
- Create: `companion/reamind/providers/fake.py`
- Test: `companion/tests/test_providers.py`

**Interfaces:**
- Consumes: stdlib only.
- Produces (in `base.py`):
  - `@dataclass ToolSpec`: `name: str`, `description: str`, `parameters: dict`, `executor: str` (`"reaper"` or `"local"`). Method `to_openai() -> dict` returns `{"type": "function", "function": {"name","description","parameters"}}`.
  - `@dataclass ToolCall`: `id: str`, `name: str`, `arguments: dict`.
  - `@dataclass Message`: `role: str`, `content: str = ""`, `tool_calls: list[ToolCall] | None = None`, `tool_call_id: str | None = None`, `name: str | None = None`.
  - `@dataclass ChatResult`: `text: str | None`, `tool_calls: list[ToolCall] = field(default_factory=list)`.
  - `class LLMProvider(abc.ABC)`: abstract `chat(self, messages: list[Message], tools: list[ToolSpec]) -> ChatResult`.
- Produces (in `fake.py`):
  - `class FakeProvider(LLMProvider)`: `__init__(self, scripted: list[ChatResult])`; `chat(...)` pops the next scripted result (FIFO) and records the `(messages, tools)` it was called with in `self.calls`. Raises `AssertionError` if called more times than scripted.

- [ ] **Step 1: Write the failing test**

Create `companion/tests/test_providers.py`:

```python
import pytest

from reamind.providers.base import ChatResult, Message, ToolCall, ToolSpec
from reamind.providers.fake import FakeProvider


def test_toolspec_to_openai_shape():
    spec = ToolSpec(
        name="list_tracks",
        description="List tracks",
        parameters={"type": "object", "properties": {}},
        executor="reaper",
    )
    d = spec.to_openai()
    assert d["type"] == "function"
    assert d["function"]["name"] == "list_tracks"
    assert d["function"]["parameters"] == {"type": "object", "properties": {}}


def test_fake_provider_returns_scripted_in_order():
    r1 = ChatResult(text=None, tool_calls=[ToolCall(id="c1", name="list_tracks", arguments={})])
    r2 = ChatResult(text="done", tool_calls=[])
    fp = FakeProvider([r1, r2])
    out1 = fp.chat([Message(role="user", content="hi")], [])
    out2 = fp.chat([Message(role="user", content="hi")], [])
    assert out1 is r1
    assert out2 is r2
    assert len(fp.calls) == 2


def test_fake_provider_raises_when_exhausted():
    fp = FakeProvider([])
    with pytest.raises(AssertionError):
        fp.chat([], [])
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd companion && .venv/bin/python -m pytest tests/test_providers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'reamind.providers'`.

- [ ] **Step 3: Write minimal implementation**

Create `companion/reamind/providers/__init__.py`:

```python
```

Create `companion/reamind/providers/base.py`:

```python
from __future__ import annotations

import abc
from dataclasses import dataclass, field


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict
    executor: str

    def to_openai(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class Message:
    role: str
    content: str = ""
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    name: str | None = None


@dataclass
class ChatResult:
    text: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMProvider(abc.ABC):
    @abc.abstractmethod
    def chat(self, messages: list[Message], tools: list[ToolSpec]) -> ChatResult:
        ...
```

Create `companion/reamind/providers/fake.py`:

```python
from __future__ import annotations

from .base import ChatResult, LLMProvider, Message, ToolSpec


class FakeProvider(LLMProvider):
    def __init__(self, scripted: list[ChatResult]) -> None:
        self._scripted = list(scripted)
        self._i = 0
        self.calls: list[tuple[list[Message], list[ToolSpec]]] = []

    def chat(self, messages: list[Message], tools: list[ToolSpec]) -> ChatResult:
        self.calls.append((list(messages), list(tools)))
        assert self._i < len(self._scripted), "FakeProvider exhausted"
        result = self._scripted[self._i]
        self._i += 1
        return result
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd companion && .venv/bin/python -m pytest tests/test_providers.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
cd /home/bradzgar/projects/reamind
git add companion/reamind/providers/ companion/tests/test_providers.py
git commit -m "feat: llm provider abstraction + fake provider"
```

---

### Task 6: LocalProvider + server detection (`providers/local.py`)

**Files:**
- Create: `companion/reamind/providers/local.py`
- Test: `companion/tests/test_local_provider.py`

**Interfaces:**
- Consumes: `reamind.providers.base` (`ChatResult`, `LLMProvider`, `Message`, `ToolCall`, `ToolSpec`), stdlib `urllib.request`, `json`.
- Produces:
  - `class LocalProvider(LLMProvider)`: `__init__(self, base_url: str, model: str, tool_mode: str = "native", timeout: float = 60.0)`.
    - `chat(...)` POSTs OpenAI-compatible `/v1/chat/completions` (base_url + `/v1/chat/completions`) with `messages` serialized via `messages_to_openai(...)` and `tools=[spec.to_openai() ...]` when tools present; parses the first choice into a `ChatResult`. Any `tool_calls` in the response become `ToolCall(id, name, arguments)` with `arguments` JSON-decoded from the string the API returns.
    - HTTP performed by module function `_post_json(url, payload, timeout, api_key=None) -> dict` (so tests can monkeypatch it).
  - `messages_to_openai(messages: list[Message]) -> list[dict]` — maps our `Message` to OpenAI wire dicts (assistant tool_calls → `{"id","type":"function","function":{"name","arguments":<json str>}}`; tool results → `{"role":"tool","tool_call_id","content"}`).
  - `detect_servers(probe=_probe) -> list[dict]` — returns entries `{"name": "ollama"|"lmstudio", "base_url": ...}` for reachable servers. Probing done by injectable `probe(base_url) -> bool`. Defaults: Ollama `http://localhost:11434`, LM Studio `http://localhost:1234`.
  - `list_models(base_url, fetch=_get_json) -> list[str]` — GET `base_url + "/v1/models"`, return `[m["id"] ...]`. `fetch` injectable.

- [ ] **Step 1: Write the failing test**

Create `companion/tests/test_local_provider.py`:

```python
from reamind.providers import local
from reamind.providers.base import Message, ToolSpec


def test_messages_to_openai_maps_roles_and_tool_calls():
    from reamind.providers.base import ToolCall

    msgs = [
        Message(role="system", content="sys"),
        Message(role="user", content="hi"),
        Message(
            role="assistant",
            content="",
            tool_calls=[ToolCall(id="c1", name="list_tracks", arguments={"a": 1})],
        ),
        Message(role="tool", content='{"ok": true}', tool_call_id="c1", name="list_tracks"),
    ]
    wire = local.messages_to_openai(msgs)
    assert wire[0] == {"role": "system", "content": "sys"}
    assert wire[2]["tool_calls"][0]["function"]["name"] == "list_tracks"
    assert wire[2]["tool_calls"][0]["function"]["arguments"] == '{"a": 1}'
    assert wire[3] == {"role": "tool", "tool_call_id": "c1", "content": '{"ok": true}'}


def test_chat_parses_text_response(monkeypatch):
    def fake_post(url, payload, timeout, api_key=None):
        assert url.endswith("/v1/chat/completions")
        return {"choices": [{"message": {"role": "assistant", "content": "hello there"}}]}

    monkeypatch.setattr(local, "_post_json", fake_post)
    p = local.LocalProvider(base_url="http://localhost:11434", model="m")
    res = p.chat([Message(role="user", content="hi")], [])
    assert res.text == "hello there"
    assert res.tool_calls == []


def test_chat_parses_tool_calls(monkeypatch):
    def fake_post(url, payload, timeout, api_key=None):
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "c9",
                                "type": "function",
                                "function": {"name": "list_tracks", "arguments": '{"x": 2}'},
                            }
                        ],
                    }
                }
            ]
        }

    monkeypatch.setattr(local, "_post_json", fake_post)
    p = local.LocalProvider(base_url="http://localhost:11434", model="m")
    spec = ToolSpec("list_tracks", "d", {"type": "object", "properties": {}}, "reaper")
    res = p.chat([Message(role="user", content="hi")], [spec])
    assert res.text is None
    assert len(res.tool_calls) == 1
    assert res.tool_calls[0].id == "c9"
    assert res.tool_calls[0].name == "list_tracks"
    assert res.tool_calls[0].arguments == {"x": 2}


def test_detect_servers_uses_injected_probe():
    reachable = {"http://localhost:11434"}
    found = local.detect_servers(probe=lambda url: url in reachable)
    names = {f["name"] for f in found}
    assert names == {"ollama"}


def test_list_models_extracts_ids():
    def fake_get(url):
        assert url.endswith("/v1/models")
        return {"data": [{"id": "qwen2.5:7b"}, {"id": "llama3.1:8b"}]}

    ids = local.list_models("http://localhost:11434", fetch=fake_get)
    assert ids == ["qwen2.5:7b", "llama3.1:8b"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd companion && .venv/bin/python -m pytest tests/test_local_provider.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'reamind.providers.local'`.

- [ ] **Step 3: Write minimal implementation**

Create `companion/reamind/providers/local.py`:

```python
from __future__ import annotations

import json
import urllib.error
import urllib.request

from .base import ChatResult, LLMProvider, Message, ToolCall, ToolSpec

OLLAMA_URL = "http://localhost:11434"
LMSTUDIO_URL = "http://localhost:1234"


def _post_json(url: str, payload: dict, timeout: float, api_key: str | None = None) -> dict:
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_json(url: str, timeout: float = 5.0) -> dict:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _probe(base_url: str, timeout: float = 1.5) -> bool:
    try:
        _get_json(base_url + "/v1/models", timeout=timeout)
        return True
    except (urllib.error.URLError, OSError, ValueError):
        return False


def messages_to_openai(messages: list[Message]) -> list[dict]:
    wire: list[dict] = []
    for m in messages:
        if m.role == "assistant" and m.tool_calls:
            wire.append(
                {
                    "role": "assistant",
                    "content": m.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments),
                            },
                        }
                        for tc in m.tool_calls
                    ],
                }
            )
        elif m.role == "tool":
            wire.append(
                {"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content}
            )
        else:
            wire.append({"role": m.role, "content": m.content})
    return wire


class LocalProvider(LLMProvider):
    def __init__(
        self,
        base_url: str,
        model: str,
        tool_mode: str = "native",
        timeout: float = 60.0,
        api_key: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.tool_mode = tool_mode
        self.timeout = timeout
        self.api_key = api_key

    def chat(self, messages: list[Message], tools: list[ToolSpec]) -> ChatResult:
        payload: dict = {
            "model": self.model,
            "messages": messages_to_openai(messages),
            "stream": False,
        }
        if tools:
            payload["tools"] = [t.to_openai() for t in tools]
        url = self.base_url + "/v1/chat/completions"
        resp = _post_json(url, payload, self.timeout, api_key=self.api_key)
        msg = resp["choices"][0]["message"]
        raw_calls = msg.get("tool_calls") or []
        tool_calls: list[ToolCall] = []
        for rc in raw_calls:
            fn = rc.get("function", {})
            args_raw = fn.get("arguments") or "{}"
            try:
                args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
            except ValueError:
                args = {}
            tool_calls.append(ToolCall(id=rc.get("id", ""), name=fn.get("name", ""), arguments=args))
        text = msg.get("content")
        return ChatResult(text=text, tool_calls=tool_calls)


def detect_servers(probe=_probe) -> list[dict]:
    candidates = [("ollama", OLLAMA_URL), ("lmstudio", LMSTUDIO_URL)]
    return [{"name": name, "base_url": url} for name, url in candidates if probe(url)]


def list_models(base_url: str, fetch=_get_json) -> list[str]:
    data = fetch(base_url.rstrip("/") + "/v1/models")
    return [m["id"] for m in data.get("data", [])]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd companion && .venv/bin/python -m pytest tests/test_local_provider.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
cd /home/bradzgar/projects/reamind
git add companion/reamind/providers/local.py companion/tests/test_local_provider.py
git commit -m "feat: local (openai-compatible) provider + server detection"
```

---

### Task 7: Tool registry + read-only REAPER tool specs (`tools/registry.py`, `tools/reaper_readonly.py`)

**Files:**
- Create: `companion/reamind/tools/__init__.py`
- Create: `companion/reamind/tools/registry.py`
- Create: `companion/reamind/tools/reaper_readonly.py`
- Test: `companion/tests/test_registry.py`

**Interfaces:**
- Consumes: `reamind.providers.base.ToolSpec`.
- Produces (in `registry.py`):
  - `class ToolRegistry`: `register(spec: ToolSpec) -> None`; `get(name: str) -> ToolSpec` (raises `KeyError`); `specs() -> list[ToolSpec]`; `validate_args(name: str, args: dict) -> None` — checks all keys in the spec's `parameters["required"]` are present, else raises `ValueError`.
- Produces (in `reaper_readonly.py`):
  - `READONLY_TOOLS: list[ToolSpec]` — three specs (`get_project_summary`, `list_tracks`, `get_track`), all `executor="reaper"`. `get_track` requires `track_guid` (string).
  - `build_registry() -> ToolRegistry` — a registry with the read-only tools registered.

- [ ] **Step 1: Write the failing test**

Create `companion/tests/test_registry.py`:

```python
import pytest

from reamind.providers.base import ToolSpec
from reamind.tools.reaper_readonly import READONLY_TOOLS, build_registry
from reamind.tools.registry import ToolRegistry


def test_register_and_get():
    reg = ToolRegistry()
    spec = ToolSpec("t", "d", {"type": "object", "properties": {}}, "reaper")
    reg.register(spec)
    assert reg.get("t") is spec


def test_get_unknown_raises():
    reg = ToolRegistry()
    with pytest.raises(KeyError):
        reg.get("nope")


def test_validate_args_requires_required_keys():
    reg = ToolRegistry()
    reg.register(
        ToolSpec(
            "get_track",
            "d",
            {"type": "object", "properties": {"track_guid": {"type": "string"}}, "required": ["track_guid"]},
            "reaper",
        )
    )
    reg.validate_args("get_track", {"track_guid": "{ABC}"})
    with pytest.raises(ValueError):
        reg.validate_args("get_track", {})


def test_build_registry_has_three_readonly_tools():
    reg = build_registry()
    names = {s.name for s in reg.specs()}
    assert names == {"get_project_summary", "list_tracks", "get_track"}
    assert all(s.executor == "reaper" for s in READONLY_TOOLS)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd companion && .venv/bin/python -m pytest tests/test_registry.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'reamind.tools'`.

- [ ] **Step 3: Write minimal implementation**

Create `companion/reamind/tools/__init__.py`:

```python
```

Create `companion/reamind/tools/registry.py`:

```python
from __future__ import annotations

from ..providers.base import ToolSpec


class ToolRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        self._specs[spec.name] = spec

    def get(self, name: str) -> ToolSpec:
        return self._specs[name]

    def specs(self) -> list[ToolSpec]:
        return list(self._specs.values())

    def validate_args(self, name: str, args: dict) -> None:
        spec = self.get(name)
        required = spec.parameters.get("required", [])
        missing = [k for k in required if k not in (args or {})]
        if missing:
            raise ValueError(f"{name}: missing required args: {missing}")
```

Create `companion/reamind/tools/reaper_readonly.py`:

```python
from __future__ import annotations

from ..providers.base import ToolSpec
from .registry import ToolRegistry

READONLY_TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="get_project_summary",
        description="Return a summary of the current REAPER project: track count, tempo, sample rate, and the current selection.",
        parameters={"type": "object", "properties": {}, "required": []},
        executor="reaper",
    ),
    ToolSpec(
        name="list_tracks",
        description="List all tracks with index, name, GUID, color, parent/folder depth, FX names, and sends/receives.",
        parameters={"type": "object", "properties": {}, "required": []},
        executor="reaper",
    ),
    ToolSpec(
        name="get_track",
        description="Return detailed info for one track, addressed by its GUID.",
        parameters={
            "type": "object",
            "properties": {
                "track_guid": {"type": "string", "description": "The track GUID, e.g. {AB12...}"}
            },
            "required": ["track_guid"],
        },
        executor="reaper",
    ),
]


def build_registry() -> ToolRegistry:
    reg = ToolRegistry()
    for spec in READONLY_TOOLS:
        reg.register(spec)
    return reg
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd companion && .venv/bin/python -m pytest tests/test_registry.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
cd /home/bradzgar/projects/reamind
git add companion/reamind/tools/ companion/tests/test_registry.py
git commit -m "feat: tool registry + read-only reaper tool specs"
```

---

### Task 8: Agent loop (`agent.py`)

**Files:**
- Create: `companion/reamind/agent.py`
- Test: `companion/tests/test_agent.py`

**Interfaces:**
- Consumes: `reamind.providers.base` (`ChatResult`, `LLMProvider`, `Message`, `ToolCall`, `ToolSpec`), `reamind.tools.registry.ToolRegistry`.
- Produces:
  - `run_turn(provider: LLMProvider, registry: ToolRegistry, messages: list[Message], reaper_executor: Callable[[ToolCall], dict], on_text: Callable[[str], None], max_iterations: int = 8) -> list[Message]`
    - Appends provider responses/tool results to `messages` (returned).
    - Each iteration: `result = provider.chat(messages, registry.specs())`.
      - If `result.tool_calls`: append an assistant Message carrying the tool_calls; for each call, route by executor tag — `"reaper"` calls go to `reaper_executor(call)` (returns a result dict), `"local"` (none yet) → error result dict `{"ok": False, "error": "no local executor"}`. On unknown tool name or failed `registry.validate_args`, produce `{"ok": False, "error": ...}` WITHOUT calling the executor. Append a `role="tool"` Message per call with `content=json.dumps(result_dict)` and matching `tool_call_id`. Continue loop.
      - Else (text): call `on_text(result.text or "")`, append assistant text Message, and return `messages`.
    - If `max_iterations` reached with tool calls still pending, append a final assistant Message `content="Stopped: reached max tool iterations."`, call `on_text(...)` with it, and return.

- [ ] **Step 1: Write the failing test**

Create `companion/tests/test_agent.py`:

```python
import json

from reamind.agent import run_turn
from reamind.providers.base import ChatResult, Message, ToolCall
from reamind.providers.fake import FakeProvider
from reamind.tools.reaper_readonly import build_registry


def test_text_only_turn_calls_on_text_and_returns():
    provider = FakeProvider([ChatResult(text="hello", tool_calls=[])])
    texts = []
    msgs = run_turn(
        provider,
        build_registry(),
        [Message(role="user", content="hi")],
        reaper_executor=lambda call: {"ok": True, "result": {}},
        on_text=texts.append,
    )
    assert texts == ["hello"]
    assert msgs[-1].role == "assistant"
    assert msgs[-1].content == "hello"


def test_reaper_tool_call_is_routed_to_executor_then_finishes():
    provider = FakeProvider(
        [
            ChatResult(text=None, tool_calls=[ToolCall(id="c1", name="list_tracks", arguments={})]),
            ChatResult(text="you have 3 tracks", tool_calls=[]),
        ]
    )
    seen = []

    def executor(call: ToolCall) -> dict:
        seen.append(call.name)
        return {"ok": True, "result": {"tracks": []}}

    texts = []
    msgs = run_turn(provider, build_registry(), [Message(role="user", content="list")], executor, texts.append)
    assert seen == ["list_tracks"]
    assert texts == ["you have 3 tracks"]
    tool_msgs = [m for m in msgs if m.role == "tool"]
    assert tool_msgs[0].tool_call_id == "c1"
    assert json.loads(tool_msgs[0].content) == {"ok": True, "result": {"tracks": []}}


def test_unknown_tool_does_not_call_executor():
    provider = FakeProvider(
        [
            ChatResult(text=None, tool_calls=[ToolCall(id="c1", name="bogus", arguments={})]),
            ChatResult(text="ok", tool_calls=[]),
        ]
    )
    calls = []
    run_turn(provider, build_registry(), [Message(role="user", content="x")], lambda c: calls.append(c) or {}, lambda t: None)
    assert calls == []


def test_missing_required_arg_errors_without_executor():
    provider = FakeProvider(
        [
            ChatResult(text=None, tool_calls=[ToolCall(id="c1", name="get_track", arguments={})]),
            ChatResult(text="done", tool_calls=[]),
        ]
    )
    calls = []
    msgs = run_turn(provider, build_registry(), [Message(role="user", content="x")], lambda c: calls.append(c) or {}, lambda t: None)
    assert calls == []
    tool_msg = [m for m in msgs if m.role == "tool"][0]
    assert json.loads(tool_msg.content)["ok"] is False


def test_max_iterations_guard():
    loop = [ChatResult(text=None, tool_calls=[ToolCall(id="c", name="list_tracks", arguments={})]) for _ in range(10)]
    provider = FakeProvider(loop)
    texts = []
    run_turn(
        provider,
        build_registry(),
        [Message(role="user", content="x")],
        lambda c: {"ok": True, "result": {}},
        texts.append,
        max_iterations=3,
    )
    assert texts and "max tool iterations" in texts[-1]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd companion && .venv/bin/python -m pytest tests/test_agent.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'reamind.agent'`.

- [ ] **Step 3: Write minimal implementation**

Create `companion/reamind/agent.py`:

```python
from __future__ import annotations

import json
from typing import Callable

from .providers.base import LLMProvider, Message, ToolCall
from .tools.registry import ToolRegistry


def run_turn(
    provider: LLMProvider,
    registry: ToolRegistry,
    messages: list[Message],
    reaper_executor: Callable[[ToolCall], dict],
    on_text: Callable[[str], None],
    max_iterations: int = 8,
) -> list[Message]:
    for _ in range(max_iterations):
        result = provider.chat(messages, registry.specs())
        if not result.tool_calls:
            text = result.text or ""
            on_text(text)
            messages.append(Message(role="assistant", content=text))
            return messages

        messages.append(Message(role="assistant", content=result.text or "", tool_calls=result.tool_calls))
        for call in result.tool_calls:
            out = _execute_call(registry, call, reaper_executor)
            messages.append(
                Message(
                    role="tool",
                    content=json.dumps(out),
                    tool_call_id=call.id,
                    name=call.name,
                )
            )

    stop = "Stopped: reached max tool iterations."
    on_text(stop)
    messages.append(Message(role="assistant", content=stop))
    return messages


def _execute_call(registry: ToolRegistry, call: ToolCall, reaper_executor: Callable[[ToolCall], dict]) -> dict:
    try:
        spec = registry.get(call.name)
    except KeyError:
        return {"ok": False, "error": f"unknown tool: {call.name}"}
    try:
        registry.validate_args(call.name, call.arguments)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    if spec.executor == "reaper":
        return reaper_executor(call)
    return {"ok": False, "error": f"no executor for tag: {spec.executor}"}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd companion && .venv/bin/python -m pytest tests/test_agent.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
cd /home/bradzgar/projects/reamind
git add companion/reamind/agent.py companion/tests/test_agent.py
git commit -m "feat: agent loop with tool routing and guards"
```

---

### Task 9: Server entrypoint (`server.py`)

**Files:**
- Create: `companion/reamind/server.py`
- Test: `companion/tests/test_server.py`

**Interfaces:**
- Consumes: `reamind.bridge.Bridge`, `reamind.config` (`Config`, `load`), `reamind.agent.run_turn`, `reamind.tools.reaper_readonly.build_registry`, `reamind.providers.base` (`LLMProvider`, `Message`, `ToolCall`), `reamind.providers.local.LocalProvider`.
- Produces:
  - `SYSTEM_PROMPT: str` — a short constant describing the REAPER assistant role, GUID addressing convention, and "propose a plan before multi-step/destructive work".
  - `class Server`:
    - `__init__(self, config: Config, provider: LLMProvider, bridge: Bridge)` — stores them; `self.registry = build_registry()`; `self.history: list[Message] = [Message(role="system", content=SYSTEM_PROMPT)]`; `self._req_seq = 0`.
    - `make_reaper_executor(self, poll_interval: float = 0.05, now=time.monotonic, sleep=time.sleep) -> Callable[[ToolCall], dict]` — returns a function that: increments `self._req_seq`, calls `bridge.send_request(call.name, call.arguments, seq)`, polls `bridge.read_result(id)` until non-None or `config.safety.tool_timeout_s` elapsed; returns the result dict, or `{"ok": False, "error": "tool timed out"}`.
    - `handle_user_message(self, text: str) -> None` — append user Message; `run_turn(provider, registry, history, executor, on_text=lambda t: bridge.push_chat("assistant", t, done=True), max_iterations=config.safety.max_tool_iterations)`.
    - `tick(self) -> None` — `for msg in bridge.drain_inbox(): self.handle_user_message(msg["text"])`; then `bridge.write_heartbeat(os.getpid())`.
    - `run(self, stop: Callable[[], bool] | None = None, sleep=time.sleep, interval: float = 0.1) -> None` — `bridge.clear_stale(); bridge.write_session(...)`; loop `tick()` + sleep until `stop()` true.
  - `build_provider(config: Config) -> LLMProvider` — construct a `LocalProvider` from config (auto-detect a server + first model if config lacks them; raise `RuntimeError` with a friendly message if none found).
  - `main(argv: list[str] | None = None) -> int` — argparse `--bridge DIR` (default: config.bridge_dir or `<repo>/bridge`), `--config PATH`; wires `load`, `build_provider`, `Bridge`, `Server().run()`.

- [ ] **Step 1: Write the failing test**

Create `companion/tests/test_server.py`:

```python
import threading

from reamind.bridge import Bridge
from reamind.config import default_config
from reamind.providers.base import ChatResult, Message, ToolCall
from reamind.providers.fake import FakeProvider
from reamind.server import Server


def test_reaper_executor_roundtrips_via_bridge(tmp_path):
    bridge = Bridge(tmp_path / "b")
    bridge.ensure_dirs()
    server = Server(default_config(), FakeProvider([]), bridge)
    executor = server.make_reaper_executor(poll_interval=0.001)

    call = ToolCall(id="", name="list_tracks", arguments={})

    def responder():
        import time

        from reamind.jsonio import atomic_write_json, read_json

        for _ in range(1000):
            reqs = list(bridge.requests.glob("*.json"))
            if reqs:
                data = read_json(reqs[0])
                atomic_write_json(
                    bridge.results / f"{data['id']}.json",
                    {"id": data["id"], "ok": True, "result": {"tracks": []}},
                )
                return
            time.sleep(0.001)

    t = threading.Thread(target=responder)
    t.start()
    out = executor(call)
    t.join()
    assert out == {"id": out["id"], "ok": True, "result": {"tracks": []}}


def test_reaper_executor_times_out(tmp_path):
    bridge = Bridge(tmp_path / "b")
    bridge.ensure_dirs()
    cfg = default_config()
    cfg.safety.tool_timeout_s = 0.05
    server = Server(cfg, FakeProvider([]), bridge)
    executor = server.make_reaper_executor(poll_interval=0.001)
    out = executor(ToolCall(id="", name="list_tracks", arguments={}))
    assert out["ok"] is False
    assert "timed out" in out["error"]


def test_handle_user_message_pushes_assistant_chat(tmp_path):
    bridge = Bridge(tmp_path / "b")
    bridge.ensure_dirs()
    provider = FakeProvider([ChatResult(text="hi back", tool_calls=[])])
    server = Server(default_config(), provider, bridge)
    server.handle_user_message("hello")
    chats = sorted(bridge.chat.glob("*.json"))
    from reamind.jsonio import read_json

    payloads = [read_json(f) for f in chats]
    assert any(p["role"] == "assistant" and p["text"] == "hi back" for p in payloads)


def test_tick_drains_inbox(tmp_path):
    bridge = Bridge(tmp_path / "b")
    bridge.ensure_dirs()
    from reamind.jsonio import atomic_write_json

    atomic_write_json(bridge.inbox / "000000001.json", {"seq": 1, "text": "yo"})
    provider = FakeProvider([ChatResult(text="reply", tool_calls=[])])
    server = Server(default_config(), provider, bridge)
    server.tick()
    assert list(bridge.inbox.glob("*.json")) == []
    assert bridge.heartbeat.exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd companion && .venv/bin/python -m pytest tests/test_server.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'reamind.server'`.

- [ ] **Step 3: Write minimal implementation**

Create `companion/reamind/server.py`:

```python
from __future__ import annotations

import argparse
import os
import time
import uuid
from pathlib import Path
from typing import Callable

from .agent import run_turn
from .bridge import Bridge
from .config import Config, load
from .providers.base import LLMProvider, Message, ToolCall
from .providers.local import LocalProvider, detect_servers, list_models
from .tools.reaper_readonly import build_registry

SYSTEM_PROMPT = (
    "You are ReaMind, an assistant embedded in the REAPER digital audio workstation. "
    "You help build sessions, route tracks, and inspect projects by calling tools. "
    "Always address tracks by their GUID, never by bare index. "
    "For multi-step or destructive work, briefly propose a plan before acting."
)


class Server:
    def __init__(self, config: Config, provider: LLMProvider, bridge: Bridge) -> None:
        self.config = config
        self.provider = provider
        self.bridge = bridge
        self.registry = build_registry()
        self.history: list[Message] = [Message(role="system", content=SYSTEM_PROMPT)]
        self._req_seq = 0

    def make_reaper_executor(
        self,
        poll_interval: float = 0.05,
        now: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> Callable[[ToolCall], dict]:
        def executor(call: ToolCall) -> dict:
            self._req_seq += 1
            call_id = self.bridge.send_request(call.name, call.arguments, self._req_seq)
            deadline = now() + self.config.safety.tool_timeout_s
            while now() < deadline:
                result = self.bridge.read_result(call_id)
                if result is not None:
                    return result
                sleep(poll_interval)
            return {"ok": False, "error": "tool timed out"}

        return executor

    def handle_user_message(self, text: str) -> None:
        self.history.append(Message(role="user", content=text))
        executor = self.make_reaper_executor()
        run_turn(
            self.provider,
            self.registry,
            self.history,
            executor,
            on_text=lambda t: self.bridge.push_chat("assistant", t, done=True),
            max_iterations=self.config.safety.max_tool_iterations,
        )

    def tick(self) -> None:
        for msg in self.bridge.drain_inbox():
            self.handle_user_message(msg.get("text", ""))
        self.bridge.write_heartbeat(os.getpid())

    def run(
        self,
        stop: Callable[[], bool] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        interval: float = 0.1,
    ) -> None:
        self.bridge.clear_stale()
        self.bridge.write_session(uuid.uuid4().hex)
        stop = stop or (lambda: False)
        while not stop():
            self.tick()
            sleep(interval)


def build_provider(config: Config) -> LLMProvider:
    p = config.provider
    base_url = p.base_url
    model = p.model
    if not base_url:
        servers = detect_servers()
        if not servers:
            raise RuntimeError(
                "No local model server found. Start Ollama (:11434) or LM Studio (:1234), "
                "or set provider.base_url in the config."
            )
        base_url = servers[0]["base_url"]
    if not model:
        models = list_models(base_url)
        if not models:
            raise RuntimeError(
                f"No models available at {base_url}. Pull a tool-capable model "
                "(e.g. `ollama pull qwen2.5:7b`)."
            )
        model = models[0]
    tool_mode = "native" if p.tool_mode == "auto" else p.tool_mode
    return LocalProvider(base_url=base_url, model=model, tool_mode=tool_mode, api_key=p.api_key)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="reamind.server")
    parser.add_argument("--bridge", default=None)
    parser.add_argument("--config", default=None)
    args = parser.parse_args(argv)

    config = load(Path(args.config) if args.config else None)
    bridge_dir = args.bridge or config.bridge_dir or str(Path(__file__).resolve().parents[2] / "bridge")
    bridge = Bridge(Path(bridge_dir))
    provider = build_provider(config)
    Server(config, provider, bridge).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd companion && .venv/bin/python -m pytest tests/test_server.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Run the full companion suite**

Run: `cd companion && .venv/bin/python -m pytest -v`
Expected: PASS (all tests from Tasks 1–9).

- [ ] **Step 6: Commit**

```bash
cd /home/bradzgar/projects/reamind
git add companion/reamind/server.py companion/tests/test_server.py
git commit -m "feat: companion server entrypoint and main loop"
```

---

### Task 10: Lua JSON + IPC + pure helpers with tests

**Files:**
- Create: `panel/json.lua` (vendored pure-Lua JSON — use the public-domain `rxi/json.lua`, single file)
- Create: `panel/helpers.lua`
- Create: `panel/ipc.lua`
- Create: `panel/test/run.lua`
- Create: `panel/test/json_spec.lua`
- Create: `panel/test/helpers_spec.lua`

**Interfaces:**
- `panel/json.lua` returns a table with `json.encode(value) -> string` and `json.decode(string) -> value` (rxi/json.lua API).
- `panel/helpers.lua` returns a table:
  - `helpers.seq_name(n: integer) -> string` — zero-padded `%09d.json` (matches companion filenames).
  - `helpers.hex_to_native_color(hex: string) -> integer` — `"#RRGGBB"` → REAPER native color int via `(r) | (g<<8) | (b<<16)` (pure arithmetic; no reaper API). Returns `nil` for malformed input.
  - `helpers.coerce_args(schema_props: table, args: table) -> table` — for each key whose schema type is `"integer"`, convert numeric strings to numbers; passthrough otherwise.
- `panel/ipc.lua` returns a table with functions that take a `bridge_root` string:
  - `ipc.write_json_atomic(path, tbl)` — encode + write to `path .. ".tmp"` then `os.rename`.
  - `ipc.read_json(path) -> table|nil` — read+decode, or nil if missing/invalid.
  - `ipc.push_inbox(bridge_root, seq, text)` — write `inbox/<seq_name>.json` = `{seq=seq, text=text}`.
  - `ipc.write_result(bridge_root, id, ok, payload)` — write `results/<id>.json` = `{id=id, ok=ok, result=payload}` (or `error=payload` when `ok==false`).
  - (Directory *listing* is NOT in ipc.lua — it needs the reaper API and lives in `reamind_panel.lua`.)

- [ ] **Step 1: Write the failing test**

Create `panel/test/run.lua` (zero-dependency assert runner):

```lua
local M = { passed = 0, failed = 0 }

function M.eq(a, b, msg)
  if a ~= b then
    M.failed = M.failed + 1
    print(string.format("FAIL: %s (got %s, want %s)", msg or "", tostring(a), tostring(b)))
  else
    M.passed = M.passed + 1
  end
end

function M.truthy(v, msg)
  if not v then
    M.failed = M.failed + 1
    print(string.format("FAIL: %s (got falsy)", msg or ""))
  else
    M.passed = M.passed + 1
  end
end

function M.finish()
  print(string.format("passed=%d failed=%d", M.passed, M.failed))
  if M.failed > 0 then os.exit(1) end
end

return M
```

Create `panel/test/json_spec.lua`:

```lua
package.path = "./?.lua;" .. package.path
local t = require("test.run")
local json = require("json")

local encoded = json.encode({ a = 1, b = { 2, 3 } })
local decoded = json.decode(encoded)
t.eq(decoded.a, 1, "json roundtrip a")
t.eq(decoded.b[1], 2, "json roundtrip b[1]")
t.eq(decoded.b[2], 3, "json roundtrip b[2]")

local obj = json.decode('{"id":"call_1","ok":true}')
t.eq(obj.id, "call_1", "decode id")
t.eq(obj.ok, true, "decode ok")

t.finish()
```

Create `panel/test/helpers_spec.lua`:

```lua
package.path = "./?.lua;" .. package.path
local t = require("test.run")
local h = require("helpers")

t.eq(h.seq_name(1), "000000001.json", "seq_name pads")
t.eq(h.seq_name(42), "000000042.json", "seq_name pads 42")

t.eq(h.hex_to_native_color("#FF0000"), 255, "red -> 255")
t.eq(h.hex_to_native_color("#00FF00"), 65280, "green -> 65280")
t.eq(h.hex_to_native_color("#0000FF"), 16711680, "blue -> 16711680")
t.eq(h.hex_to_native_color("bad"), nil, "malformed -> nil")

local coerced = h.coerce_args({ n = { type = "integer" } }, { n = "5", s = "x" })
t.eq(coerced.n, 5, "integer string coerced")
t.eq(coerced.s, "x", "string passthrough")

t.finish()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd panel && lua test/json_spec.lua; lua test/helpers_spec.lua`
Expected: FAIL — `module 'json' not found` / `module 'helpers' not found`.

- [ ] **Step 3: Add json.lua and write helpers.lua + ipc.lua**

Fetch the vendored JSON library (public domain, single file):

```bash
cd /home/bradzgar/projects/reamind/panel
curl -fsSL https://raw.githubusercontent.com/rxi/json.lua/master/json.lua -o json.lua
```

If offline, create `panel/json.lua` with a minimal encoder/decoder implementing `json.encode`/`json.decode` for the shapes used here (objects, arrays, strings, numbers, booleans, null). (rxi/json.lua is ~280 lines; reproduce it or use any MIT/public-domain pure-Lua JSON. The tests in Step 1 define the required behavior.)

Create `panel/helpers.lua`:

```lua
local M = {}

function M.seq_name(n)
  return string.format("%09d.json", n)
end

function M.hex_to_native_color(hex)
  if type(hex) ~= "string" then return nil end
  local r, g, b = hex:match("^#(%x%x)(%x%x)(%x%x)$")
  if not r then return nil end
  r = tonumber(r, 16)
  g = tonumber(g, 16)
  b = tonumber(b, 16)
  return r | (g << 8) | (b << 16)
end

function M.coerce_args(schema_props, args)
  local out = {}
  for k, v in pairs(args or {}) do
    local prop = schema_props and schema_props[k]
    if prop and prop.type == "integer" and type(v) == "string" then
      out[k] = tonumber(v) or v
    else
      out[k] = v
    end
  end
  return out
end

return M
```

Create `panel/ipc.lua`:

```lua
local json = require("json")
local helpers = require("helpers")

local M = {}

function M.write_json_atomic(path, tbl)
  local tmp = path .. ".tmp"
  local f = assert(io.open(tmp, "w"))
  f:write(json.encode(tbl))
  f:close()
  os.rename(tmp, path)
end

function M.read_json(path)
  local f = io.open(path, "r")
  if not f then return nil end
  local data = f:read("*a")
  f:close()
  local ok, decoded = pcall(json.decode, data)
  if not ok then return nil end
  return decoded
end

function M.push_inbox(bridge_root, seq, text)
  local path = bridge_root .. "/inbox/" .. helpers.seq_name(seq)
  M.write_json_atomic(path, { seq = seq, text = text })
end

function M.write_result(bridge_root, id, ok, payload)
  local out = { id = id, ok = ok }
  if ok then out.result = payload else out.error = payload end
  M.write_json_atomic(bridge_root .. "/results/" .. id .. ".json", out)
end

return M
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd panel && lua test/json_spec.lua && lua test/helpers_spec.lua`
Expected: both print `failed=0` and exit 0.

- [ ] **Step 5: Commit**

```bash
cd /home/bradzgar/projects/reamind
git add panel/json.lua panel/helpers.lua panel/ipc.lua panel/test/
git commit -m "feat: lua json, ipc helpers, and pure-helper tests"
```

---

### Task 11: Lua read-only REAPER tool implementations (`panel/tools/readonly.lua`)

**Files:**
- Create: `panel/tools/readonly.lua`

**Interfaces:**
- `panel/tools/readonly.lua` returns a table mapping tool name → function `(args) -> ok(boolean), result_or_error`:
  - `["get_project_summary"](args)` → `true, { track_count, tempo, sample_rate, selected_track_count }`.
  - `["list_tracks"](args)` → `true, { tracks = { {index, name, guid, color, folder_depth, fx = {names...}}, ... } }`.
  - `["get_track"](args)` → uses `args.track_guid`; finds the track via `reaper.BR_GetMediaTrackByGUID` (SWS, installed) or by scanning `GetTrackGUID`; returns `true, {index, name, guid, color, folder_depth, fx}` or `false, "track not found"`.
- These call the ReaScript API and are only runnable inside REAPER; they are exercised via the panel `selftest` action (Task 13), not unit tests.

- [ ] **Step 1: Write the implementation**

Create `panel/tools/readonly.lua`:

```lua
local M = {}

local function track_guid(tr)
  return reaper.GetTrackGUID(tr)
end

local function track_fx_names(tr)
  local names = {}
  local count = reaper.TrackFX_GetCount(tr)
  for i = 0, count - 1 do
    local _, name = reaper.TrackFX_GetFXName(tr, i, "")
    names[#names + 1] = name
  end
  return names
end

local function track_info(tr, index)
  local _, name = reaper.GetTrackName(tr)
  local color = reaper.GetTrackColor(tr)
  local depth = reaper.GetMediaTrackInfo_Value(tr, "I_FOLDERDEPTH")
  return {
    index = index,
    name = name,
    guid = track_guid(tr),
    color = color,
    folder_depth = depth,
    fx = track_fx_names(tr),
  }
end

function M.get_project_summary(args)
  local track_count = reaper.CountTracks(0)
  local tempo = reaper.Master_GetTempo()
  local sample_rate = reaper.GetSetProjectInfo(0, "PROJECT_SRATE", 0, false)
  local selected = reaper.CountSelectedTracks(0)
  return true, {
    track_count = track_count,
    tempo = tempo,
    sample_rate = sample_rate,
    selected_track_count = selected,
  }
end

function M.list_tracks(args)
  local tracks = {}
  local count = reaper.CountTracks(0)
  for i = 0, count - 1 do
    local tr = reaper.GetTrack(0, i)
    tracks[#tracks + 1] = track_info(tr, i)
  end
  return true, { tracks = tracks }
end

function M.get_track(args)
  local guid = args and args.track_guid
  if not guid then return false, "missing track_guid" end
  local count = reaper.CountTracks(0)
  for i = 0, count - 1 do
    local tr = reaper.GetTrack(0, i)
    if reaper.GetTrackGUID(tr) == guid then
      return true, track_info(tr, i)
    end
  end
  return false, "track not found"
end

return M
```

- [ ] **Step 2: Syntax-check with standalone lua**

Because this file references the `reaper` global (only present inside REAPER), verify it *parses* without executing:

Run: `cd panel && luac -p tools/readonly.lua 2>/dev/null || lua -e "assert(loadfile('tools/readonly.lua'))" && echo "parse ok"`
Expected: prints `parse ok` (compiles/loads without syntax error).

- [ ] **Step 3: Commit**

```bash
cd /home/bradzgar/projects/reamind
git add panel/tools/readonly.lua
git commit -m "feat: lua read-only reaper tool implementations"
```

---

### Task 12: Panel UI + defer loop + companion launch (`panel/reamind_panel.lua`)

**Files:**
- Create: `panel/reamind_panel.lua`

**Interfaces:**
- Consumes: `ipc.lua`, `helpers.lua`, `json.lua`, `tools/readonly.lua`, the ReaImGui API (`reaper.ImGui_*`), and `reaper.ExecProcess`, `reaper.EnumerateFiles`, `reaper.Undo_BeginBlock/EndBlock`.
- Produces the runnable panel script (loaded as a REAPER Action). Behavior:
  - On first run: resolve `SCRIPT_DIR` (from `debug.getinfo`), set `BRIDGE_ROOT = SCRIPT_DIR/../bridge`, ensure bridge subdirs exist (create via writing/removing a probe file per dir, or via `reaper.RecursiveCreateDirectory`), launch companion once with `reaper.ExecProcess` running `python -m reamind.server --bridge <BRIDGE_ROOT>` from the `companion/.venv` interpreter (path: `SCRIPT_DIR/../companion/.venv/bin/python`), non-blocking (prefix timeout 0 / background form).
  - Each defer frame:
    1. Drain `chat/` via `reaper.EnumerateFiles`, decode with `ipc.read_json`, append to an in-memory `messages` list (dedupe by seq), delete the file.
    2. Poll `requests/` via `EnumerateFiles`; for each new `id` not in `processed_ids`: decode; look up the tool in `tools/readonly.lua`; wrap in `reaper.Undo_BeginBlock()` / `reaper.Undo_EndBlock(tool.." (ReaMind)", -1)`; call it with `helpers.coerce_args`; write `results/<id>.json` via `ipc.write_result`; mark id processed; delete the request file.
    3. Render the ReaImGui window: scrolling transcript of `messages`, a text input + Send button that on submit calls `ipc.push_inbox(BRIDGE_ROOT, inbox_seq, text)` and increments `inbox_seq`.
    4. Heartbeat check: if `heartbeat.json` is older than N seconds, show a "companion not responding — Restart" button that re-launches the companion.
  - Uses `reaper.defer` to reschedule.

- [ ] **Step 1: Write the panel script**

Create `panel/reamind_panel.lua`:

```lua
local SCRIPT_DIR = ({reaper.get_action_context()})[2]:match("^(.*[/\\])")
package.path = SCRIPT_DIR .. "?.lua;" .. package.path

local ipc = require("ipc")
local helpers = require("helpers")
local tools = require("tools.readonly")

local BRIDGE_ROOT = SCRIPT_DIR .. "../bridge"
local COMPANION_PY = SCRIPT_DIR .. "../companion/.venv/bin/python"

local ctx = reaper.ImGui_CreateContext("ReaMind")
local messages = {}
local seen_chat = {}
local processed_ids = {}
local inbox_seq = 0
local input_text = ""

local function ensure_dirs()
  for _, sub in ipairs({ "inbox", "chat", "requests", "results" }) do
    reaper.RecursiveCreateDirectory(BRIDGE_ROOT .. "/" .. sub, 0)
  end
end

local function launch_companion()
  local cmd = string.format('"%s" -m reamind.server --bridge "%s"', COMPANION_PY, BRIDGE_ROOT)
  reaper.ExecProcess(cmd, -2)
end

local function list_files(dir)
  local out = {}
  local i = 0
  while true do
    local f = reaper.EnumerateFiles(dir, i)
    if not f then break end
    out[#out + 1] = f
    i = i + 1
  end
  table.sort(out)
  return out
end

local function drain_chat()
  local dir = BRIDGE_ROOT .. "/chat"
  for _, name in ipairs(list_files(dir)) do
    local path = dir .. "/" .. name
    local msg = ipc.read_json(path)
    if msg and not seen_chat[msg.seq] then
      seen_chat[msg.seq] = true
      messages[#messages + 1] = msg
    end
    os.remove(path)
  end
end

local function run_tool(name, args)
  local fn = tools[name]
  if not fn then return false, "unknown tool: " .. tostring(name) end
  reaper.Undo_BeginBlock()
  local ok, result = fn(args)
  reaper.Undo_EndBlock(name .. " (ReaMind)", -1)
  return ok, result
end

local function poll_requests()
  local dir = BRIDGE_ROOT .. "/requests"
  for _, name in ipairs(list_files(dir)) do
    local path = dir .. "/" .. name
    local req = ipc.read_json(path)
    if req and req.id and not processed_ids[req.id] then
      processed_ids[req.id] = true
      local args = helpers.coerce_args({}, req.args or {})
      local ok, result = run_tool(req.tool, args)
      ipc.write_result(BRIDGE_ROOT, req.id, ok, result)
    end
    os.remove(path)
  end
end

local function draw()
  local visible, open = reaper.ImGui_Begin(ctx, "ReaMind", true)
  if visible then
    if reaper.ImGui_BeginChild(ctx, "transcript", 0, -60) then
      for _, m in ipairs(messages) do
        reaper.ImGui_TextWrapped(ctx, string.format("[%s] %s", m.role or "?", m.text or ""))
      end
      reaper.ImGui_EndChild(ctx)
    end
    local changed, txt = reaper.ImGui_InputText(ctx, "##input", input_text)
    if changed then input_text = txt end
    reaper.ImGui_SameLine(ctx)
    if reaper.ImGui_Button(ctx, "Send") and input_text ~= "" then
      inbox_seq = inbox_seq + 1
      ipc.push_inbox(BRIDGE_ROOT, inbox_seq, input_text)
      messages[#messages + 1] = { role = "user", text = input_text }
      input_text = ""
    end
    reaper.ImGui_End(ctx)
  end
  return open
end

local function loop()
  drain_chat()
  poll_requests()
  local open = draw()
  if open then
    reaper.defer(loop)
  end
end

ensure_dirs()
launch_companion()
reaper.defer(loop)
```

- [ ] **Step 2: Syntax-check with standalone lua**

Run: `cd panel && lua -e "assert(loadfile('reamind_panel.lua'))" && echo "parse ok"`
Expected: prints `parse ok`.

- [ ] **Step 3: Manual smoke test in REAPER**

Do this manually (document result in the commit message body if anything deviates):
1. In REAPER: Actions → Show action list → New action → Load ReaScript → select `panel/reamind_panel.lua`.
2. Ensure a local model is available: `ollama pull qwen2.5:7b` (or start LM Studio with a tool-capable model loaded).
3. Run the action. Expect: a docked "ReaMind" window appears; the companion process starts (check `bridge/heartbeat.json` updates).
4. Type "how many tracks are in my project?" → the assistant should call `get_project_summary` and reply with the count.

- [ ] **Step 4: Commit**

```bash
cd /home/bradzgar/projects/reamind
git add panel/reamind_panel.lua
git commit -m "feat: reaimgui chat panel with defer loop and companion launch"
```

---

### Task 13: Selftest action + end-to-end smoke doc

**Files:**
- Create: `panel/reamind_selftest.lua`
- Create: `docs/SMOKE.md`

**Interfaces:**
- `panel/reamind_selftest.lua` — a standalone REAPER action that, against the current project, runs each read-only tool from `tools/readonly.lua` directly (no LLM, no bridge) and shows pass/fail per tool in the REAPER console (`reaper.ShowConsoleMsg`). This validates the ReaScript-touching code path in isolation.
- `docs/SMOKE.md` — the manual release smoke checklist, including the end-to-end scenario.

- [ ] **Step 1: Write the selftest action**

Create `panel/reamind_selftest.lua`:

```lua
local SCRIPT_DIR = ({reaper.get_action_context()})[2]:match("^(.*[/\\])")
package.path = SCRIPT_DIR .. "?.lua;" .. package.path
local tools = require("tools.readonly")
local json = require("json")

local function report(name, ok, result)
  local status = ok and "PASS" or "FAIL"
  reaper.ShowConsoleMsg(string.format("[%s] %s -> %s\n", status, name, json.encode(result)))
end

reaper.ShowConsoleMsg("ReaMind selftest\n================\n")

local ok1, r1 = tools.get_project_summary({})
report("get_project_summary", ok1, r1)

local ok2, r2 = tools.list_tracks({})
report("list_tracks", ok2, r2)

if ok2 and r2.tracks and r2.tracks[1] then
  local guid = r2.tracks[1].guid
  local ok3, r3 = tools.get_track({ track_guid = guid })
  report("get_track", ok3, r3)
else
  reaper.ShowConsoleMsg("[SKIP] get_track (no tracks in project)\n")
end
```

- [ ] **Step 2: Syntax-check**

Run: `cd panel && lua -e "assert(loadfile('reamind_selftest.lua'))" && echo "parse ok"`
Expected: prints `parse ok`.

- [ ] **Step 3: Write the smoke checklist**

Create `docs/SMOKE.md`:

```markdown
# ReaMind Manual Smoke Checklist (Foundation)

Prereqs:
- `cd companion && python -m venv .venv && .venv/bin/pip install -e ".[dev]"`
- A local model server running with a tool-capable model (e.g. `ollama pull qwen2.5:7b`).
- ReaImGui installed (ReaPack).

## Companion unit tests
- [ ] `cd companion && .venv/bin/python -m pytest -v` → all pass.

## Lua helper tests
- [ ] `cd panel && lua test/json_spec.lua && lua test/helpers_spec.lua` → `failed=0`.

## Selftest action (ReaScript path, no LLM)
- [ ] Load `panel/reamind_selftest.lua` as an action and run it.
- [ ] Console shows PASS for get_project_summary, list_tracks, and (with >=1 track) get_track.

## End-to-end (LLM + bridge + panel)
- [ ] Load and run `panel/reamind_panel.lua`. Docked "ReaMind" window appears.
- [ ] `bridge/heartbeat.json` timestamp updates every second or two.
- [ ] Ask: "how many tracks are in my project?" → assistant calls get_project_summary and answers with the correct count.
- [ ] Add a track named "Kick", ask: "what tracks do I have?" → assistant lists it by name.
- [ ] Kill the companion process; panel shows a "companion not responding — Restart" affordance (or relaunch), and works again after restart.
```

- [ ] **Step 4: Commit**

```bash
cd /home/bradzgar/projects/reamind
git add panel/reamind_selftest.lua docs/SMOKE.md
git commit -m "feat: selftest action and smoke checklist"
```

---

## Self-Review

**1. Spec coverage (this plan targets spec §8 phases 1–2):**
- IPC bridge + protocol (spec §3) → Tasks 2, 3, 10 (both sides), request/result shapes match spec exactly (`id`, `seq`, `tool`, `args` / `id`, `ok`, `result|error`).
- Panel skeleton + companion skeleton + echo round-trip (phase 1) → Tasks 9, 12 (inbox→agent→chat; requests→panel→results).
- Local provider + local-first onboarding (spec §5) → Task 6 (`detect_servers`, `list_models`, zero-key default) + `build_provider` in Task 9.
- Agent loop with routing + iteration/timeout guards + GUID addressing (spec §5, §6) → Tasks 8, 9; system prompt states GUID convention.
- Read-only project awareness tools (spec §4.1) → Tasks 7 (schemas) + 11 (Lua impls).
- Config file at `~/.config/reamind/config.json` (spec §6) → Task 4.
- Undo-wrapping every REAPER tool (spec §6) → Task 12 `run_tool`.
- Testing strategy (spec §7): pytest for companion logic, fake provider for agent loop, bridge round-trip test, Lua pure-helper tests, selftest action, e2e smoke → Tasks 2–13.
- Deferred to later plans (correctly out of this plan's scope): construction/routing/FX/templates (phase 3), theming/onboarding UI (phase 4), library management (phase 5), MCP + cloud providers (phase 6), all audio DSP (spec §10).

**2. Placeholder scan:** No "TBD"/"implement later"/vague steps. Every code step contains complete code. The one external fetch (rxi/json.lua) has an explicit offline fallback described.

**3. Type consistency:** `ToolSpec(name, description, parameters, executor)`, `ToolCall(id, name, arguments)`, `Message(role, content, tool_calls, tool_call_id, name)`, `ChatResult(text, tool_calls)` used identically across Tasks 5–9. Bridge method names (`push_chat`, `drain_inbox`, `send_request`, `read_result`, `write_heartbeat`, `clear_stale`, `write_session`) consistent between Task 3 definition and Task 9 usage. Result dict shape `{ok, result|error}` consistent between Lua `write_result` (Task 10), Lua tools (Task 11), agent `_execute_call` (Task 8), and server executor (Task 9). Bridge filename format `%09d.json` matches between Python (`push_chat`) and Lua (`helpers.seq_name`).
