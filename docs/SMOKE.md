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
