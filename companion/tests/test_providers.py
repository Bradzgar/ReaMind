import pytest

from reamind.providers.base import ChatResult, Message, ToolCall, ToolSpec
from reamind.providers.fake import FakeProvider


def test_toolspec_to_openai_shape():
    spec = ToolSpec(
        name="list_tracks",
        description="List tracks",
        parameters={"type": "object", "properties": {}},
        executor="reaper",
    )
    d = spec.to_openai()
    assert d["type"] == "function"
    assert d["function"]["name"] == "list_tracks"
    assert d["function"]["parameters"] == {"type": "object", "properties": {}}


def test_fake_provider_returns_scripted_in_order():
    r1 = ChatResult(text=None, tool_calls=[ToolCall(id="c1", name="list_tracks", arguments={})])
    r2 = ChatResult(text="done", tool_calls=[])
    fp = FakeProvider([r1, r2])
    out1 = fp.chat([Message(role="user", content="hi")], [])
    out2 = fp.chat([Message(role="user", content="hi")], [])
    assert out1 is r1
    assert out2 is r2
    assert len(fp.calls) == 2


def test_fake_provider_raises_when_exhausted():
    fp = FakeProvider([])
    with pytest.raises(AssertionError):
        fp.chat([], [])
