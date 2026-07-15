# ReaMind — Debug Logging Design Spec

**Date:** 2026-07-15
**Status:** Draft — pending review
**Phase:** Post-v1 enhancement

## 1. Overview

Add stdlib `logging`-based debug output to the Python companion. A `--debug`
CLI flag enables verbose output; normal mode is silent unless warnings or
errors occur. Replace all silent `except: pass` with logged warnings.

## 2. Architecture

```
companion/reamind/
  logutil.py            # NEW — configure_root(debug: bool), module-level get_logger()
  agent.py              # (modified) — log unknown tools, catch+log unexpected exceptions
  server.py             # (modified) — log startup steps, scan_fx/mcp_init failures
  local_tools.py        # (modified) — log model listing failures, provider switch errors
  provider_factory.py   # (modified) — log live check failures
  library/quarantine.py # (modified) — log per-file quarantine failures
```

**No Lua changes.** Debug info appears in companion stderr and in tool error
responses via traceback capture.

## 3. logutil.py

```python
import logging

def configure_root(debug: bool = False) -> None:
    logger = logging.getLogger("reamind")
    logger.setLevel(logging.DEBUG if debug else logging.WARNING)
    if not logger.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter(
            "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        ))
        logger.addHandler(h)

def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"reamind.{name}")
```

Each module does: `from .logutil import get_logger; log = get_logger("server")`

## 4. Logging sites

| Module | Event | Level |
|--------|-------|-------|
| `server` | Startup (config loaded, tools registered, provider built) | DEBUG |
| `server` | FX scan failure | WARNING |
| `server` | MCP init per-server failure | WARNING |
| `server` | Tool call dispatched | DEBUG |
| `agent` | Unknown tool requested | DEBUG |
| `agent` | Unexpect exception in _execute_call | ERROR (with traceback) |
| `local_tools` | Model listing failure in server_status | DEBUG |
| `local_tools` | Provider switch failure | WARNING |
| `provider_factory` | Live check failure | WARNING |
| `quarantine` | Per-file move/delete failure | DEBUG |
| `bridge` | Stale file clear | DEBUG |
| `mcp_host` | Server connect/disconnect | INFO |
| `mcp_host` | Tool call result | DEBUG |

## 5. Error response enhancement

In `agent._execute_call`, wrap the executor dispatch in a try/except that
captures the traceback and includes it in the error message visible to the
LLM. This gives the user a chance to see what failed even without stderr
access:

```python
try:
    if spec.executor == "reaper":
        return reaper_executor(call)
    ...
except Exception as e:
    import traceback
    tb = traceback.format_exc()
    log.error("Tool %s failed: %s\n%s", call.name, e, tb)
    return {"ok": False, "error": f"{e}\n{tb}"}
```

## 6. CLI

`--debug` flag added to argparse in `server.main()`. Calls `configure_root(debug=True)` before any logging site fires.

## 7. Scope

**In scope:**
- `logging`-based debug output to stderr
- `--debug` CLI flag
- Replace silent except:pass with logged warnings
- Traceback capture in agent error responses
- All modules get logger with module short name

**Out of scope:**
- File-based logging
- Log rotation
- Structured/JSON logging
- Lua panel debug output
- Bridge traffic dump
- Config-based debug toggle (CLI flag only)
