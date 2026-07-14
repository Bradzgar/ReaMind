from __future__ import annotations

import secrets
import shutil
import time
from pathlib import Path

from .jsonio import atomic_write_json, read_json


class Bridge:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.inbox = self.root / "inbox"
        self.chat = self.root / "chat"
        self.requests = self.root / "requests"
        self.results = self.root / "results"
        self.heartbeat = self.root / "heartbeat.json"
        self.session = self.root / "session.json"
        self._chat_seq = 0

    def ensure_dirs(self) -> None:
        for d in (self.inbox, self.chat, self.requests, self.results):
            d.mkdir(parents=True, exist_ok=True)

    def clear_stale(self) -> None:
        for d in (self.inbox, self.chat, self.requests, self.results):
            if d.exists():
                shutil.rmtree(d)
        for f in (self.heartbeat, self.session):
            try:
                f.unlink()
            except FileNotFoundError:
                pass
        self._chat_seq = 0
        self.ensure_dirs()

    def write_session(self, session_id: str) -> None:
        atomic_write_json(self.session, {"session_id": session_id, "started": time.time()})

    def write_heartbeat(self, pid: int) -> None:
        atomic_write_json(self.heartbeat, {"pid": pid, "ts": time.time()})

    def push_chat(self, role: str, text: str, done: bool = False) -> int:
        seq = self._chat_seq
        self._chat_seq += 1
        atomic_write_json(
            self.chat / f"{seq:09d}.json",
            {"seq": seq, "role": role, "text": text, "done": done},
        )
        return seq

    def drain_inbox(self) -> list[dict]:
        out: list[dict] = []
        for f in sorted(self.inbox.glob("*.json")):
            try:
                out.append(read_json(f))
            except (ValueError, OSError):
                pass
            finally:
                try:
                    f.unlink()
                except FileNotFoundError:
                    pass
        return out

    def send_request(self, tool: str, args: dict, seq: int) -> str:
        call_id = "call_" + secrets.token_hex(4)
        atomic_write_json(
            self.requests / f"{call_id}.json",
            {"id": call_id, "seq": seq, "tool": tool, "args": args},
        )
        return call_id

    def read_result(self, call_id: str) -> dict | None:
        f = self.results / f"{call_id}.json"
        if not f.exists():
            return None
        try:
            data = read_json(f)
        except (ValueError, OSError):
            return None
        finally:
            try:
                f.unlink()
            except FileNotFoundError:
                pass
        return data
