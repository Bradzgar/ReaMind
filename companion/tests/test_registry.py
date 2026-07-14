import pytest

from reamind.providers.base import ToolSpec
from reamind.tools.reaper_readonly import READONLY_TOOLS, build_registry
from reamind.tools.registry import ToolRegistry


def test_register_and_get():
    reg = ToolRegistry()
    spec = ToolSpec("t", "d", {"type": "object", "properties": {}}, "reaper")
    reg.register(spec)
    assert reg.get("t") is spec


def test_get_unknown_raises():
    reg = ToolRegistry()
    with pytest.raises(KeyError):
        reg.get("nope")


def test_validate_args_requires_required_keys():
    reg = ToolRegistry()
    reg.register(
        ToolSpec(
            "get_track",
            "d",
            {"type": "object", "properties": {"track_guid": {"type": "string"}}, "required": ["track_guid"]},
            "reaper",
        )
    )
    reg.validate_args("get_track", {"track_guid": "{ABC}"})
    with pytest.raises(ValueError):
        reg.validate_args("get_track", {})


def test_build_registry_has_three_readonly_tools():
    reg = build_registry()
    names = {s.name for s in reg.specs()}
    assert names == {"get_project_summary", "list_tracks", "get_track"}
    assert all(s.executor == "reaper" for s in READONLY_TOOLS)
