package.path = "./?.lua;" .. package.path
local t = require("test.run")

local theme = require("theme")
local helpers = require("helpers")

t.eq(theme.DEFAULTS.bg, "#1e1e1e")
t.eq(theme.DEFAULTS.text, "#d4d4d4")

local merged = theme.merge_colors(
    { bg = "#111", text = "#222" },
    { bg = "#999" }
)
t.eq(merged.bg, "#999")
t.eq(merged.text, "#222")
t.eq(merged.accent, nil)

local m2 = theme.merge_colors(
    { bg = "#111" },
    { bg = "#fff", text = "#ccc" }
)
t.eq(m2.bg, "#fff")
t.eq(m2.text, "#ccc")

local m3 = theme.merge_colors(nil, { bg = "#abc" })
t.eq(m3.bg, "#abc")

local m4 = theme.merge_colors({ bg = "#def" }, nil)
t.eq(m4.bg, "#def")

local col = helpers.hex_to_native_color("#FF8040")
t.truthy(col)

t.finish()
