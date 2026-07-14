from __future__ import annotations

from ..providers.base import ToolSpec
from .registry import ToolRegistry

READONLY_TOOLS: list[ToolSpec] = [
    ToolSpec(
        name="get_project_summary",
        description="Return a summary of the current REAPER project: track count, tempo, sample rate, and the current selection.",
        parameters={"type": "object", "properties": {}, "required": []},
        executor="reaper",
    ),
    ToolSpec(
        name="list_tracks",
        description="List all tracks with index, name, GUID, color, parent/folder depth, FX names, and sends/receives.",
        parameters={"type": "object", "properties": {}, "required": []},
        executor="reaper",
    ),
    ToolSpec(
        name="get_track",
        description="Return detailed info for one track, addressed by its GUID.",
        parameters={
            "type": "object",
            "properties": {
                "track_guid": {"type": "string", "description": "The track GUID, e.g. {AB12...}"}
            },
            "required": ["track_guid"],
        },
        executor="reaper",
    ),
]


def build_registry() -> ToolRegistry:
    reg = ToolRegistry()
    for spec in READONLY_TOOLS:
        reg.register(spec)
    return reg
