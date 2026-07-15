import json
import sys

import pytest

from reamind.mcp.stdio import StdioTransport


ECHO_SERVER = '''
import sys, json
sys.stdout.reconfigure(line_buffering=True)  # no-op on most Pythons, harmless
while True:
    line = sys.stdin.readline()
    if not line:
        break
    try:
        msg = json.loads(line)
    except json.JSONDecodeError:
        continue
    if msg.get("method") == "exit":
        sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": msg.get("id"), "result": "bye"}) + "\\n")
        sys.stdout.flush()
        break
    response = {"jsonrpc": "2.0", "id": msg.get("id"), "result": msg.get("params", {})}
    sys.stdout.write(json.dumps(response) + "\\n")
    sys.stdout.flush()
'''


class TestStdioTransport:
    def test_start_and_stop(self):
        t = StdioTransport(sys.executable, ["-c", "import time; time.sleep(60)"])
        t.start()
        assert t.alive()
        t.stop()

    def test_send_recv_roundtrip(self):
        t = StdioTransport(sys.executable, ["-c", ECHO_SERVER])
        t.start()
        t.send({"jsonrpc": "2.0", "id": 1, "method": "echo", "params": {"hello": "world"}})
        resp = t.recv()
        assert resp["id"] == 1
        assert resp["result"] == {"hello": "world"}
        t.send({"jsonrpc": "2.0", "id": 2, "method": "exit"})
        bye = t.recv()
        assert bye["result"] == "bye"
        t.stop()

    def test_send_raises_if_not_started(self):
        t = StdioTransport("echo", ["hello"])
        with pytest.raises(RuntimeError, match="not started"):
            t.send({"test": 1})

    def test_recv_raises_if_not_started(self):
        t = StdioTransport("echo", ["hello"])
        with pytest.raises(RuntimeError, match="not started"):
            t.recv()

    def test_recv_raises_if_process_exited(self):
        t = StdioTransport(sys.executable, ["-c", "print('no json')"])
        t.start()
        t._process.wait()
        with pytest.raises(RuntimeError):
            t.recv()

    def test_env_passed_to_subprocess(self):
        t = StdioTransport(sys.executable, [
            "-c",
            "import os, json, sys; "
            "sys.stdout.write(json.dumps({'jsonrpc': '2.0', 'id': 1, 'result': os.environ['REAMIND_TEST']}) + '\\n'); "
            "sys.stdout.flush()"
        ], env={"REAMIND_TEST": "yes"})
        t.start()
        resp = t.recv()
        assert resp["result"] == "yes"
        t.stop()
