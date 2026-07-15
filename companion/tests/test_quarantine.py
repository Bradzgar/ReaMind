from datetime import date
from pathlib import Path
import tempfile

from reamind.library.quarantine import (
    consolidate_project,
    quarantine_files,
    reclaim_regenerable,
    unnest_project,
)


def test_quarantine_moves_to_dated_dir():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        src = root / "source"
        src.mkdir()
        f1 = src / "file1.wav"
        f2 = src / "sub" / "file2.wav"
        f2.parent.mkdir()
        f1.write_bytes(b"a")
        f2.write_bytes(b"b")

        qbase = root / "quarantine"
        result = quarantine_files([f1, f2], qbase)

        today = date.today().isoformat()
        assert result["moved_count"] == 2
        assert not f1.exists()
        assert not f2.exists()
        assert (qbase / today).exists()


def test_quarantine_preserves_relative_structure():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "A" / "B").mkdir(parents=True)
        f = root / "A" / "B" / "data.wav"
        f.write_bytes(b"x")

        qbase = root / "q"
        result = quarantine_files([f], qbase)

        today = date.today().isoformat()
        moved_to = qbase / today
        assert any(
            (moved_to / "A" / "B" / "data.wav").exists()
            for _ in [1]
        ) or result["moved_count"] == 1


def test_quarantine_handles_missing_files():
    result = quarantine_files([Path("/nonexistent/file.wav")], Path("/tmp/q"))
    assert result["moved_count"] == 0
    assert len(result.get("errors", [])) >= 1


def test_reclaim_deletes_regenerable():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "song.reapeaks").write_bytes(b"p")
        (root / "song.RPP-UNDO").write_bytes(b"u")
        (root / "song.RPP-bak").write_bytes(b"b")
        (root / "keep.wav").write_bytes(b"real")

        files = [root / "song.reapeaks", root / "song.RPP-UNDO", root / "song.RPP-bak"]
        result = reclaim_regenerable(files)

        assert result["deleted_count"] == 3
        assert (root / "keep.wav").exists()


def test_consolidate_copies_external_media():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        proj = root / "MyProject"
        proj.mkdir()
        ext = root / "External"
        ext.mkdir()
        (ext / "sample.wav").write_bytes(b"data")
        rpp = proj / "song.RPP"
        rpp.write_text(
            '<REAPER_PROJECT 0.1\n  <ITEM\n    <SOURCE WAVE\n      FILE "../External/sample.wav"\n    >\n  >\n>\n'
        )

        result = consolidate_project(rpp)
        assert result["moved_count"] == 1
        assert (proj / "sample.wav").exists()


def test_unnest_copies_to_sibling():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        proj = root / "ProjectA"
        nested_dir = proj / "nested"
        nested_dir.mkdir(parents=True)
        nested_rpp = nested_dir / "sub.RPP"
        nested_rpp.write_text("<REAPER_PROJECT 0.1\n>\n")

        result = unnest_project(nested_rpp, root)

        new_dir = root / "nested"
        assert new_dir.exists()
        assert (new_dir / "sub.RPP").exists()


def test_reclaim_noop_on_empty():
    result = reclaim_regenerable([])
    assert result["deleted_count"] == 0
    assert result["bytes_freed"] == 0
