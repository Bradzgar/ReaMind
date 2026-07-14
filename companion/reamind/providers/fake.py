from __future__ import annotations

from .base import ChatResult, LLMProvider, Message, ToolSpec


class FakeProvider(LLMProvider):
    def __init__(self, scripted: list[ChatResult]) -> None:
        self._scripted = list(scripted)
        self._i = 0
        self.calls: list[tuple[list[Message], list[ToolSpec]]] = []

    def chat(self, messages: list[Message], tools: list[ToolSpec]) -> ChatResult:
        self.calls.append((list(messages), list(tools)))
        assert self._i < len(self._scripted), "FakeProvider exhausted"
        result = self._scripted[self._i]
        self._i += 1
        return result
