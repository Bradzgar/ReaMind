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
