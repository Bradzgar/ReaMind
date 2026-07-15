local SCRIPT_DIR = ({reaper.get_action_context()})[2]:match("^(.*[/\\])")
package.path = SCRIPT_DIR .. "?.lua;" .. package.path

local ipc = require("ipc")
local helpers = require("helpers")
local tools = require("tools.readonly")
local con_tools = require("tools.construction")
local fx_scanner = require("tools.fx_scanner")
local theme = require("theme")

local all_tools = {}
for k, v in pairs(tools) do all_tools[k] = v end
for k, v in pairs(con_tools) do all_tools[k] = v end
all_tools["list_available_fx"] = fx_scanner.list_available_fx
all_tools.tool_specs = {}
for k, v in pairs(tools.tool_specs or {}) do all_tools.tool_specs[k] = v end
for k, v in pairs(con_tools.tool_specs or {}) do all_tools.tool_specs[k] = v end

local BRIDGE_ROOT = SCRIPT_DIR .. "../bridge"

local SEP = package.config:sub(1, 1)

local is_windows = reaper.GetOS():match("^Win")
local COMPANION_PY
if is_windows then
  COMPANION_PY = SCRIPT_DIR .. "../companion/.venv/Scripts/python.exe"
else
  COMPANION_PY = SCRIPT_DIR .. "../companion/.venv/bin/python"
end

local ctx = reaper.ImGui_CreateContext("ReaMind")
local messages = {}
local seen_chat = {}
local processed_ids = {}
local inbox_seq = 0
local input_text = ""
local companion_started = false
local HEARTBEAT_TIMEOUT = 15
local last_heartbeat = 0
local state = { frame = 0 }

local settings_loaded = false
local server_display = "scanning..."
local available_models = {}
local current_model = ""
local provider_url = ""
local provider_model = ""
local provider_api_key = ""
local current_colors = { bg = theme.DEFAULTS.bg, text = theme.DEFAULTS.text, accent = theme.DEFAULTS.accent,
                          user_bubble = theme.DEFAULTS.user_bubble, assistant_bubble = theme.DEFAULTS.assistant_bubble,
                          error = theme.DEFAULTS.error }
local theme_preset_items = { "dark", "light" }

local function config_path()
  if is_windows then
    return (os.getenv("APPDATA") or (os.getenv("USERPROFILE") or "") .. "/AppData/Roaming") .. "/reamind/config.json"
  end
  local home = os.getenv("HOME") or os.getenv("USERPROFILE") or ""
  return home .. "/.config/reamind/config.json"
end
local current_preset_idx = 0

local function ensure_dirs()
  for _, sub in ipairs({ "inbox", "chat", "requests", "results" }) do
    reaper.RecursiveCreateDirectory(BRIDGE_ROOT .. SEP .. sub, 0)
  end
end

do
  local c = ipc.read_json(config_path())
  if c and c.provider then
    provider_url = c.provider.base_url or ""
    provider_model = c.provider.model or ""
    provider_api_key = c.provider.api_key or ""
  end
end

