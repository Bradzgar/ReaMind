from __future__ import annotations

import json
from typing import Callable

from .providers.base import LLMProvider, Message, ToolCall
from .tools.registry import ToolRegistry


def run_turn(
    provider: LLMProvider,
    registry: ToolRegistry,
    messages: list[Message],
    reaper_executor: Callable[[ToolCall], dict],
    on_text: Callable[[str], None],
    max_iterations: int = 8,
    local_executor: Callable[[ToolCall], dict] | None = None,
) -> list[Message]:
    for _ in range(max_iterations):
        result = provider.chat(messages, registry.specs())
        if not result.tool_calls:
            text = result.text or ""
            on_text(text)
            messages.append(Message(role="assistant", content=text))
            return messages

        messages.append(Message(role="assistant", content=result.text or "", tool_calls=result.tool_calls))
        for call in result.tool_calls:
            out = _execute_call(registry, call, reaper_executor, local_executor)
            messages.append(
                Message(
                    role="tool",
                    content=json.dumps(out),
                    tool_call_id=call.id,
                    name=call.name,
                )
            )

    stop = "Stopped: reached max tool iterations."
    on_text(stop)
    messages.append(Message(role="assistant", content=stop))
    return messages


def _execute_call(
    registry: ToolRegistry,
    call: ToolCall,
    reaper_executor: Callable[[ToolCall], dict],
    local_executor: Callable[[ToolCall], dict] | None = None,
) -> dict:
    try:
        spec = registry.get(call.name)
    except KeyError:
        return {"ok": False, "error": f"unknown tool: {call.name}"}
    try:
        registry.validate_args(call.name, call.arguments)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    if spec.executor == "reaper":
        return reaper_executor(call)
    if spec.executor == "local" and local_executor is not None:
        return local_executor(call)
    return {"ok": False, "error": f"no executor for tag: {spec.executor}"}
