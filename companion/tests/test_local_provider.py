from reamind.providers import local
from reamind.providers.base import Message, ToolSpec


def test_messages_to_openai_maps_roles_and_tool_calls():
    from reamind.providers.base import ToolCall

    msgs = [
        Message(role="system", content="sys"),
        Message(role="user", content="hi"),
        Message(
            role="assistant",
            content="",
            tool_calls=[ToolCall(id="c1", name="list_tracks", arguments={"a": 1})],
        ),
        Message(role="tool", content='{"ok": true}', tool_call_id="c1", name="list_tracks"),
    ]
    wire = local.messages_to_openai(msgs)
    assert wire[0] == {"role": "system", "content": "sys"}
    assert wire[2]["tool_calls"][0]["function"]["name"] == "list_tracks"
    assert wire[2]["tool_calls"][0]["function"]["arguments"] == '{"a": 1}'
    assert wire[3] == {"role": "tool", "tool_call_id": "c1", "content": '{"ok": true}'}


def test_chat_parses_text_response(monkeypatch):
    def fake_post(url, payload, timeout, api_key=None):
        assert url.endswith("/v1/chat/completions")
        return {"choices": [{"message": {"role": "assistant", "content": "hello there"}}]}

    monkeypatch.setattr(local, "_post_json", fake_post)
    p = local.LocalProvider(base_url="http://localhost:11434", model="m")
    res = p.chat([Message(role="user", content="hi")], [])
    assert res.text == "hello there"
    assert res.tool_calls == []


def test_chat_parses_tool_calls(monkeypatch):
    def fake_post(url, payload, timeout, api_key=None):
        return {
            "choices": [
                {
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "c9",
                                "type": "function",
                                "function": {"name": "list_tracks", "arguments": '{"x": 2}'},
                            }
                        ],
                    }
                }
            ]
        }

    monkeypatch.setattr(local, "_post_json", fake_post)
    p = local.LocalProvider(base_url="http://localhost:11434", model="m")
    spec = ToolSpec("list_tracks", "d", {"type": "object", "properties": {}}, "reaper")
    res = p.chat([Message(role="user", content="hi")], [spec])
    assert res.text is None
    assert len(res.tool_calls) == 1
    assert res.tool_calls[0].id == "c9"
    assert res.tool_calls[0].name == "list_tracks"
    assert res.tool_calls[0].arguments == {"x": 2}


def test_detect_servers_uses_injected_probe():
    reachable = {"http://localhost:11434"}
    found = local.detect_servers(probe=lambda url: url in reachable)
    names = {f["name"] for f in found}
    assert names == {"ollama"}


def test_list_models_extracts_ids():
    def fake_get(url):
        assert url.endswith("/v1/models")
        return {"data": [{"id": "qwen2.5:7b"}, {"id": "llama3.1:8b"}]}

    ids = local.list_models("http://localhost:11434", fetch=fake_get)
    assert ids == ["qwen2.5:7b", "llama3.1:8b"]
