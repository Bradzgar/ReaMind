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

## Theming & Onboarding Smoke

1. **Settings panel opens:** Launch panel in REAPER. Click "Settings" header. See server status and theme controls.
2. **Server detection:** Panel shows detected servers. Refresh button re-scans.
3. **Theme preset:** Select "light" from the preset combo. Colors change immediately.
4. **Custom color:** Edit the "bg" field to "#222222", click Apply. Background changes.
5. **Font scale:** Drag the slider to 1.5. Text scales up.
6. **Save theme:** Edit a color, click "Save Theme". Restart panel — verify the saved theme is applied.

## Construction Tools Smoke

1. **Create track:** Ask "Create a track called Test Vocal." Verify track appears in REAPER.
2. **Set track props:** Ask "Rename track X to Lead Vocals and color it blue."
3. **Create folder:** "Make a folder called DRUMS." A folder track appears.
4. **Add send:** "Send Kick to Reverb." A send is created in the routing matrix.
5. **Sidechain:** "Sidechain the Kick into the Bass compressor." Verify routing on channels 3/4.
6. **Insert FX:** "Add an EQ to the Vocal track." ReaEQ appears on the track.
7. **Set FX param:** "Set the EQ band 1 frequency on Vocal to 200Hz."
8. **Template:** "Apply the drum_kit_7mic template." 8 tracks created in a DRUMS folder.
9. **Delete confirmation:** "Delete track X." Verify confirmation prompt before execution.
10. **Undo:** Use Ctrl+Z to undo any operation. Verify undo works for every tool.
