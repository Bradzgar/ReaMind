import pathlib

from reamind.bridge import Bridge
from reamind.jsonio import atomic_write_json, read_json


def make(tmp_path: pathlib.Path) -> Bridge:
    b = Bridge(tmp_path / "bridge")
    b.ensure_dirs()
    return b


def test_ensure_dirs_creates_channels(tmp_path):
    b = make(tmp_path)
    for d in (b.inbox, b.chat, b.requests, b.results):
        assert d.is_dir()


def test_push_chat_is_monotonic_and_readable(tmp_path):
    b = make(tmp_path)
    s0 = b.push_chat("assistant", "hello")
    s1 = b.push_chat("status", "thinking", done=False)
    assert s1 == s0 + 1
    files = sorted(b.chat.iterdir())
    assert len(files) == 2
    first = read_json(files[0])
    assert first == {"seq": s0, "role": "assistant", "text": "hello", "done": False}


def test_drain_inbox_reads_in_order_and_deletes(tmp_path):
    b = make(tmp_path)
    atomic_write_json(b.inbox / "000000001.json", {"seq": 1, "text": "first"})
    atomic_write_json(b.inbox / "000000002.json", {"seq": 2, "text": "second"})
    msgs = b.drain_inbox()
    assert [m["text"] for m in msgs] == ["first", "second"]
    assert list(b.inbox.iterdir()) == []


def test_send_request_writes_unique_ids(tmp_path):
    b = make(tmp_path)
    id1 = b.send_request("list_tracks", {}, seq=5)
    id2 = b.send_request("list_tracks", {}, seq=6)
    assert id1 != id2
    payload = read_json(b.requests / f"{id1}.json")
    assert payload["tool"] == "list_tracks"
    assert payload["seq"] == 5
    assert payload["id"] == id1


def test_read_result_returns_none_when_absent_then_consumes(tmp_path):
    b = make(tmp_path)
    assert b.read_result("call_x") is None
    atomic_write_json(b.results / "call_x.json", {"id": "call_x", "ok": True, "result": {"n": 1}})
    got = b.read_result("call_x")
    assert got == {"id": "call_x", "ok": True, "result": {"n": 1}}
    assert b.read_result("call_x") is None


def test_clear_stale_empties_channels_and_resets_seq(tmp_path):
    b = make(tmp_path)
    b.push_chat("assistant", "x")
    atomic_write_json(b.inbox / "000000001.json", {"seq": 1, "text": "y"})
    b.clear_stale()
    assert list(b.chat.iterdir()) == []
    assert list(b.inbox.iterdir()) == []
    assert b.push_chat("assistant", "again") == 0
