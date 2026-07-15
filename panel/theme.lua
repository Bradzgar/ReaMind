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

function M.apply(ctx, colors)
    local col = M.merge_colors(M.DEFAULTS, colors)
    local v = helpers.hex_to_native_color
    if v(col.bg) then
        reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_WindowBg(), v(col.bg))
    end
    if v(col.text) then
        reaper.ImGui_PushStyleColor(ctx, reaper.ImGui_Col_Text(), v(col.text))
    end
    if col.font_scale and col.font_scale > 0 then
        local io = reaper.ImGui_GetIO(ctx)
        if io then io.FontGlobalScale = col.font_scale end
    end
end

function M.sample_reaper_colors(ctx)
    local function gc(idx)
        local ok, c = reaper.ThemeLayout_GetColor(idx)
        return ok and c or 0
    end
    return {
        bg = "#1e1e1e",
        text = "#d4d4d4",
        accent = "#569cd6",
        user_bubble = "#2d5a27",
        assistant_bubble = "#1e3a5f",
        error = "#f44747",
        font_scale = 1.0,
    }
end

return M
