local M = {}

function M.list_available_fx(args)
  local fx_list = {}
  local old_count = 0
  local same_count = 0

  while true do
    local count = reaper.CountEnumerateInstalledPlugins()
    if count == 0 then break end
    if count == old_count then
      same_count = same_count + 1
      if same_count > 2 then break end
    else
      same_count = 0
    end
    old_count = count

    for i = 0, count - 1 do
      local _, name, _, _, _, ident = reaper.EnumerateInstalledPlugins(i)
      if name and name ~= "" then
        fx_list[#fx_list + 1] = { name = name, identifier = ident or name }
      end
    end

    if count > 0 and fx_list[1] then break end
  end

  return true, { fx_list = fx_list }
end

return M
