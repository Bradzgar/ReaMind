from __future__ import annotations

import abc
from dataclasses import dataclass, field


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict
    executor: str
    destructive: bool = False
    return_confirmation: bool = False

    def to_openai(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class Message:
    role: str
    content: str = ""
    tool_calls: list[ToolCall] | None = None
    tool_call_id: str | None = None
    name: str | None = None


@dataclass
class ChatResult:
    text: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)


class LLMProvider(abc.ABC):
    @abc.abstractmethod
    def chat(self, messages: list[Message], tools: list[ToolSpec]) -> ChatResult:
        ...
