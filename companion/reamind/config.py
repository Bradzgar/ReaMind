from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .jsonio import atomic_write_json, read_json
from .theme import Theme, default_theme

if os.name == "nt":
    appdata = os.environ.get("APPDATA")
    DEFAULT_CONFIG_PATH = Path(appdata) / "reamind" / "config.json" if appdata else Path.home() / "reamind" / "config.json"
else:
    DEFAULT_CONFIG_PATH = Path.home() / ".config" / "reamind" / "config.json"


@dataclass
class ProviderConfig:
    name: str = "local"
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    tool_mode: str = "auto"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "model": self.model,
            "base_url": self.base_url,
            "api_key": self.api_key,
            "tool_mode": self.tool_mode,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "ProviderConfig":
        d = d or {}
        return cls(
            name=d.get("name", "local"),
            model=d.get("model"),
            base_url=d.get("base_url"),
            api_key=d.get("api_key"),
            tool_mode=d.get("tool_mode", "auto"),
        )


@dataclass
class MCPConfig:
    name: str = ""
    transport: str = "stdio"
    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict | None = None
    url: str = ""

    def to_dict(self) -> dict:
        d = {"name": self.name, "transport": self.transport}
        if self.command:
            d["command"] = self.command
        if self.args:
            d["args"] = self.args
        if self.env is not None:
            d["env"] = self.env
        if self.url:
            d["url"] = self.url
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "MCPConfig":
        d = d or {}
        return cls(
            name=d.get("name", ""),
            transport=d.get("transport", "stdio"),
            command=d.get("command", ""),
            args=d.get("args", []),
            env=d.get("env"),
            url=d.get("url", ""),
        )


@dataclass
class SafetyConfig:
    confirm_destructive: bool = True
    max_tool_iterations: int = 8
    tool_timeout_s: float = 30.0

    def to_dict(self) -> dict:
        return {
            "confirm_destructive": self.confirm_destructive,
            "max_tool_iterations": self.max_tool_iterations,
            "tool_timeout_s": self.tool_timeout_s,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SafetyConfig":
        d = d or {}
        return cls(
            confirm_destructive=d.get("confirm_destructive", True),
            max_tool_iterations=d.get("max_tool_iterations", 8),
            tool_timeout_s=d.get("tool_timeout_s", 30.0),
        )


@dataclass
class Config:
    provider: ProviderConfig = field(default_factory=ProviderConfig)
    theme: Theme = field(default_factory=default_theme)
    projects_roots: list[str] = field(default_factory=list)
    quarantine_dir: str = "~/.config/reamind/quarantine"
    mcp_servers: list[MCPConfig] = field(default_factory=list)
    templates_dir: str = ""
    safety: SafetyConfig = field(default_factory=SafetyConfig)
    bridge_dir: str = ""

    def to_dict(self) -> dict:
        return {
            "provider": self.provider.to_dict(),
            "theme": self.theme.to_dict(),
            "projects_roots": self.projects_roots,
            "quarantine_dir": self.quarantine_dir,
            "mcp_servers": [s.to_dict() for s in self.mcp_servers],
            "templates_dir": self.templates_dir,
            "safety": self.safety.to_dict(),
            "bridge_dir": self.bridge_dir,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Config":
        d = d or {}
        return cls(
            provider=ProviderConfig.from_dict(d.get("provider", {})),
            theme=Theme.from_dict(d.get("theme", {})),
            projects_roots=d.get("projects_roots", []),
            quarantine_dir=d.get("quarantine_dir", "~/.config/reamind/quarantine"),
            mcp_servers=[MCPConfig.from_dict(s) for s in d.get("mcp_servers", [])],
            templates_dir=d.get("templates_dir", ""),
            safety=SafetyConfig.from_dict(d.get("safety", {})),
            bridge_dir=d.get("bridge_dir", ""),
        )


def default_config() -> Config:
    return Config()


def load(path: Path | None = None) -> Config:
    path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    if not path.exists():
        cfg = default_config()
        save(cfg, path)
        return cfg
    return Config.from_dict(read_json(path))


def save(cfg: Config, path: Path | None = None) -> None:
    path = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    atomic_write_json(path, cfg.to_dict())
