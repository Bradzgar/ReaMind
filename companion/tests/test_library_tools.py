from reamind.tools.library import (
    CONSOLIDATE_PROJECT,
    GET_FILE_DETAILS,
    LIST_FINDINGS,
    LIST_QUARANTINE_BATCHES,
    QUARANTINE_FILES,
    RECLAIM_SPACE,
    SCAN_ROOT,
    SET_PROJECTS_ROOT,
    UNNEST_PROJECT,
    build_library_registry,
)


def test_all_nine_names_present():
    specs = [
        SCAN_ROOT, LIST_FINDINGS, GET_FILE_DETAILS,
        LIST_QUARANTINE_BATCHES, QUARANTINE_FILES, RECLAIM_SPACE,
        CONSOLIDATE_PROJECT, UNNEST_PROJECT, SET_PROJECTS_ROOT,
    ]
    for s in specs:
        assert s.name
        assert s.description
        assert s.parameters
        assert s.executor == "local"


def test_registry_registers_all_nine():
    reg = build_library_registry()
    names = {s.name for s in reg.specs()}
    expected = {
        "scan_root", "list_findings", "get_file_details",
        "list_quarantine_batches", "quarantine_files", "reclaim_space",
        "consolidate_project", "unnest_project", "set_projects_root",
    }
    assert names == expected


def test_destructive_tools_flagged():
    reg = build_library_registry()
    destructive = {"quarantine_files", "reclaim_space", "consolidate_project", "unnest_project"}
    for spec in reg.specs():
        if spec.name in destructive:
            assert spec.destructive is True, spec.name
            assert spec.return_confirmation is True, spec.name
        else:
            assert spec.destructive is False, spec.name


def test_scan_root_has_required_params():
    assert "path" in SCAN_ROOT.parameters["required"]
    assert SCAN_ROOT.parameters["properties"]["path"]["type"] == "string"
