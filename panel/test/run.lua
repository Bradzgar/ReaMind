local M = { passed = 0, failed = 0 }

function M.eq(a, b, msg)
  if a ~= b then
    M.failed = M.failed + 1
    print(string.format("FAIL: %s (got %s, want %s)", msg or "", tostring(a), tostring(b)))
  else
    M.passed = M.passed + 1
  end
end

function M.truthy(v, msg)
  if not v then
    M.failed = M.failed + 1
    print(string.format("FAIL: %s (got falsy)", msg or ""))
  else
    M.passed = M.passed + 1
  end
end

function M.finish()
  print(string.format("passed=%d failed=%d", M.passed, M.failed))
  if M.failed > 0 then os.exit(1) end
end

return M
