package.path = "./?.lua;" .. package.path
local t = require("test.run")
local json = require("json")

local encoded = json.encode({ a = 1, b = { 2, 3 } })
local decoded = json.decode(encoded)
t.eq(decoded.a, 1, "json roundtrip a")
t.eq(decoded.b[1], 2, "json roundtrip b[1]")
t.eq(decoded.b[2], 3, "json roundtrip b[2]")

local obj = json.decode('{"id":"call_1","ok":true}')
t.eq(obj.id, "call_1", "decode id")
t.eq(obj.ok, true, "decode ok")

t.finish()
