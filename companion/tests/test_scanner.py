from pathlib import Path
import tempfile

from reamind.library.scanner import scan_root


def _make_rpp(dir_path: Path, name: str, sources: list[str]) -> Path:
    lines = ["<REAPER_PROJECT 0.1"]
    for s in sources:
        ext = s.rsplit(".", 1)[-1].upper()
        stype = {"WAV": "WAVE", "MIDI": "MIDI", "RPP": "RPP"}.get(ext, "WAVE")
        lines.append("  <ITEM")
        lines.append(f"    <SOURCE {stype}")
        lines.append(f'      FILE "{s}"')
        lines.append("    >")
        lines.append("  >")
    lines.append(">")
    rpp = dir_path / name
    rpp.write_text("\n".join(lines))
    return rpp


def test_detects_external_media():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        proj = root / "MyProject"
        proj.mkdir()
        _make_rpp(proj, "song.RPP", ["../OtherFolder/kick.wav"])
        ext_file = root / "OtherFolder" / "kick.wav"
        ext_file.parent.mkdir()
        ext_file.write_bytes(b"audio")

        result = scan_root(root)
        externals = [f for f in result.findings if f.type == "external_media"]
        assert len(externals) == 1
        assert "kick.wav" in externals[0].path


def test_detects_orphaned_media():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        proj = root / "MyProject"
        proj.mkdir()
        _make_rpp(proj, "song.RPP", [])
        (proj / "unused.wav").write_bytes(b"orphan")

        result = scan_root(root)
        orphans = [f for f in result.findings if f.type == "orphaned_media"]
        assert len(orphans) == 1
        assert "unused.wav" in orphans[0].path


def test_detects_regenerable():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        proj = root / "MyProject"
        proj.mkdir()
        _make_rpp(proj, "song.RPP", [])
        (proj / "song.reapeaks").write_bytes(b"peaks")
        (proj / "song.RPP-UNDO").write_bytes(b"undo")
        (proj / "song.RPP-bak").write_bytes(b"bak")

        result = scan_root(root)
        regens = [f for f in result.findings if f.type == "regenerable"]
        assert len(regens) == 3


def test_detects_duplicates():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        a = root / "a"; b = root / "b"
        a.mkdir(); b.mkdir()
        _make_rpp(a, "a.RPP", ["kick.wav"])
        _make_rpp(b, "b.RPP", ["kick.wav"])
        content = b"identical" * 100
        (a / "kick.wav").write_bytes(content)
        (b / "kick.wav").write_bytes(content)

        result = scan_root(root)
        dups = [f for f in result.findings if f.type == "duplicate"]
        assert len(dups) >= 2  # each side reports the other


def test_detects_missing_media():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        proj = root / "MyProject"
        proj.mkdir()
        _make_rpp(proj, "song.RPP", ["gone.wav"])

        result = scan_root(root)
        missing = [f for f in result.findings if f.type == "missing_media"]
        assert len(missing) == 1


def test_detects_nested_project():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        proj = root / "MyProject"
        proj.mkdir()
        sub = proj / "sub"
        sub.mkdir()
        _make_rpp(proj, "main.RPP", [])
        _make_rpp(sub, "nested.RPP", [])

        result = scan_root(root)
        nested = [f for f in result.findings if f.type == "nested_project"]
        assert len(nested) == 1
        assert "nested.RPP" in nested[0].path


def test_summary_counts():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        proj = root / "MyProject"
        proj.mkdir()
        _make_rpp(proj, "song.RPP", ["kick.wav", "snare.wav"])
        (proj / "kick.wav").write_bytes(b"k" * 100)
        (proj / "snare.wav").write_bytes(b"s" * 200)
        (proj / "orphan.wav").write_bytes(b"o" * 50)

        result = scan_root(root)
        assert result.summary["project_count"] == 1
        assert result.summary["media_count"] >= 2
        assert result.summary["orphaned_count"] == 1


def test_empty_root():
    with tempfile.TemporaryDirectory() as d:
        result = scan_root(Path(d))
        assert result.summary["project_count"] == 0
        assert result.findings == []
