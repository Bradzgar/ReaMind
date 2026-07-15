local helpers = require("helpers")

local M = {}

M.DEFAULTS = {
    bg = "#1e1e1e",
    text = "#d4d4d4",
    accent = "#569cd6",
    user_bubble = "#2d5a27",
    assistant_bubble = "#1e3a5f",
    error = "#f44747",
    font_scale = 1.0,
}

function M.merge_colors(base, overrides)
    local out = {}
    for k, v in pairs(base or {}) do
        out[k] = v
    end
    for k, v in pairs(overrides or {}) do
        out[k] = v
    end
    return out
end

function M.hex_to_imgui_color(hex)
    if type(hex) ~= "string" then return nil end
    local r, g, b = hex:match("^#(%x%x)(%x%x)(%x%x)$")
    if not r then return nil end
    r = tonumber(r, 16) / 255
    g = tonumber(g, 16) / 255
    b = tonumber(b, 16) / 255
    return reaper.ImGui_ColorConvertDouble4ToU32(r, g, b, 1.0)
end

M._pushed = 0

function M.apply(ctx, colors)
    local col = M.merge_colors(M.DEFAULTS, colors)
    local cv = M.hex_to_imgui_color
    if cv(col.bg) then
        reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_WindowBg(), cv(col.bg))
        M._pushed = M._pushed + 1
    end
    if cv(col.text) then
        reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_Text(), cv(col.text))
        M._pushed = M._pushed + 1
    end
    if col.font_scale and col.font_scale > 0 then
        local io = reaper.ImGui_GetIO(ctx)
        if io then io.FontGlobalScale = col.font_scale end
    end
end

function M.pop(ctx)
    if M._pushed > 0 then
        reaper.ImGui_PopStyleColor(ctx, M._pushed)
        M._pushed = 0
    end
end

return M
