from reamind.theme import (
    DARK_PRESET,
    LIGHT_PRESET,
    PRESETS,
    Theme,
    ThemeColors,
    default_theme,
)


def test_dark_preset_values():
    assert DARK_PRESET.bg == "#1e1e1e"
    assert DARK_PRESET.text == "#d4d4d4"
    assert DARK_PRESET.accent == "#569cd6"
    assert DARK_PRESET.font_scale == 1.0


def test_light_preset_contrasts_with_dark():
    assert LIGHT_PRESET.bg == "#f0f0f0"
    assert LIGHT_PRESET.text == "#1a1a1a"
    assert LIGHT_PRESET.user_bubble == "#d4edda"


def test_presets_dict_has_both():
    assert set(PRESETS.keys()) == {"dark", "light"}
    assert PRESETS["dark"] is DARK_PRESET


def test_theme_roundtrip():
    theme = Theme(preset="dark", colors=DARK_PRESET)
    d = theme.to_dict()
    again = Theme.from_dict(d)
    assert again.preset == "dark"
    assert again.colors.bg == "#1e1e1e"


def test_theme_from_dict_tolerates_empty():
    t = Theme.from_dict({})
    assert t.preset == "dark"
    assert t.colors.bg == "#1e1e1e"


def test_theme_from_dict_tolerates_partial_colors():
    t = Theme.from_dict({"colors": {"bg": "#111111"}})
    assert t.colors.bg == "#111111"
    assert t.colors.text == "#d4d4d4"  # default


def test_default_theme():
    t = default_theme()
    assert t.preset == "dark"
    assert isinstance(t.colors, ThemeColors)
