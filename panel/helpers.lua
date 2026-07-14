local M = {}

function M.seq_name(n)
  return string.format("%09d.json", n)
end

function M.hex_to_native_color(hex)
  if type(hex) ~= "string" then return nil end
  local r, g, b = hex:match("^#(%x%x)(%x%x)(%x%x)$")
  if not r then return nil end
  r = tonumber(r, 16)
  g = tonumber(g, 16)
  b = tonumber(b, 16)
  return r | (g << 8) | (b << 16)
end

function M.coerce_args(schema_props, args)
  local out = {}
  for k, v in pairs(args or {}) do
    local prop = schema_props and schema_props[k]
    if prop and prop.type == "integer" and type(v) == "string" then
      out[k] = tonumber(v) or v
    else
      out[k] = v
    end
  end
  return out
end

return M
