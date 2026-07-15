from __future__ import annotations

import argparse
import os
import time
import uuid
from pathlib import Path
from typing import Callable

from .agent import run_turn
from .bridge import Bridge
from .config import Config, load
from .local_tools import build_library_executor, build_local_executor, write_status
from .providers.base import LLMProvider, Message, ToolCall
from .providers.local import LocalProvider, detect_servers, list_models
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
        self._quarantine_base = Path(self.config.quarantine_dir)
        self.history: list[Message] = [Message(role="system", content=SYSTEM_PROMPT)]
        self._req_seq = 0
        self._config_path = config_path
        self._rebuild_local_executor()

    def _build_merged_local_executor(self, reaper_executor=None):
        existing = build_local_executor(
            self.config, self._config_path, self.bridge.root, reaper_executor
        )
        lib_exec = build_library_executor(self.config, self._quarantine_base)

        def merged(call: ToolCall) -> dict:
            result = existing(call)
            if result.get("ok") is False and "unknown" in str(result.get("error", "")):
                return lib_exec(call)
            return result

        return merged

    def _rebuild_local_executor(self, reaper_executor=None):
        self.local_executor = self._build_merged_local_executor(reaper_executor)

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
        write_status(self.bridge.root, self.config)
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


def build_provider(config: Config) -> LLMProvider:
    p = config.provider
    base_url = p.base_url
    model = p.model
    if not base_url:
        servers = detect_servers()
        if not servers:
            raise RuntimeError(
                "No local model server found. Start Ollama (:11434) or LM Studio (:1234), "
                "or set provider.base_url in the config."
            )
        base_url = servers[0]["base_url"]
    if not model:
        models = list_models(base_url)
        if not models:
            raise RuntimeError(
                f"No models available at {base_url}. Pull a tool-capable model "
                "(e.g. `ollama pull qwen2.5:7b`)."
            )
        model = models[0]
    tool_mode = "native" if p.tool_mode == "auto" else p.tool_mode
    return LocalProvider(base_url=base_url, model=model, tool_mode=tool_mode, api_key=p.api_key)


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
