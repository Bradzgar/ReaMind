#!/usr/bin/env python3
"""ReaMind panel installer — copies Lua files into REAPER's Scripts directory."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path


def find_reaper_resource() -> Path | None:
    candidates: list[Path] = []

    if os.name == "nt":
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            candidates.append(Path(appdata) / "REAPER")
        candidates.append(Path.home() / "AppData" / "Roaming" / "REAPER")
    elif sys.platform == "darwin":
        candidates.append(Path.home() / "Library" / "Application Support" / "REAPER")
    else:
        candidates.append(Path.home() / ".config" / "REAPER")
        candidates.append(Path.home() / ".REAPER")

    for c in candidates:
        if c.is_dir():
            return c
    return None


def check_reaimgui(reaper_dir: Path) -> bool:
    plugins = reaper_dir / "UserPlugins"
    if not plugins.is_dir():
        return False
    for f in plugins.iterdir():
        if f.name.startswith("reaper_imgui"):
            return True
    return False


def panel_files(repo_root: Path) -> list[tuple[Path, str]]:
    panel_dir = repo_root / "panel"
    files: list[tuple[Path, str]] = [
        (panel_dir / "reamind_panel.lua", "reamind_panel.lua"),
        (panel_dir / "helpers.lua", "helpers.lua"),
        (panel_dir / "ipc.lua", "ipc.lua"),
        (panel_dir / "json.lua", "json.lua"),
        (panel_dir / "theme.lua", "theme.lua"),
    ]
    tools_dir = panel_dir / "tools"
    if tools_dir.is_dir():
        for f in tools_dir.glob("*.lua"):
            files.append((f, f"tools/{f.name}"))
    return files


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent

    reaper = find_reaper_resource()
    if reaper is None:
        print("ERROR: REAPER resource directory not found.")
        print("  Expected locations: ~/.config/REAPER (Linux),")
        print("  ~/Library/Application Support/REAPER (macOS),")
        print("  %APPDATA%/REAPER (Windows).")
        print("  Run REAPER once first, or set the path manually.")
        return 1

    scripts_dir = reaper / "Scripts" / "ReaMind"

    if not check_reaimgui(reaper):
        print("WARNING: ReaImGui not detected in UserPlugins.")
        print("  Install it via ReaPack first:")
        print("  Extensions → ReaPack → Browse packages → reaimgui")
        print()

    files = panel_files(repo_root)
    print(f"Installing {len(files)} files to {scripts_dir}")

    scripts_dir.mkdir(parents=True, exist_ok=True)
    for src_path, dst_name in files:
        if not src_path.exists():
            print(f"  SKIP {dst_name} (source not found)")
            continue
        dst_path = scripts_dir / dst_name
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_path, dst_path)
        print(f"  COPY {dst_name}")

    print()
    print("Panel installed. Next steps in REAPER:")
    print("  1. Actions → Show action list")
    print("  2. Click ReaScript: Load...")
    print(f"  3. Select {scripts_dir / 'reamind_panel.lua'}")
    print("  4. Run the action to open the ReaMind panel")
    print()
    print("Optional: add to __startup.lua to open on launch.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
