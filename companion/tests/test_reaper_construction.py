from reamind.tools.reaper_construction import (
    CONSTRUCTION_TOOLS,
    build_construction_registry,
)


def test_all_specs_have_required_fields():
    for spec in CONSTRUCTION_TOOLS:
        assert spec.name, f"missing name on {spec}"
        assert spec.description, f"missing description on {spec}"
        assert "type" in spec.parameters, f"missing parameters.type on {spec.name}"
        assert spec.executor in ("reaper", "local"), f"bad executor on {spec.name}: {spec.executor}"


def test_track_tools_present():
    names = {s.name for s in CONSTRUCTION_TOOLS}
    for expected in (
        "create_track", "create_folder", "set_track_props", "delete_track",
        "add_send", "add_receive", "create_sidechain",
        "insert_fx", "set_fx_param", "list_available_fx",
        "apply_template", "undo_point",
    ):
        assert expected in names, f"missing {expected}"


def test_delete_track_is_destructive():
    for spec in CONSTRUCTION_TOOLS:
        if spec.name == "delete_track":
            assert spec.destructive is True
            return
    assert False, "delete_track not found"


def test_only_delete_track_is_destructive():
    destructive = [s.name for s in CONSTRUCTION_TOOLS if s.destructive]
    assert destructive == ["delete_track"]


def test_registry_builds_with_all_tools():
    reg = build_construction_registry()
    assert len(reg.specs()) == 12
