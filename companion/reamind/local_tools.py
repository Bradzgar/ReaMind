from __future__ import annotations

from pathlib import Path
from typing import Callable

from .config import Config, save as config_save
from .jsonio import atomic_write_json
from .providers.base import ToolCall
from .providers.local import detect_servers, list_models


def server_status() -> dict:
    servers = detect_servers()
    result_servers = []
    for s in servers:
        try:
            models = list_models(s["base_url"])
        except Exception:
            models = []
        result_servers.append(
            {"name": s["name"], "base_url": s["base_url"], "models": models}
        )
    return {"ok": True, "result": {"servers": result_servers}}


def update_provider_config(
    call: ToolCall, config: Config, config_path: Path | None, save_fn: Callable
) -> dict:
    args = call.arguments or {}
    for field in ("model", "base_url", "api_key", "tool_mode"):
        if field in args:
            setattr(config.provider, field, args[field])
    save_fn(config, config_path)
    return {"ok": True, "result": {"message": "provider config updated"}}


def write_status(bridge_root: Path, config: Config, servers: list | None = None) -> None:
    if servers is None:
        status_result = server_status()
        servers = status_result["result"]["servers"]
    atomic_write_json(
        bridge_root / "status.json",
        {
            "servers": servers,
            "current_model": config.provider.model,
            "current_base_url": config.provider.base_url,
        },
    )


def build_local_executor(
    config: Config, config_path: Path | None, bridge_root: Path
) -> Callable[[ToolCall], dict]:
    def executor(call: ToolCall) -> dict:
        if call.name == "server_status":
            result = server_status()
            write_status(bridge_root, config, servers=result["result"]["servers"])
            return result
        if call.name == "update_provider_config":
            result = update_provider_config(call, config, config_path, config_save)
            write_status(bridge_root, config)
            return result
        return {"ok": False, "error": f"unknown local tool: {call.name}"}

    return executor
