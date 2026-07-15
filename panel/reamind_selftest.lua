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

-- theme module
local theme = require("theme")
if theme.DEFAULTS and theme.DEFAULTS.bg and theme.DEFAULTS.text then
  reaper.ShowConsoleMsg("[PASS] theme: defaults loaded\n")
else
  reaper.ShowConsoleMsg("[FAIL] theme: defaults missing\n")
end
