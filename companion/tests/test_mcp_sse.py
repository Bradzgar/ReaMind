import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from reamind.mcp.sse import SSETransport


class MCPSSEHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/mcp":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.server.sse_wfile = self.wfile
            session_id = "sess_123"
            endpoint = f"http://localhost:{self.server.server_port}/messages/{session_id}"
            self.wfile.write(f"event: endpoint\ndata: {endpoint}\n\n".encode())
            self.wfile.flush()
            try:
                while self.rfile.readline():
                    pass
            except Exception:
                pass
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        sse_wfile = getattr(self.server, "sse_wfile", None)
        if self.path.startswith("/messages/"):
            length = int(self.headers.get("Content-Length", "0"))
            if length > 0:
                body = json.loads(self.rfile.read(length))
                method = body.get("method", "")
                req_id = body.get("id", "")
                if method == "initialize":
                    response = {"jsonrpc": "2.0", "id": req_id, "result": {"capabilities": {"tools": {}}}}
                elif method == "tools/list":
                    response = {"jsonrpc": "2.0", "id": req_id, "result": {"tools": [{"name": "echo", "description": "Echo", "inputSchema": {"type": "object", "properties": {}}}]}}
                elif method == "tools/call":
                    response = {"jsonrpc": "2.0", "id": req_id, "result": {"content": [{"type": "text", "text": "ok"}]}}
                else:
                    response = {"jsonrpc": "2.0", "id": req_id, "result": {}}
                self.send_response(200)
                self.end_headers()
                if sse_wfile is not None:
                    try:
                        sse_wfile.write(f"data: {json.dumps(response)}\n\n".encode())
                        sse_wfile.flush()
                    except Exception:
                        pass
        else:
            self.send_response(404)
            self.end_headers()


def _start_server(port=0):
    server = ThreadingHTTPServer(("127.0.0.1", port), MCPSSEHandler)
    actual_port = server.server_port
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server, actual_port


class TestSSETransport:
    def test_start_discovers_endpoint(self):
        server, port = _start_server()
        try:
            t = SSETransport(f"http://127.0.0.1:{port}/mcp")
            t.start()
            assert t._message_url is not None
            assert f":{port}/messages/" in t._message_url
            t.stop()
        finally:
            server.shutdown()

    def test_send_recv_roundtrip(self):
        server, port = _start_server()
        try:
            t = SSETransport(f"http://127.0.0.1:{port}/mcp")
            t.start()
            t.send({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
            resp = t.recv()
            assert resp["result"]["tools"][0]["name"] == "echo"
            t.stop()
        finally:
            server.shutdown()

    def test_send_raises_if_not_started(self):
        t = SSETransport("http://localhost:9999/mcp")
        with pytest.raises(RuntimeError, match="not started"):
            t.send({"test": 1})

    def test_recv_raises_if_not_started(self):
        t = SSETransport("http://localhost:9999/mcp")
        with pytest.raises(RuntimeError, match="not started"):
            t.recv()
