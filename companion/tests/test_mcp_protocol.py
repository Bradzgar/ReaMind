import pytest

from reamind.mcp.protocol import (
    JSONRPCError,
    next_id,
    parse_response,
    send_notification,
    send_request,
)


class TestSendRequest:
    def test_minimal(self):
        msg = send_request(1, "test/method")
        assert msg == {"jsonrpc": "2.0", "id": 1, "method": "test/method"}

    def test_with_params(self):
        msg = send_request(2, "tools/call", {"name": "x", "arguments": {"a": 1}})
        assert msg["jsonrpc"] == "2.0"
        assert msg["id"] == 2
        assert msg["method"] == "tools/call"
        assert msg["params"] == {"name": "x", "arguments": {"a": 1}}

    def test_params_none_is_omitted(self):
        msg = send_request(3, "ping")
        assert "params" not in msg


class TestSendNotification:
    def test_minimal(self):
        msg = send_notification("initialized")
        assert msg == {"jsonrpc": "2.0", "method": "initialized"}
        assert "id" not in msg

    def test_with_params(self):
        msg = send_notification("notifications/ready", {"status": "ok"})
        assert msg["jsonrpc"] == "2.0"
        assert msg["method"] == "notifications/ready"
        assert msg["params"] == {"status": "ok"}
        assert "id" not in msg

    def test_params_none_is_omitted(self):
        msg = send_notification("ping")
        assert "params" not in msg


class TestParseResponse:
    def test_success_result(self):
        resp = {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}
        result = parse_response(resp)
        assert result["result"] == {"tools": []}

    def test_error_response_raises(self):
        resp = {"jsonrpc": "2.0", "id": 2, "error": {"code": -32600, "message": "invalid"}}
        with pytest.raises(JSONRPCError) as excinfo:
            parse_response(resp)
        assert excinfo.value.code == -32600
        assert "invalid" in excinfo.value.message

    def test_notification_returns_none(self):
        resp = {"jsonrpc": "2.0", "method": "notifications/ready"}
        result = parse_response(resp)
        assert result is None

    def test_missing_jsonrpc_raises(self):
        with pytest.raises(ValueError, match="jsonrpc"):
            parse_response({"id": 1, "result": {}})

    def test_wrong_jsonrpc_version_raises(self):
        with pytest.raises(ValueError, match="jsonrpc"):
            parse_response({"jsonrpc": "1.0", "id": 1, "result": {}})

    def test_response_without_result_or_error_raises(self):
        with pytest.raises(ValueError, match="result.*error"):
            parse_response({"jsonrpc": "2.0", "id": 1})

    def test_batch_not_supported(self):
        result = parse_response([{"jsonrpc": "2.0", "id": 1, "result": {}}])
        assert result == [{"jsonrpc": "2.0", "id": 1, "result": {}}]


class TestNextId:
    def test_increments(self):
        a = next_id()
        b = next_id()
        c = next_id()
        assert a == 1
        assert b == 2
        assert c == 3
