from __future__ import annotations

import json
import urllib.error
import urllib.request

from .base import ChatResult, LLMProvider, Message, ToolCall, ToolSpec

OLLAMA_URL = "http://localhost:11434"
LMSTUDIO_URL = "http://localhost:1234"


def _post_json(url: str, payload: dict, timeout: float, api_key: str | None = None) -> dict:
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_json(url: str, timeout: float = 5.0) -> dict:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _probe(base_url: str, timeout: float = 1.5) -> bool:
    try:
        _get_json(base_url + "/v1/models", timeout=timeout)
        return True
    except (urllib.error.URLError, OSError, ValueError):
        return False


def messages_to_openai(messages: list[Message]) -> list[dict]:
    wire: list[dict] = []
    for m in messages:
        if m.role == "assistant" and m.tool_calls:
            wire.append(
                {
                    "role": "assistant",
                    "content": m.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.name,
                                "arguments": json.dumps(tc.arguments),
                            },
                        }
                        for tc in m.tool_calls
                    ],
                }
            )
        elif m.role == "tool":
            wire.append(
                {"role": "tool", "tool_call_id": m.tool_call_id, "content": m.content}
            )
        else:
            wire.append({"role": m.role, "content": m.content})
    return wire


class LocalProvider(LLMProvider):
    def __init__(
        self,
        base_url: str,
        model: str,
        tool_mode: str = "native",
        timeout: float = 60.0,
        api_key: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.tool_mode = tool_mode
        self.timeout = timeout
        self.api_key = api_key

    def chat(self, messages: list[Message], tools: list[ToolSpec]) -> ChatResult:
        payload: dict = {
            "model": self.model,
            "messages": messages_to_openai(messages),
            "stream": False,
        }
        if tools:
            payload["tools"] = [t.to_openai() for t in tools]
        url = self.base_url + "/v1/chat/completions"
        resp = _post_json(url, payload, self.timeout, api_key=self.api_key)
        msg = resp["choices"][0]["message"]
        raw_calls = msg.get("tool_calls") or []
        tool_calls: list[ToolCall] = []
        for rc in raw_calls:
            fn = rc.get("function", {})
            args_raw = fn.get("arguments") or "{}"
            try:
                args = json.loads(args_raw) if isinstance(args_raw, str) else args_raw
            except ValueError:
                args = {}
            tool_calls.append(ToolCall(id=rc.get("id", ""), name=fn.get("name", ""), arguments=args))
        text = msg.get("content")
        return ChatResult(text=text, tool_calls=tool_calls)


def detect_servers(probe=_probe) -> list[dict]:
    candidates = [("ollama", OLLAMA_URL), ("lmstudio", LMSTUDIO_URL)]
    return [{"name": name, "base_url": url} for name, url in candidates if probe(url)]


def list_models(base_url: str, fetch=_get_json) -> list[str]:
    data = fetch(base_url.rstrip("/") + "/v1/models")
    return [m["id"] for m in data.get("data", [])]
