local M = {}

function M._clamp_db(val, min, max)
  local v = tonumber(val) or 0
  if v < min then return min end
  if v > max then return max end
  return v
end

function M._is_valid_guid(s)
  return type(s) == "string" and s:match("^{.*}$") ~= nil
end

function M._is_hex_color_str(s)
  return type(s) == "string" and s:match("^#[0-9a-fA-F]+$") ~= nil
end

local function track_by_guid(guid)
  local count = reaper.CountTracks(0)
  for i = 0, count - 1 do
    local tr = reaper.GetTrack(0, i)
    if reaper.GetTrackGUID(tr) == guid then
      return tr, i
    end
  end
  return nil
end

function M.create_track(args)
  local name = args and args.name or "New Track"
  local idx = reaper.CountTracks(0)
  local position = tonumber(args and args.position) or -1
  if position < 0 or position > idx then position = idx end
  reaper.InsertTrackAtIndex(position, true)
  local tr = reaper.GetTrack(0, position)
  reaper.GetSetMediaTrackInfo_String(tr, "P_NAME", name, true)

  local color = tonumber(args and args.color)
  if color then
    reaper.SetTrackColor(tr, color)
  end

  local parent_guid = args and args.parent_guid
  if parent_guid and parent_guid ~= "" then
    local parent_tr = track_by_guid(parent_guid)
    if parent_tr then
      local parent_depth = reaper.GetMediaTrackInfo_Value(parent_tr, "I_FOLDERDEPTH")
      if parent_depth == 0 then
        reaper.SetMediaTrackInfo_Value(parent_tr, "I_FOLDERDEPTH", 1)
      end
      reaper.SetMediaTrackInfo_Value(tr, "I_FOLDERDEPTH", -1)
    end
  end

  local guid = reaper.GetTrackGUID(tr)
  return true, { track_guid = guid, index = position }
end

function M.create_folder(args)
  local name = args and args.name or "Folder"
  local child_guids = args and args.child_guids or {}

  local idx = reaper.CountTracks(0)
  reaper.InsertTrackAtIndex(idx, true)
  local folder_tr = reaper.GetTrack(0, idx)
  reaper.GetSetMediaTrackInfo_String(folder_tr, "P_NAME", name, true)
  reaper.SetMediaTrackInfo_Value(folder_tr, "I_FOLDERDEPTH", 1)

  local child_count = 0
  for _, child_guid in ipairs(child_guids) do
    local child_tr = track_by_guid(child_guid)
    if child_tr then
      reaper.SetMediaTrackInfo_Value(child_tr, "I_FOLDERDEPTH", -1)
      child_count = child_count + 1
    end
  end

  reaper.SetMediaTrackInfo_Value(folder_tr, "I_FOLDERDEPTH", 0)

  return true, {
    folder_guid = reaper.GetTrackGUID(folder_tr),
    child_count = child_count,
  }
end

function M.set_track_props(args)
  local guid = args and args.track_guid
  if not guid then return false, "missing track_guid" end
  local tr = track_by_guid(guid)
  if not tr then return false, "track not found" end

  if args.name ~= nil then
    reaper.GetSetMediaTrackInfo_String(tr, "P_NAME", args.name, true)
  end
  if args.color ~= nil then
    reaper.SetTrackColor(tr, args.color)
  end
  if args.volume_db ~= nil then
    reaper.SetMediaTrackInfo_Value(tr, "D_VOL", M._clamp_db(args.volume_db, -150, 24))
  end
  if args.pan ~= nil then
    reaper.SetMediaTrackInfo_Value(tr, "D_PAN", math.max(-1, math.min(1, args.pan or 0)))
  end
  if args.record_arm ~= nil then
    reaper.SetMediaTrackInfo_Value(tr, "I_RECARM", args.record_arm and 1 or 0)
  end

  return true, { track_guid = guid }
end

function M.delete_track(args)
  local guid = args and args.track_guid
  if not guid then return false, "missing track_guid" end
  local tr, idx = track_by_guid(guid)
  if not tr then return false, "track not found" end
  reaper.DeleteTrack(tr)
  return true, { track_guid = guid }
end

function M.add_send(args)
  local src_guid = args and args.src_guid
  local dst_guid = args and args.dst_guid
  if not src_guid or not dst_guid then return false, "missing src_guid or dst_guid" end

  local src_tr = track_by_guid(src_guid)
  local dst_tr = track_by_guid(dst_guid)
  if not src_tr or not dst_tr then return false, "track not found" end

  local gain = tonumber(args and args.gain_db) or 0
  local is_pre = args and args.is_pre_fader

  local send_idx = reaper.CreateTrackSend(src_tr, dst_tr)
  if send_idx >= 0 then
    reaper.SetTrackSendInfo_Value(src_tr, 0, send_idx, "D_VOL", M._clamp_db(gain, -150, 24))
    if is_pre then
      reaper.SetTrackSendInfo_Value(src_tr, 0, send_idx, "I_SENDMODE", 3)
    end
  end

  return true, { src_guid = src_guid, dst_guid = dst_guid, send_index = send_idx }
