import threading

from reamind.bridge import Bridge
from reamind.config import default_config
from reamind.providers.base import ChatResult, Message, ToolCall
from reamind.providers.fake import FakeProvider
from reamind.server import Server


def test_reaper_executor_roundtrips_via_bridge(tmp_path):
    bridge = Bridge(tmp_path / "b")
    bridge.ensure_dirs()
    server = Server(default_config(), FakeProvider([]), bridge)
    executor = server.make_reaper_executor(poll_interval=0.001)

    call = ToolCall(id="", name="list_tracks", arguments={})

    def responder():
        import time

        from reamind.jsonio import atomic_write_json, read_json

        for _ in range(1000):
            reqs = list(bridge.requests.glob("*.json"))
            if reqs:
                data = read_json(reqs[0])
                atomic_write_json(
                    bridge.results / f"{data['id']}.json",
                    {"id": data["id"], "ok": True, "result": {"tracks": []}},
                )
                return
            time.sleep(0.001)

    t = threading.Thread(target=responder)
    t.start()
    out = executor(call)
    t.join()
    assert out == {"id": out["id"], "ok": True, "result": {"tracks": []}}


def test_reaper_executor_times_out(tmp_path):
    bridge = Bridge(tmp_path / "b")
    bridge.ensure_dirs()
    cfg = default_config()
    cfg.safety.tool_timeout_s = 0.05
    server = Server(cfg, FakeProvider([]), bridge)
    executor = server.make_reaper_executor(poll_interval=0.001)
    out = executor(ToolCall(id="", name="list_tracks", arguments={}))
    assert out["ok"] is False
    assert "timed out" in out["error"]


def test_handle_user_message_pushes_assistant_chat(tmp_path):
    bridge = Bridge(tmp_path / "b")
    bridge.ensure_dirs()
    provider = FakeProvider([ChatResult(text="hi back", tool_calls=[])])
    server = Server(default_config(), provider, bridge)
    server.handle_user_message("hello")
    chats = sorted(bridge.chat.glob("*.json"))
    from reamind.jsonio import read_json

    payloads = [read_json(f) for f in chats]
    assert any(p["role"] == "assistant" and p["text"] == "hi back" for p in payloads)


def test_tick_drains_inbox(tmp_path):
    bridge = Bridge(tmp_path / "b")
    bridge.ensure_dirs()
    from reamind.jsonio import atomic_write_json

    atomic_write_json(bridge.inbox / "000000001.json", {"seq": 1, "text": "yo"})
    provider = FakeProvider([ChatResult(text="reply", tool_calls=[])])
    server = Server(default_config(), provider, bridge)
    server.tick()
    assert list(bridge.inbox.glob("*.json")) == []
    assert bridge.heartbeat.exists()
