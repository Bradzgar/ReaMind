from __future__ import annotations


class JSONRPCError(Exception):
    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


_counter = 0


def next_id() -> int:
    global _counter
    _counter += 1
    return _counter


def send_request(id: int, method: str, params: dict | None = None) -> dict:
    msg: dict = {"jsonrpc": "2.0", "id": id, "method": method}
    if params is not None:
        msg["params"] = params
    return msg


def send_notification(method: str, params: dict | None = None) -> dict:
    msg: dict = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        msg["params"] = params
    return msg


def parse_response(data: dict) -> dict | None:
    if isinstance(data, list):
        return data
    if data.get("jsonrpc") != "2.0":
        raise ValueError("missing or unsupported jsonrpc version")
    if "id" not in data:
        return None
    if "error" in data:
        err = data["error"]
        raise JSONRPCError(err.get("code", -1), err.get("message", "JSON-RPC error"))
    if "result" in data:
        return data
    raise ValueError("response missing both result and error")
