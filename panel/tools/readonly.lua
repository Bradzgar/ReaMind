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
