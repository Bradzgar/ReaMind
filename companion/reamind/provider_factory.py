from __future__ import annotations

from .config import Config
from .providers.base import LLMProvider, Message
from .providers.local import LocalProvider, detect_servers, list_models


def build_provider(config: Config, check_live: bool = False) -> LLMProvider:
    p = config.provider
    tool_mode = "native" if p.tool_mode == "auto" else p.tool_mode

    if p.base_url:
        if not p.model:
            raise ValueError("provider.model must be set when using a cloud endpoint")
        provider = LocalProvider(
            base_url=p.base_url,
            model=p.model,
            tool_mode=tool_mode,
            api_key=p.api_key,
        )
    else:
        servers = detect_servers()
        if not servers:
            raise RuntimeError(
                "No local model server found. Start Ollama (:11434) or LM Studio (:1234), "
                "or set provider.base_url in the config."
            )
        base_url = servers[0]["base_url"]
        model = p.model
        if not model:
            models = list_models(base_url)
            if not models:
                raise RuntimeError(
                    f"No models available at {base_url}. Pull a tool-capable model "
                    "(e.g. `ollama pull qwen2.5:7b`)."
                )
            model = models[0]
        provider = LocalProvider(
            base_url=base_url,
            model=model,
            tool_mode=tool_mode,
            api_key=p.api_key,
        )

    if check_live:
        try:
            provider.chat([Message(role="user", content="ping")], [])
        except Exception as e:
            raise ConnectionError(f"provider connectivity check failed: {e}") from e

    return provider
