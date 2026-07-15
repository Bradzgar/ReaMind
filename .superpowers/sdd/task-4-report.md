# Task 4 Report: Agent confirmation gating

## Summary

Added confirmation gating for destructive tools to the agent loop. When a tool has both `destructive=True` and `return_confirmation=True`, the agent blocks execution unless `confirm_ok: true` is present in the tool call arguments. The `confirm_destructive` parameter on `run_turn` allows disabling this gating globally.

## Changes

### `companion/reamind/agent.py`
- `run_turn()`: Added `confirm_destructive: bool = True` parameter, threaded through to `_execute_call`.
- `_execute_call()`: Added `confirm_destructive: bool = True` parameter. Before dispatching to an executor, checks if `spec.destructive and spec.return_confirmation and confirm_destructive` — if all true and `confirm_ok` is not in call args, returns `{"ok": False, "confirm_required": True, ...}` to block execution.

### `companion/tests/test_agent.py`
Added 3 new tests:
- `test_destructive_tool_blocked_without_confirmation` — destructive tool with `confirm_destructive=True` is blocked when `confirm_ok` absent
- `test_destructive_tool_allowed_with_confirmation` — destructive tool proceeds when `confirm_ok: true` present in args
- `test_confirm_disabled_lets_destructive_through` — destructive tool proceeds when `confirm_destructive=False`

## TDD Evidence

### Step 1: Write failing tests
```
$ .venv/bin/python -m pytest tests/test_agent.py -v -k "destructive or confirm"
3 failed — TypeError: run_turn() got an unexpected keyword argument 'confirm_destructive'
```

### Step 2: Implement
Added `confirm_destructive` parameter to `run_turn` and `_execute_call`, with confirmation gating logic.

### Step 3: Verify individual tests
```
$ .venv/bin/python -m pytest tests/test_agent.py -v -k "destructive or confirm"
3 passed
```

### Step 4: Full suite
```
$ .venv/bin/python -m pytest -v
74 passed in 0.24s
```

## Commit
```
feat: confirmation gating for destructive tools
```

---

## Task 4 Review Fixes — MCP Host

**Commit:** `d30e5de` — `fix: add transport key to list_servers, fix prefix routing bug, defensive fixes`

### Fixes applied to `companion/reamind/mcp_host.py`

| # | Severity | Issue | Fix |
|---|----------|-------|-----|
| 1 | CRITICAL | Missing `"transport"` key in `list_servers()` | Added `"transport": type(c._transport).__name__` |
| 2 | IMPORTANT | Prefix routing bug in `execute()` — `startswith()` could route `"ab__tool"` to client `"a"` | Sort clients by `-len(c.name)` so longer prefixes match first |
| 3 | MINOR | Fragile error detection `"error" in str(resp)` | Changed to `"error" in resp` (dict key check) |
| 4 | MINOR | Silent tool loss — `list_tools()` unconditionally resets `self.tools = []` | Build into local `tools` list, assign `self.tools = tools` at end |
| 5 | MINOR | Overly broad `except Exception` in `call_tool` | Changed to `except (OSError, RuntimeError, ValueError, JSONRPCError)` |

### Test results
```
12/12 mcp_host tests pass (0.05s)
26/26 combined MCP protocol + host tests pass (0.06s)
```
