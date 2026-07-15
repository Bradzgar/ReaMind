from __future__ import annotations

from ..providers.base import ToolSpec


class ToolRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        self._specs[spec.name] = spec

    def get(self, name: str) -> ToolSpec:
        return self._specs[name]

    def specs(self) -> list[ToolSpec]:
        return list(self._specs.values())

    def unregister_prefix(self, prefix: str) -> None:
        target = prefix + "__"
        to_remove = [name for name in self._specs if name.startswith(target)]
        for name in to_remove:
            del self._specs[name]

    def validate_args(self, name: str, args: dict) -> None:
        spec = self.get(name)
        required = spec.parameters.get("required", [])
        missing = [k for k in required if k not in (args or {})]
        if missing:
            raise ValueError(f"{name}: missing required args: {missing}")
