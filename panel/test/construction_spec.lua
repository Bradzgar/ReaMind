require("test.run")

-- Set package.path to find construction module
local script_dir = debug.getinfo(1).source:match("@?(.*/)")
package.path = script_dir .. "../?.lua;" .. package.path

local t = require("test.run")

local c = require("tools.construction")

-- clamp_db
t.eq(c._clamp_db(5, -24, 24), 5)
t.eq(c._clamp_db(-30, -24, 24), -24)
t.eq(c._clamp_db(50, -24, 24), 24)

-- is_valid_guid
t.truthy(c._is_valid_guid("{ABC123-DEF456}"))
t.truthy(c._is_valid_guid("{abc-def-ghi-jkl}"))
t.falsy(c._is_valid_guid(""))
t.falsy(c._is_valid_guid(nil))
t.falsy(c._is_valid_guid(123))

-- is_hex_color_str
t.truthy(c._is_hex_color_str("#FF8040"))
t.truthy(c._is_hex_color_str("#1e1e1e"))
t.falsy(c._is_hex_color_str("FF8040"))   -- no #
t.falsy(c._is_hex_color_str("#GGGGGG"))  -- not hex
t.falsy(c._is_hex_color_str(""))

t.finish()
