from __future__ import annotations

import json
import time
import urllib.error
import urllib.request


class SSETransport:
    def __init__(self, url: str) -> None:
        self._url = url.rstrip("/")
        self._message_url: str | None = None
        self._response: urllib.request._UrlopenRet | None = None
        self._buffer = ""

    def start(self) -> bool:
        req = urllib.request.Request(self._url, headers={"Accept": "text/event-stream"})
        try:
            self._response = urllib.request.urlopen(req, timeout=30)
        except (urllib.error.URLError, OSError) as e:
            raise RuntimeError(f"failed to connect to MCP SSE endpoint: {e}") from e
        self._message_url = self._read_endpoint()
        if self._message_url is None:
            raise RuntimeError("no endpoint event received from MCP SSE server")
        return True

    def _read_endpoint(self) -> str | None:
        deadline = time.time() + 10
        event_type = None
        data = None
        while time.time() < deadline:
            line = self._read_sse_line()
            if line == "":
                if event_type == "endpoint" and data is not None:
                    return data
                event_type = None
                data = None
            elif line.startswith("event: "):
                event_type = line[7:].strip()
            elif line.startswith("data: "):
                data = line[6:].strip()
            if event_type == "endpoint" and data is not None:
                return data
        return None

    def _read_sse_line(self) -> str:
        line = ""
        while True:
            ch = self._response.read(1)
            if not ch:
                return ""
            ch = ch.decode("utf-8", errors="replace")
            if ch == "\n":
                return line.rstrip("\r")
            line += ch

    def _read_sse_event(self) -> str | None:
        data = None
        while True:
            line = self._read_sse_line()
            if line == "":
                if data is not None:
                    return data
                if self._response is None or self._response.closed:
                    return None
            elif line.startswith("data: "):
                data = line[6:].strip()

    def stop(self) -> None:
        if self._response is not None:
            try:
                self._response.close()
            except Exception:
                pass
            self._response = None

    def send(self, msg: dict) -> None:
        if self._message_url is None:
            raise RuntimeError("transport not started")
        data = json.dumps(msg).encode("utf-8")
        req = urllib.request.Request(
            self._message_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            resp = urllib.request.urlopen(req, timeout=30)
            resp.close()
        except (urllib.error.URLError, OSError) as e:
            raise RuntimeError(f"failed to send MCP message: {e}") from e

    def recv(self) -> dict:
        if self._response is None:
            raise RuntimeError("transport not started")
        data = self._read_sse_event()
        if data is None:
            raise RuntimeError("SSE stream closed")
        try:
            return json.loads(data)
        except json.JSONDecodeError as e:
            raise ValueError(f"invalid JSON from MCP SSE: {e}") from e

    def alive(self) -> bool:
        return self._response is not None and not self._response.closed
