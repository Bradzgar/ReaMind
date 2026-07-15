from __future__ import annotations

import argparse
import os
import sys
import time
import uuid
from pathlib import Path
from typing import Callable

from .agent import run_turn
from .bridge import Bridge
from .config import Config, load
from .local_tools import build_library_executor, build_local_executor, write_status
from .mcp_host import MCPHost
from .providers.base import LLMProvider, Message, ToolCall, ToolSpec
from .provider_factory import build_provider
from .tools.fx_map import resolve_fx_name
from .tools.library import build_library_registry
from .tools.reaper_construction import build_construction_registry
from .tools.reaper_readonly import build_registry

SYSTEM_PROMPT = (
    "You are ReaMind, an assistant embedded in the REAPER digital audio workstation. "
    "You help build sessions, route tracks, and inspect projects by calling tools. "
    "Always address tracks by their GUID, never by bare index. "
    "For multi-step or destructive work, briefly propose a plan before acting."
)


class Server:
    def __init__(self, config: Config, provider: LLMProvider, bridge: Bridge, config_path: Path | None = None) -> None:
        self.config = config
        self.provider = provider
        self.bridge = bridge
        self.registry = build_registry()
        con_reg = build_construction_registry()
        for spec in con_reg.specs():
            self.registry.register(spec)
        lib_reg = build_library_registry()
        for spec in lib_reg.specs():
            self.registry.register(spec)
        self.registry.register(ToolSpec(
            name="get_provider_status",
            description="Get current provider settings and connectivity status",
            parameters={"type": "object", "properties": {}, "required": []},
            executor="local",
            destructive=False,
            return_confirmation=False,
        ))
        self.registry.register(ToolSpec(
            name="switch_provider",
            description="Switch to a different LLM provider or model. Updates base_url, model, api_key, and tool_mode. Requires confirmation — this may incur costs.",
            parameters={
                "type": "object",
                "properties": {
                    "base_url": {"type": "string", "description": "Provider API endpoint"},
                    "model": {"type": "string", "description": "Model name"},
                    "api_key": {"type": "string", "description": "API key for the provider"},
                    "tool_mode": {"type": "string", "description": "Tool calling mode: native, prompted-json, or auto"},
                    "confirm_ok": {"type": "boolean", "description": "Set to true to confirm the switch"},
                },
                "required": ["confirm_ok"],
            },
            executor="local",
            destructive=True,
            return_confirmation=True,
        ))
        self.registry.register(ToolSpec(
            name="list_mcp_servers",
            description="List all connected MCP servers and their tool counts",
            parameters={"type": "object", "properties": {}, "required": []},
            executor="local",
            destructive=False,
            return_confirmation=False,
        ))
        self.registry.register(ToolSpec(
            name="connect_mcp_server",
            description="Connect to an MCP server and register its tools. For stdio servers provide command and args; for SSE servers provide url.",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name for this MCP server (used as tool prefix)"},
                    "transport": {"type": "string", "description": "stdio or sse"},
                    "command": {"type": "string", "description": "Executable (stdio transport)"},
                    "args": {"type": "array", "items": {"type": "string"}, "description": "Arguments (stdio transport)"},
                    "env": {"type": "object", "description": "Environment variables (stdio transport)"},
                    "url": {"type": "string", "description": "SSE endpoint URL (sse transport)"},
                },
                "required": ["name", "transport"],
            },
            executor="local",
            destructive=False,
            return_confirmation=False,
        ))
        self.registry.register(ToolSpec(
            name="disconnect_mcp_server",
            description="Disconnect from an MCP server and unregister its tools. Requires confirmation.",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Name of the MCP server to disconnect"},
                    "confirm_ok": {"type": "boolean", "description": "Set to true to confirm disconnection"},
                },
                "required": ["name", "confirm_ok"],
            },
            executor="local",
            destructive=True,
            return_confirmation=True,
        ))
        self.mcp_host = MCPHost()
        self._init_mcp()
        self._quarantine_base = Path(self.config.quarantine_dir)
        self.history: list[Message] = [Message(role="system", content=SYSTEM_PROMPT)]
        self._req_seq = 0
        self._config_path = config_path
        self._rebuild_local_executor()

    def _build_merged_local_executor(self, reaper_executor=None):
        existing = build_local_executor(
            self.config, self._config_path, self.bridge.root, reaper_executor,
            mcp_host=self.mcp_host,
            rebuild_callback=lambda: self.rebuild_provider(check_live=True),
            registry_register=self.registry.register,
            registry_unregister=self.registry.unregister_prefix,
        )
        lib_exec = build_library_executor(self.config, self._quarantine_base, self._config_path)
        mcp = self.mcp_host.execute if self.mcp_host else lambda c: {"ok": False, "error": "no MCP host"}

        def merged(call: ToolCall) -> dict:
            result = existing(call)
            if result.get("ok") is False and "unknown" in str(result.get("error", "")):
                result = lib_exec(call)
                if result.get("ok") is False and "unknown" in str(result.get("error", "")):
                    return mcp(call)
            return result

        return merged

    def _rebuild_local_executor(self, reaper_executor=None):
        self.local_executor = self._build_merged_local_executor(reaper_executor)

    def rebuild_provider(self, check_live: bool = False) -> None:
        self.provider = build_provider(self.config, check_live=check_live)
        self._rebuild_local_executor()

    def _init_mcp(self) -> None:
        for mcp_config in self.config.mcp_servers:
            try:
                client = self.mcp_host.add_server(mcp_config.name, mcp_config.to_dict())
                for spec in client.list_tools():
                    self.registry.register(spec)
            except Exception as e:
                print(f"[ReaMind] WARNING: failed to connect MCP server '{mcp_config.name}': {e}", file=sys.stderr)

    def make_reaper_executor(
        self,
        poll_interval: float = 0.05,
        now: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> Callable[[ToolCall], dict]:
        def executor(call: ToolCall) -> dict:
            args = dict(call.arguments or {})
            if call.name == "insert_fx" and "fx_name" in args:
                args["fx_name"] = resolve_fx_name(args["fx_name"])
            self._req_seq += 1
            call_id = self.bridge.send_request(call.name, args, self._req_seq)
            deadline = now() + self.config.safety.tool_timeout_s
            while now() < deadline:
                result = self.bridge.read_result(call_id)
                if result is not None:
                    return result
                sleep(poll_interval)
            return {"ok": False, "error": "tool timed out"}

        return executor

    def handle_user_message(self, text: str) -> None:
        self.history.append(Message(role="user", content=text))
        executor = self.make_reaper_executor()
        self._rebuild_local_executor(executor)
        run_turn(
            self.provider,
            self.registry,
            self.history,
            executor,
            on_text=lambda t: self.bridge.push_chat("assistant", t, done=True),
            max_iterations=self.config.safety.max_tool_iterations,
            local_executor=self.local_executor,
            mcp_executor=self.mcp_host.execute,
        )

    def tick(self) -> None:
        for msg in self.bridge.drain_inbox():
            self.handle_user_message(msg.get("text", ""))
        self.bridge.write_heartbeat(os.getpid())

    def run(
        self,
        stop: Callable[[], bool] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        interval: float = 0.1,
    ) -> None:
        self.bridge.clear_stale()
        mcp_srv = [{"name": s["name"], "connected": s["connected"], "tool_count": s["tool_count"]} for s in self.mcp_host.list_servers()]
        write_status(self.bridge.root, self.config, mcp_servers=mcp_srv)
        self.bridge.write_session(uuid.uuid4().hex)
        self._scan_fx()
        stop = stop or (lambda: False)
        while not stop():
            self.tick()
            sleep(interval)

    def _scan_fx(self) -> None:
        try:
            executor = self.make_reaper_executor(poll_interval=0.05)
            call = ToolCall(id="startup_scan", name="list_available_fx", arguments={})
            result = executor(call)
            if result.get("ok"):
                from .tools.fx_map import set_scanned_cache
                fx_list = result.get("result", {}).get("fx_list", [])
                set_scanned_cache(fx_list)
        except Exception:
            pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="reamind.server")
    parser.add_argument("--bridge", default=None)
    parser.add_argument("--config", default=None)
    args = parser.parse_args(argv)

    config = load(Path(args.config) if args.config else None)
    bridge_dir = args.bridge or config.bridge_dir or str(Path(__file__).resolve().parents[2] / "bridge")
    bridge = Bridge(Path(bridge_dir))
    provider = build_provider(config)
    config_path_arg = Path(args.config) if args.config else None
    Server(config, provider, bridge, config_path=config_path_arg).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
