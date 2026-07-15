from __future__ import annotations

from pathlib import Path
from typing import Callable

from .config import Config, save as config_save
from .jsonio import atomic_write_json, read_json
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
    config: Config,
    config_path: Path | None,
    bridge_root: Path,
    reaper_executor: Callable[[ToolCall], dict] | None = None,
) -> Callable[[ToolCall], dict]:
    def executor(call: ToolCall) -> dict:
        if call.name == "server_status":
            result = server_status()
            write_status(bridge_root, config)
            return result
        if call.name == "update_provider_config":
            result = update_provider_config(call, config, config_path, config_save)
            write_status(bridge_root, config)
            return result
        if call.name == "apply_template":
            return apply_template(call, reaper_executor)
        return {"ok": False, "error": f"unknown local tool: {call.name}"}

    return executor


def apply_template(call: ToolCall, reaper_executor: Callable[[ToolCall], dict] | None) -> dict:
    template_name = (call.arguments or {}).get("template_name", "")
    if not template_name:
        return {"ok": False, "error": "missing template_name"}

    def _find_templates_dir() -> Path:
        current = Path(__file__).resolve().parent
        for _ in range(10):
            candidate = current / "templates"
            if candidate.is_dir():
                return candidate
            parent = current.parent
            if parent == current:
                break
            current = parent
        return Path(__file__).resolve().parents[2] / "templates"

    templates_dir = _find_templates_dir()
    path = templates_dir / f"{template_name}.json"
    try:
        data = read_json(path)
    except (FileNotFoundError, ValueError):
        return {"ok": False, "error": f"template not found: {template_name}"}

    steps = data if isinstance(data, list) else data.get("steps", [])
    if not steps:
        return {"ok": False, "error": "template has no steps"}

    if reaper_executor is None:
        return {"ok": False, "error": "template execution requires reaper executor"}

    completed = 0
    for step in steps:
        step_name = step.get("tool", "")
        step_args = step.get("args", {})
        step_call = ToolCall(id=f"tmpl_{completed}", name=step_name, arguments=step_args)
        result = reaper_executor(step_call)
        if result.get("ok"):
            completed += 1

    return {
        "ok": True,
        "result": {
            "template_name": template_name,
            "steps_completed": completed,
            "total_steps": len(steps),
        },
    }
