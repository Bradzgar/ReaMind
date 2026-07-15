from reamind.tools.fx_map import (
    FRIENDLY_NAMES,
    STATIC_FX_MAP,
    merge_scanned,
    resolve_fx_name,
    set_scanned_cache,
)


def test_static_map_has_expected_keys():
    assert STATIC_FX_MAP["eq"] == "ReaEQ"
    assert STATIC_FX_MAP["compressor"] == "ReaComp"
    assert STATIC_FX_MAP["gate"] == "ReaGate"
    assert STATIC_FX_MAP["reverb"] == "ReaVerb"
    assert STATIC_FX_MAP["delay"] == "ReaDelay"


def test_resolve_returns_identifier_as_is():
    assert resolve_fx_name("ReaEQ") == "ReaEQ"
    assert resolve_fx_name("ReaComp") == "ReaComp"


def test_resolve_looks_up_friendly_name():
    assert resolve_fx_name("eq") == "ReaEQ"
    assert resolve_fx_name("compressor") == "ReaComp"


def test_resolve_unknown_friendly_returns_as_is():
    assert resolve_fx_name("some_obscure_fx") == "some_obscure_fx"


def test_merge_scanned_adds_new_entries():
    scanned = [
        {"name": "ValhallaVintageVerb", "identifier": "VST3: ValhallaVintageVerb"},
        {"name": "Serum", "identifier": "VST3: Serum (Xfer Records)"},
    ]
    merged = merge_scanned(scanned)
    assert merged["eq"] == "ReaEQ"  # static preserved
    assert merged["valhallavintageverb"] == "VST3: ValhallaVintageVerb"
    assert merged["serum"] == "VST3: Serum (Xfer Records)"


def test_merge_scanned_empty_returns_static():
    merged = merge_scanned([])
    assert merged["eq"] == "ReaEQ"
    assert len(merged) == len(STATIC_FX_MAP)


def test_friendly_names_list():
    assert "eq" in FRIENDLY_NAMES
    assert "compressor" in FRIENDLY_NAMES
    assert "reverb" in FRIENDLY_NAMES


def test_set_scanned_cache_updates_resolve():
    set_scanned_cache([
        {"name": "myplugin", "identifier": "VST: MyPlugin"},
    ])
    assert resolve_fx_name("myplugin") == "VST: MyPlugin"
    # reset for other tests
    set_scanned_cache([])
