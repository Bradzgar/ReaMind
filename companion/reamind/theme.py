from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ThemeColors:
    bg: str = "#1e1e1e"
    text: str = "#d4d4d4"
    accent: str = "#569cd6"
    user_bubble: str = "#2d5a27"
    assistant_bubble: str = "#1e3a5f"
    error: str = "#f44747"
    font_scale: float = 1.0


DARK_PRESET = ThemeColors()

LIGHT_PRESET = ThemeColors(
    bg="#f0f0f0",
    text="#1a1a1a",
    accent="#007acc",
    user_bubble="#d4edda",
    assistant_bubble="#d6e4f0",
    error="#dc3545",
    font_scale=1.0,
)

PRESETS: dict[str, ThemeColors] = {
    "dark": DARK_PRESET,
    "light": LIGHT_PRESET,
}


@dataclass
class Theme:
    preset: str = "dark"
    colors: ThemeColors = field(default_factory=ThemeColors)

    def to_dict(self) -> dict:
        return {
            "preset": self.preset,
            "colors": {
                "bg": self.colors.bg,
                "text": self.colors.text,
                "accent": self.colors.accent,
                "user_bubble": self.colors.user_bubble,
                "assistant_bubble": self.colors.assistant_bubble,
                "error": self.colors.error,
                "font_scale": self.colors.font_scale,
            },
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Theme":
        d = d or {}
        c = d.get("colors") or {}
        dflt = ThemeColors()
        return cls(
            preset=d.get("preset", "dark"),
            colors=ThemeColors(
                bg=c.get("bg", dflt.bg),
                text=c.get("text", dflt.text),
                accent=c.get("accent", dflt.accent),
                user_bubble=c.get("user_bubble", dflt.user_bubble),
                assistant_bubble=c.get("assistant_bubble", dflt.assistant_bubble),
                error=c.get("error", dflt.error),
                font_scale=c.get("font_scale", dflt.font_scale),
            ),
        )


def default_theme() -> Theme:
    return Theme()
