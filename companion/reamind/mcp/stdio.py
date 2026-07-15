from __future__ import annotations

import json
import os
import subprocess


class StdioTransport:
    def __init__(self, command: str, args: list[str], env: dict[str, str] | None = None) -> None:
        self._command = command
        self._args = args
        self._env = env
        self._process: subprocess.Popen | None = None

    def start(self) -> bool:
        run_env = None
        if self._env is not None:
            run_env = os.environ.copy()
            run_env.update(self._env)
        try:
            self._process = subprocess.Popen(
                [self._command] + self._args,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=run_env,
            )
        except (FileNotFoundError, PermissionError) as e:
            raise RuntimeError(f"failed to start MCP server: {e}") from e
        return True

    def stop(self) -> None:
        if self._process is None:
            return
        try:
            self._process.terminate()
            self._process.wait(timeout=5)
        except (subprocess.TimeoutExpired, ProcessLookupError):
            try:
                self._process.kill()
                self._process.wait(timeout=2)
            except (subprocess.TimeoutExpired, ProcessLookupError):
                pass
        self._process = None

    def send(self, msg: dict) -> None:
        if self._process is None:
            raise RuntimeError("transport not started")
        line = json.dumps(msg) + "\n"
        try:
            self._process.stdin.write(line)
            self._process.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            raise RuntimeError(f"failed to write to MCP server: {e}") from e

    def recv(self) -> dict:
        if self._process is None:
            raise RuntimeError("transport not started")
        if self._process.poll() is not None:
            raise RuntimeError("MCP server process has exited")
        line = self._process.stdout.readline()
        if not line:
            raise RuntimeError("MCP server process has exited")
        try:
            return json.loads(line)
        except json.JSONDecodeError as e:
            raise ValueError(f"invalid JSON from MCP server: {e}") from e

    def alive(self) -> bool:
        return self._process is not None and self._process.poll() is None