local function launch_companion()
  local cmd = string.format('"%s" -m reamind.server --bridge "%s" --config "%s"', COMPANION_PY, BRIDGE_ROOT, config_path())
  if is_windows then
    cmd = 'cmd /k ' .. cmd
  end
  reaper.ExecProcess(cmd, -2)
  companion_started = true
  last_heartbeat = reaper.time_precise()
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
    if not name:match("%.json$") then goto continue end
    local path = dir .. SEP .. name
    local msg = ipc.read_json(path)
    if msg and not seen_chat[msg.seq] then
      seen_chat[msg.seq] = true
      messages[#messages + 1] = msg
    end
    pcall(os.remove, path)
    ::continue::
  end
end

local function run_tool(name, args)
  local fn = all_tools[name]
  if not fn then return false, "unknown tool: " .. tostring(name) end
  reaper.Undo_BeginBlock()
  local results = { pcall(fn, args) }
  reaper.Undo_EndBlock("ReaMind: " .. name, -1)
  local pcall_ok = results[1]
  if not pcall_ok then
    return false, tostring(results[2])
  end
  return table.unpack(results, 2)
end

local function poll_requests()
  local dir = BRIDGE_ROOT .. SEP .. "requests"
  for _, name in ipairs(list_files(dir)) do
    if not name:match("%.json$") then goto continue end
    local path = dir .. SEP .. name
    local req = ipc.read_json(path)
    if req and req.id and not processed_ids[req.id] then
      processed_ids[req.id] = true
      local args = helpers.coerce_args(all_tools.tool_specs[req.tool] or {}, req.args or {})
      local ok, result = run_tool(req.tool, args)
      ipc.write_result(BRIDGE_ROOT, req.id, ok, result)
    end
    pcall(os.remove, path)
    ::continue::
  end
end

local function check_heartbeat()
  local path = BRIDGE_ROOT .. "/heartbeat.json"
  local hb = ipc.read_json(path)
  if not hb then return end
  if hb.ts then
    last_heartbeat = reaper.time_precise()
  end
end

local function load_status()
  local path = BRIDGE_ROOT .. "/status.json"
  local s = ipc.read_json(path)
  if not s then return nil end
  return s
end

local function save_config(config_table)
  local data = config_table or {}
  local path = BRIDGE_ROOT .. "/config_overlay.json"
  ipc.write_json_atomic(path, data)
end

local function draw()
  reaper.ImGui_SetNextWindowSize(ctx, 500, 400, reaper.ImGui_Cond_FirstUseEver())
  local visible, open = reaper.ImGui_Begin(ctx, "ReaMind", true)
  if visible then
    theme.apply(ctx, current_colors)
    if reaper.ImGui_BeginChild(ctx, "transcript", 0, -60) then
      for _, m in ipairs(messages) do
        reaper.ImGui_TextWrapped(ctx, string.format("[%s] %s", m.role or "?", m.text or ""))
      end
      reaper.ImGui_EndChild(ctx)
    end
    state.frame = (state.frame or 0) + 1
    if state.frame % 30 == 1 then check_heartbeat() end
    if companion_started and (reaper.time_precise() - last_heartbeat) > HEARTBEAT_TIMEOUT then
      reaper.ImGui_TextColored(ctx, 0xFF4040FF, "companion not responding")
      reaper.ImGui_SameLine(ctx)
      if reaper.ImGui_Button(ctx, "Restart") then
        launch_companion()
      end
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
    if reaper.ImGui_CollapsingHeader(ctx, "Settings") then
      if not settings_loaded and companion_started then
        local status = load_status()
        if status then
          if status.current_model and status.current_model ~= "" then
            current_model = status.current_model
          end
          local server_names = {}
          for _, s in ipairs(status.servers or {}) do
            server_names[#server_names + 1] = s.name
            for _, m in ipairs(s.models or {}) do
              available_models[#available_models + 1] = { name = m, base_url = s.base_url }
            end
          end
          server_display = #server_names > 0 and table.concat(server_names, ", ") or "none found"
          settings_loaded = true
        end
      end
      reaper.ImGui_Text(ctx, "Servers: " .. (server_display or "scanning..."))
      reaper.ImGui_TextWrapped(ctx, "Model: " .. (current_model ~= "" and current_model or "auto-detect"))

      if reaper.ImGui_Button(ctx, "Refresh Servers") then
        settings_loaded = false
        server_display = "scanning..."
        available_models = {}
      end
      reaper.ImGui_Separator(ctx)
      reaper.ImGui_Text(ctx, "Provider")
      local url_changed, new_url = reaper.ImGui_InputText(ctx, "Base URL", provider_url)
      if url_changed then provider_url = new_url end
      local model_changed, new_model = reaper.ImGui_InputText(ctx, "Model", provider_model)
      if model_changed then provider_model = new_model end
      local key_changed, new_key = reaper.ImGui_InputText(ctx, "API Key", provider_api_key)
      if key_changed then provider_api_key = new_key end
      if reaper.ImGui_Button(ctx, "Save & Restart Companion") then
        local c = ipc.read_json(config_path()) or {}
        c.provider = c.provider or {}
        c.provider.base_url = provider_url
        c.provider.model = provider_model
        c.provider.api_key = provider_api_key
        ipc.write_json_atomic(config_path(), c)
        launch_companion()
      end
      reaper.ImGui_Separator(ctx)
      reaper.ImGui_Text(ctx, "Theme")
      local preset_changed, new_preset = reaper.ImGui_Combo(ctx, "Preset", current_preset_idx, table.concat(theme_preset_items, "\0") .. "\0")
      if preset_changed then
        current_preset_idx = new_preset
        local preset_name = theme_preset_items[new_preset + 1]
        if preset_name == "dark" then current_colors = theme.merge_colors(theme.DEFAULTS, {}) end
        if preset_name == "light" then
          current_colors = theme.merge_colors(theme.DEFAULTS, {
            bg = "#f0f0f0", text = "#1a1a1a", accent = "#007acc",
            user_bubble = "#d4edda", assistant_bubble = "#d6e4f0", error = "#dc3545",
          })
        end
      end
      for _, key in ipairs({ "bg", "text", "accent", "user_bubble", "assistant_bubble", "error" }) do
        local changed, val = reaper.ImGui_InputText(ctx, key, current_colors[key] or "")
        if changed then
          current_colors[key] = val
        end
      end
      if reaper.ImGui_Button(ctx, "Save Theme") then
        local conf = {
          theme = { preset = theme_preset_items[current_preset_idx + 1] or "dark", colors = current_colors }
        }
        ipc.write_json_atomic(config_path(), conf)
      end
    end
    theme.pop(ctx)
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
