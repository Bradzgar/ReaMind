from __future__ import annotations

STATIC_FX_MAP: dict[str, str] = {
    "eq": "ReaEQ",
    "compressor": "ReaComp",
    "gate": "ReaGate",
    "de_esser": "ReaXComp",
    "reverb": "ReaVerb",
    "delay": "ReaDelay",
    "pitch": "ReaPitch",
    "tuner": "ReaTune",
    "synth": "ReaSynth",
    "sampler": "ReaSamplOmatic5000",
}

FRIENDLY_NAMES: list[str] = sorted(STATIC_FX_MAP.keys())

_scanned: dict[str, str] = {}


def resolve_fx_name(identifier: str) -> str:
    lower = identifier.lower()
    if lower in _scanned:
        return _scanned[lower]
    if lower in STATIC_FX_MAP:
        return STATIC_FX_MAP[lower]
    return identifier


def merge_scanned(scanned: list[dict]) -> dict[str, str]:
    merged = dict(STATIC_FX_MAP)
    for entry in (scanned or []):
        name = entry.get("name", "").lower()
        ident = entry.get("identifier", "")
        if name and ident:
            merged[name] = ident
    return merged


def set_scanned_cache(scanned: list[dict]) -> None:
    _scanned.clear()
    for entry in (scanned or []):
        name = entry.get("name", "").lower()
        ident = entry.get("identifier", "")
        if name and ident:
            _scanned[name] = ident
