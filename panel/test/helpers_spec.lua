package.path = "./?.lua;" .. package.path
local t = require("test.run")
local h = require("helpers")

t.eq(h.seq_name(1), "000000001.json", "seq_name pads")
t.eq(h.seq_name(42), "000000042.json", "seq_name pads 42")

t.eq(h.hex_to_native_color("#FF0000"), 255, "red -> 255")
t.eq(h.hex_to_native_color("#00FF00"), 65280, "green -> 65280")
t.eq(h.hex_to_native_color("#0000FF"), 16711680, "blue -> 16711680")
t.eq(h.hex_to_native_color("bad"), nil, "malformed -> nil")

local coerced = h.coerce_args({ n = { type = "integer" } }, { n = "5", s = "x" })
t.eq(coerced.n, 5, "integer string coerced")
t.eq(coerced.s, "x", "string passthrough")

t.finish()
