from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Callable

from .config import Config, save as config_save
from .jsonio import atomic_write_json, read_json
from .library.quarantine import (
    consolidate_project,
    quarantine_files as _quarantine_files,
    reclaim_regenerable,
    unnest_project,
)
from .library.scanner import scan_root
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


def write_status(bridge_root: Path, config: Config, servers: list | None = None, mcp_servers: list | None = None) -> None:
    if servers is None:
        status_result = server_status()
        servers = status_result["result"]["servers"]
    status_dict = {
        "servers": servers,
        "current_model": config.provider.model,
        "current_base_url": config.provider.base_url,
    }
    if mcp_servers is not None:
        status_dict["mcp_servers"] = mcp_servers
    atomic_write_json(bridge_root / "status.json", status_dict)


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


def build_library_executor(
    config: Config, quarantine_base: Path, config_path: Path | None = None
) -> Callable[[ToolCall], dict]:
    quarantine_base = Path(quarantine_base).expanduser()

    def executor(call: ToolCall) -> dict:
        name = call.name
        args = call.arguments or {}

        if name == "scan_root":
            path = Path(args.get("path", ""))
            result = scan_root(path)
            return {"ok": True, "result": {
                "root": result.root,
                "project_count": result.summary["project_count"],
                "media_count": result.summary["media_count"],
                "total_size_bytes": result.summary["total_size_bytes"],
                "finding_counts": {
                    k.replace("_count", ""): v
                    for k, v in result.summary.items()
                    if k.endswith("_count")
                },
            }}

        if name == "list_findings":
            root_path = Path(args.get("root", ""))
            filter_type = args.get("type")
            result = scan_root(root_path)
            findings_list = result.findings
            if filter_type:
                findings_list = [f for f in findings_list if f.type == filter_type]
            return {"ok": True, "result": {
                "findings": [
                    {
                        "type": f.type, "path": f.path,
                        "reason": f.reason, "size_bytes": f.size_bytes,
                        "related": f.related,
                    }
                    for f in findings_list
                ],
            }}

        if name == "get_file_details":
            p = Path(args.get("path", ""))
            try:
                st = p.stat()
                fhash = None
                if p.is_file():
                    fhash = hashlib.sha256(p.read_bytes()).hexdigest()
                return {"ok": True, "result": {
                    "path": str(p), "size_bytes": st.st_size,
                    "modified": st.st_mtime, "hash": fhash, "exists": p.exists(),
                }}
            except OSError as e:
                return {"ok": False, "error": str(e)}

        if name == "list_quarantine_batches":
            batches = []
            if quarantine_base.exists():
                for entry in sorted(quarantine_base.iterdir(), reverse=True):
                    if entry.is_dir():
                        fc = sum(1 for _ in entry.rglob("*") if _.is_file())
                        sz = sum(_.stat().st_size for _ in entry.rglob("*") if _.is_file())
                        batches.append({"date": entry.name, "file_count": fc, "total_bytes": sz})
            return {"ok": True, "result": {"batches": batches}}

        if name == "quarantine_files":
            paths = [Path(p) for p in args.get("paths", [])]
            result = _quarantine_files(paths, quarantine_base)
            return {"ok": True, "result": result}

        if name == "reclaim_space":
            root_dir = args.get("root")
            roots_to_scan = [Path(root_dir)] if root_dir else [Path(r) for r in config.projects_roots]
            regenerable = []
            for rt in roots_to_scan:
                rt = Path(rt)
                if rt.is_dir():
                    for entry in rt.rglob("*"):
                        if entry.is_file():
                            n = entry.name
                            if n.endswith(".reapeaks") or n.endswith(".RPP-UNDO") or n.endswith(".RPP-bak"):
                                regenerable.append(entry)
            result = reclaim_regenerable(regenerable)
            return {"ok": True, "result": result}

        if name == "consolidate_project":
            result = consolidate_project(Path(args["project_path"]))
            return {"ok": True, "result": result}

        if name == "unnest_project":
            roots = config.projects_roots or [str(Path(args["project_path"]).parent.parent)]
            proj_root = Path(roots[0])
            result = unnest_project(Path(args["project_path"]), proj_root)
            if "error" in result:
                return {"ok": False, "error": result["error"]}
            return {"ok": True, "result": result}

        if name == "set_projects_root":
            path = args.get("path", "")
            if path and path not in config.projects_roots:
                config.projects_roots.append(path)
                if config_path is not None:
                    config_save(config, config_path)
            return {"ok": True, "result": {"message": f"Added {path} to projects_roots"}}

        return {"ok": False, "error": f"unknown library tool: {name}"}

    return executor