end

function M.add_receive(args)
  local src_guid = args and args.src_guid
  local dst_guid = args and args.dst_guid
  if not src_guid or not dst_guid then return false, "missing src_guid or dst_guid" end

  local src_tr = track_by_guid(src_guid)
  local dst_tr = track_by_guid(dst_guid)
  if not src_tr or not dst_tr then return false, "track not found" end

  local gain = tonumber(args and args.gain_db) or 0
  local recv_idx = reaper.CreateTrackSend(src_tr, dst_tr)
  if recv_idx >= 0 then
    reaper.SetTrackSendInfo_Value(src_tr, 0, recv_idx, "D_VOL", M._clamp_db(gain, -150, 24))
  end

  return true, { src_guid = src_guid, dst_guid = dst_guid, receive_index = recv_idx }
end

function M.create_sidechain(args)
  local source_guid = args and args.source_guid
  local target_guid = args and args.target_guid
  if not source_guid or not target_guid then return false, "missing source_guid or target_guid" end

  local src_tr = track_by_guid(source_guid)
  local tgt_tr = track_by_guid(target_guid)
  if not src_tr or not tgt_tr then return false, "track not found" end

  local fx_idx = tonumber(args and args.target_fx_index) or -1
  if fx_idx < 0 then
    fx_idx = reaper.TrackFX_GetCount(tgt_tr) - 1
  end

  reaper.TrackFX_SetPinMappings(tgt_tr, fx_idx, 0, 1, 0, 1023)
  reaper.TrackFX_SetPinMappings(tgt_tr, fx_idx, 0, 3, 2, 1023)

  return true, {
    source_guid = source_guid,
    target_guid = target_guid,
    channels = "3/4",
  }
end

function M.insert_fx(args)
  local guid = args and args.track_guid
  local fx_name = args and args.fx_name
  if not guid or not fx_name then return false, "missing track_guid or fx_name" end

  local tr = track_by_guid(guid)
  if not tr then return false, "track not found" end

  local position = tonumber(args and args.position) or -1
  if position < 0 then
    position = reaper.TrackFX_GetCount(tr)
  end

  local fx_idx = reaper.TrackFX_AddByName(tr, fx_name, false, position)

  return true, { track_guid = guid, fx_index = fx_idx }
end

function M.set_fx_param(args)
  local guid = args and args.track_guid
  local fx_idx = tonumber(args and args.fx_index)
  local param = args and args.param
  local value = tonumber(args and args.value)

  if not guid or fx_idx == nil or param == nil or value == nil then
    return false, "missing track_guid, fx_index, param, or value"
  end

  local tr = track_by_guid(guid)
  if not tr then return false, "track not found" end

  local pidx = tonumber(param)
  if pidx == nil then
    local count = reaper.TrackFX_GetNumParams(tr, fx_idx)
    for i = 0, count - 1 do
      local _, pname = reaper.TrackFX_GetParamName(tr, fx_idx, i, "")
      if pname and pname:lower():find(param:lower(), 1, true) then
        pidx = i
        break
      end
    end
  end

  if pidx == nil then return false, "param not found" end

  reaper.TrackFX_SetParam(tr, fx_idx, pidx, value)

  return true, { track_guid = guid, fx_index = fx_idx, param = param }
end

function M.undo_point(args)
  return true, { name = args and args.name or "" }
end

function M.apply_template(args)
  local steps = args and args.steps
  if not steps then return false, "missing steps" end

  local completed = 0
  local results = {}
  for _, step in ipairs(steps) do
    local fn = M[step.tool]
    if fn then
      local ok, result = pcall(fn, step.args or {})
      if ok then
        completed = completed + 1
        results[#results + 1] = result
      else
        results[#results + 1] = { error = tostring(result) }
      end
    end
  end

  return true, {
    template_name = args and args.template_name or "",
    steps_completed = completed,
    total_steps = #steps,
    results = results,
  }
end

M.tool_specs = {
  create_track = {
    name = { type = "string" },
    color = { type = "integer" },
    position = { type = "integer" },
    parent_guid = { type = "string" },
  },
  create_folder = {
    name = { type = "string" },
    child_guids = { type = "array", items = { type = "string" } },
  },
  set_track_props = {
    track_guid = { type = "string" },
  },
  delete_track = {
    track_guid = { type = "string" },
  },
  add_send = {
    src_guid = { type = "string" },
    dst_guid = { type = "string" },
  },
  add_receive = {
    src_guid = { type = "string" },
    dst_guid = { type = "string" },
  },
  create_sidechain = {
    source_guid = { type = "string" },
    target_guid = { type = "string" },
  },
  insert_fx = {
    track_guid = { type = "string" },
    fx_name = { type = "string" },
  },
  set_fx_param = {
    track_guid = { type = "string" },
    fx_index = { type = "integer" },
    param = { type = "string" },
    value = { type = "number" },
  },
  list_available_fx = {},
  apply_template = {
    template_name = { type = "string" },
    steps = { type = "array" },
  },
  undo_point = {
    name = { type = "string" },
  },
}

return M
