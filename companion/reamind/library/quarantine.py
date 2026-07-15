from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

from ..rpp import extract_sources


def quarantine_files(paths: list[Path], quarantine_base: Path) -> dict:
    today = date.today().isoformat()
    dest_dir = quarantine_base / today
    errors = []
    moved = 0

    for src in paths:
        try:
            if not src.exists():
                errors.append(f"Not found: {src}")
                continue
            src = src.resolve()
            dest = dest_dir / src.relative_to(src.anchor)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
            moved += 1
        except Exception as e:
            errors.append(f"Failed: {src}: {e}")

    return {"moved_count": moved, "quarantine_path": str(dest_dir), "errors": errors}


def reclaim_regenerable(files: list[Path]) -> dict:
    deleted = 0
    bytes_freed = 0
    errors = []

    for f in files:
        try:
            if f.exists():
                sz = f.stat().st_size
                f.unlink()
                deleted += 1
                bytes_freed += sz
        except Exception as e:
            errors.append(f"Failed: {f}: {e}")

    return {"deleted_count": deleted, "bytes_freed": bytes_freed, "errors": errors}


def consolidate_project(project_path: Path) -> dict:
    rpp = Path(project_path)
    sources = extract_sources(rpp)
    proj_dir = rpp.parent.resolve()
    moved = 0

    for src in sources:
        src_path = Path(src["path"]).resolve()
        if src_path.is_relative_to(proj_dir):
            continue
        if not src_path.exists():
            continue
        try:
            shutil.copy2(str(src_path), str(proj_dir / src_path.name))
            moved += 1
        except Exception:
            pass

    return {"moved_count": moved, "dest_dir": str(proj_dir)}


def unnest_project(rpp_path: Path, projects_root: Path) -> dict:
    rpp = Path(rpp_path).resolve()
    proj_root = Path(projects_root).resolve()
    name = rpp.parent.name
    new_dir = proj_root / name
    if new_dir.exists():
        new_dir = proj_root / f"{name}_unnested"

    try:
        shutil.copytree(str(rpp.parent), str(new_dir), dirs_exist_ok=True)
    except Exception as e:
        return {"new_path": "", "error": str(e)}

    return {"new_path": str(new_dir / rpp.name)}
