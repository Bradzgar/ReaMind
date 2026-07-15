from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from ..rpp import extract_sources


def _is_regenerable(path: Path) -> bool:
    n = path.name
    return n.endswith(".reapeaks") or n.endswith(".RPP-UNDO") or n.endswith(".RPP-bak")


def _is_media(path: Path) -> bool:
    return path.suffix.lower() in {
        ".wav", ".aiff", ".aif", ".flac", ".mp3", ".ogg", ".mid", ".midi", ".m4a", ".wma",
    }


@dataclass
class Finding:
    type: str
    path: str
    reason: str
    size_bytes: int = 0
    related: list[str] | None = None


@dataclass
class ProjectInfo:
    path: str
    source_count: int
    sources: list[dict] = field(default_factory=list)


@dataclass
class ScanResult:
    root: str
    projects: list[ProjectInfo] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    summary: dict = field(default_factory=dict)


def scan_root(root: Path) -> ScanResult:
    root = root.resolve()
    if not root.is_dir():
        return ScanResult(root=str(root), summary=_empty_summary())

    findings: list[Finding] = []
    rpp_files: list[Path] = []
    media_files: list[Path] = []

    for entry in root.rglob("*"):
        if not entry.is_file():
            continue
        suffix = entry.suffix.lower()
        if suffix == ".rpp":
            rpp_files.append(entry)
        elif _is_media(entry):
            media_files.append(entry)
        if _is_regenerable(entry):
            findings.append(Finding(
                type="regenerable",
                path=str(entry),
                reason=f"Regenerable file: {entry.name}",
                size_bytes=entry.stat().st_size,
            ))

    all_refs: set[str] = set()
    projects: list[ProjectInfo] = []

    for rpp_path in rpp_files:
        sources = extract_sources(rpp_path)
        proj_dir = rpp_path.parent
        projects.append(ProjectInfo(
            path=str(rpp_path),
            source_count=len(sources),
            sources=sources,
        ))
        for src in sources:
            src_path = Path(src["path"])
            all_refs.add(str(src_path.resolve()))
            if not src_path.is_relative_to(proj_dir):
                findings.append(Finding(
                    type="external_media",
                    path=str(src_path),
                    reason=f"Referenced by {rpp_path.name} from outside its project directory",
                    related=[str(rpp_path)],
                ))
            if not src_path.exists():
                findings.append(Finding(
                    type="missing_media",
                    path=str(src_path),
                    reason=f"Referenced by {rpp_path.name} but file not found",
                ))

    orphaned = set()
    for mf in media_files:
        if str(mf.resolve()) not in all_refs:
            orphaned.add(str(mf))
            findings.append(Finding(
                type="orphaned_media",
                path=str(mf),
                reason="Not referenced by any .RPP in this root",
                size_bytes=mf.stat().st_size,
            ))

    rpp_dirs = {rp.parent for rp in rpp_files}
    for rpp in rpp_files:
        for other_dir in rpp_dirs:
            if other_dir != rpp.parent and rpp.parent.is_relative_to(other_dir):
                findings.append(Finding(
                    type="nested_project",
                    path=str(rpp),
                    reason=f"Nested inside {other_dir}",
                ))
                break

    by_size: dict[int, list[Path]] = defaultdict(list)
    for mf in media_files:
        try:
            by_size[mf.stat().st_size].append(mf)
        except OSError:
            pass

    dup_groups = []
    for sz, files in by_size.items():
        if len(files) < 2:
            continue
        by_quick: dict[str, list[Path]] = defaultdict(list)
        for f in files:
            try:
                with open(f, "rb") as fh:
                    data = fh.read(65536)
                by_quick[hashlib.sha256(data).hexdigest()].append(f)
            except OSError:
                pass
        for files2 in by_quick.values():
            if len(files2) < 2:
                continue
            by_full: dict[str, list[Path]] = defaultdict(list)
            for f in files2:
                try:
                    by_full[hashlib.sha256(f.read_bytes()).hexdigest()].append(f)
                except OSError:
                    pass
            for group in by_full.values():
                if len(group) >= 2:
                    dup_groups.append(group)

    for group in dup_groups:
        paths = [str(p) for p in group]
        for i, p in enumerate(group):
            findings.append(Finding(
                type="duplicate",
                path=str(p),
                reason=f"Duplicate of {len(group)-1} other file(s)",
                size_bytes=p.stat().st_size if p.exists() else 0,
                related=paths[:i] + paths[i+1:],
            ))

    total_size = sum(f.stat().st_size for f in root.rglob("*") if f.is_file())
    result = ScanResult(
        root=str(root),
        projects=projects,
        findings=findings,
        summary={
            "project_count": len(rpp_files),
            "media_count": len(media_files),
            "total_size_bytes": total_size,
            "orphaned_count": sum(1 for f in findings if f.type == "orphaned_media"),
            "regenerable_count": sum(1 for f in findings if f.type == "regenerable"),
            "duplicate_count": sum(1 for f in findings if f.type == "duplicate"),
            "nested_count": sum(1 for f in findings if f.type == "nested_project"),
            "external_count": sum(1 for f in findings if f.type == "external_media"),
            "missing_count": sum(1 for f in findings if f.type == "missing_media"),
        },
    )
    return result


def _empty_summary() -> dict:
    return {
        "project_count": 0, "media_count": 0, "total_size_bytes": 0,
        "orphaned_count": 0, "regenerable_count": 0, "duplicate_count": 0,
        "nested_count": 0, "external_count": 0, "missing_count": 0,
    }
