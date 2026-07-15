from __future__ import annotations

from ..providers.base import ToolSpec
from .registry import ToolRegistry


CONSTRUCTION_TOOLS: list[ToolSpec] = [
    # -- Track & folder --
    ToolSpec(
        name="create_track",
        description="Create a new track. Optionally set its name, color, position, and parent folder.",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Track name"},
                "color": {"type": "integer", "description": "REAPER color code (0xRRGGBB)"},
                "position": {"type": "integer", "description": "Insert position (0-based, -1 for last)"},
                "parent_guid": {"type": "string", "description": "GUID of parent folder track"},
            },
            "required": ["name"],
        },
        executor="reaper",
    ),
    ToolSpec(
        name="create_folder",
        description="Create a folder track containing the given child tracks.",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Folder name"},
                "child_guids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "GUIDs of tracks to move into this folder",
                },
            },
            "required": ["name"],
        },
        executor="reaper",
    ),
    ToolSpec(
        name="set_track_props",
        description="Update properties of an existing track. Only specified fields are changed.",
        parameters={
            "type": "object",
            "properties": {
                "track_guid": {"type": "string", "description": "Track GUID"},
                "name": {"type": "string"},
                "color": {"type": "integer"},
                "volume_db": {"type": "number"},
                "pan": {"type": "number", "minimum": -1.0, "maximum": 1.0},
                "record_arm": {"type": "boolean"},
                "input": {"type": "string", "description": "Input assignment (e.g. 'Input: Mono')"},
            },
            "required": ["track_guid"],
        },
        executor="reaper",
    ),
    ToolSpec(
        name="delete_track",
        description="Delete a track by GUID. This is destructive and requires confirmation.",
        parameters={
            "type": "object",
            "properties": {
                "track_guid": {"type": "string", "description": "Track GUID to delete"},
            },
            "required": ["track_guid"],
        },
        executor="reaper",
        destructive=True,
        return_confirmation=True,
    ),
    # -- Routing --
    ToolSpec(
        name="add_send",
        description="Create a send from a source track to a destination track.",
        parameters={
            "type": "object",
            "properties": {
                "src_guid": {"type": "string"},
                "dst_guid": {"type": "string"},
                "gain_db": {"type": "number", "description": "Send gain in dB (default 0)"},
                "is_pre_fader": {"type": "boolean"},
            },
            "required": ["src_guid", "dst_guid"],
        },
        executor="reaper",
    ),
    ToolSpec(
        name="add_receive",
        description="Add a receive on a destination track from a source track.",
        parameters={
            "type": "object",
            "properties": {
                "src_guid": {"type": "string"},
                "dst_guid": {"type": "string"},
                "gain_db": {"type": "number", "description": "Receive gain in dB (default 0)"},
            },
            "required": ["src_guid", "dst_guid"],
        },
        executor="reaper",
    ),
    ToolSpec(
        name="create_sidechain",
        description="Wire a source track into channels 3/4 of a target track's FX instance.",
        parameters={
            "type": "object",
            "properties": {
                "source_guid": {"type": "string", "description": "Source track GUID"},
                "target_guid": {"type": "string", "description": "Target track GUID (where FX lives)"},
                "target_fx_index": {
                    "type": "integer",
                    "description": "FX index on target track (-1 for last)",
                },
            },
            "required": ["source_guid", "target_guid"],
        },
        executor="reaper",
    ),
    # -- Stock FX --
    ToolSpec(
        name="insert_fx",
        description="Insert a stock REAPER effect on a track by friendly name (e.g. 'eq', 'compressor').",
        parameters={
            "type": "object",
            "properties": {
                "track_guid": {"type": "string"},
                "fx_name": {"type": "string", "description": "Friendly name or REAPER identifier"},
                "position": {"type": "integer", "description": "Insert position (-1 for last)"},
            },
            "required": ["track_guid", "fx_name"],
        },
        executor="reaper",
    ),
    ToolSpec(
        name="set_fx_param",
        description="Set a named or indexed parameter on a track's FX instance.",
        parameters={
            "type": "object",
            "properties": {
                "track_guid": {"type": "string"},
                "fx_index": {"type": "integer"},
                "param": {"type": "string", "description": "Parameter name or index"},
                "value": {"type": "number"},
            },
            "required": ["track_guid", "fx_index", "param", "value"],
        },
        executor="reaper",
    ),
    ToolSpec(
        name="list_available_fx",
        description="List all installed FX plugins available in REAPER.",
        parameters={"type": "object", "properties": {}, "required": []},
        executor="reaper",
    ),
    # -- Templates --
    ToolSpec(
        name="apply_template",
        description="Apply a named session template (e.g. 'drum_kit_7mic'). Templates are JSON files in the templates/ directory.",
        parameters={
            "type": "object",
            "properties": {
                "template_name": {"type": "string", "description": "Template file name without .json extension"},
            },
            "required": ["template_name"],
        },
        executor="local",
    ),
    # -- Meta --
    ToolSpec(
        name="undo_point",
        description="Name the current undo point. Each tool call is already undo-wrapped; this lets the LLM add descriptive names.",
        parameters={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Descriptive name for this undo point"},
            },
            "required": ["name"],
        },
        executor="reaper",
    ),
]


def build_construction_registry() -> ToolRegistry:
    reg = ToolRegistry()
    for spec in CONSTRUCTION_TOOLS:
        reg.register(spec)
    return reg
