import json

from reamind.agent import run_turn
from reamind.providers.base import ChatResult, Message, ToolCall
from reamind.providers.fake import FakeProvider
from reamind.tools.reaper_readonly import build_registry


def test_text_only_turn_calls_on_text_and_returns():
    provider = FakeProvider([ChatResult(text="hello", tool_calls=[])])
    texts = []
    msgs = run_turn(
        provider,
        build_registry(),
        [Message(role="user", content="hi")],
        reaper_executor=lambda call: {"ok": True, "result": {}},
        on_text=texts.append,
    )
    assert texts == ["hello"]
    assert msgs[-1].role == "assistant"
    assert msgs[-1].content == "hello"


def test_reaper_tool_call_is_routed_to_executor_then_finishes():
    provider = FakeProvider(
        [
            ChatResult(text=None, tool_calls=[ToolCall(id="c1", name="list_tracks", arguments={})]),
            ChatResult(text="you have 3 tracks", tool_calls=[]),
        ]
    )
    seen = []

    def executor(call: ToolCall) -> dict:
        seen.append(call.name)
        return {"ok": True, "result": {"tracks": []}}

    texts = []
    msgs = run_turn(provider, build_registry(), [Message(role="user", content="list")], executor, texts.append)
    assert seen == ["list_tracks"]
    assert texts == ["you have 3 tracks"]
    tool_msgs = [m for m in msgs if m.role == "tool"]
    assert tool_msgs[0].tool_call_id == "c1"
    assert json.loads(tool_msgs[0].content) == {"ok": True, "result": {"tracks": []}}


def test_unknown_tool_does_not_call_executor():
    provider = FakeProvider(
        [
            ChatResult(text=None, tool_calls=[ToolCall(id="c1", name="bogus", arguments={})]),
            ChatResult(text="ok", tool_calls=[]),
        ]
    )
    calls = []
    run_turn(provider, build_registry(), [Message(role="user", content="x")], lambda c: calls.append(c) or {}, lambda t: None)
    assert calls == []


def test_missing_required_arg_errors_without_executor():
    provider = FakeProvider(
        [
            ChatResult(text=None, tool_calls=[ToolCall(id="c1", name="get_track", arguments={})]),
            ChatResult(text="done", tool_calls=[]),
        ]
    )
    calls = []
    msgs = run_turn(provider, build_registry(), [Message(role="user", content="x")], lambda c: calls.append(c) or {}, lambda t: None)
    assert calls == []
    tool_msg = [m for m in msgs if m.role == "tool"][0]
    assert json.loads(tool_msg.content)["ok"] is False


def test_max_iterations_guard():
    loop = [ChatResult(text=None, tool_calls=[ToolCall(id="c", name="list_tracks", arguments={})]) for _ in range(10)]
    provider = FakeProvider(loop)
    texts = []
    run_turn(
        provider,
        build_registry(),
        [Message(role="user", content="x")],
        lambda c: {"ok": True, "result": {}},
        texts.append,
        max_iterations=3,
    )
    assert texts and "max tool iterations" in texts[-1]
