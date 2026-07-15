from pathlib import Path
import tempfile

from reamind.rpp import extract_sources, parse_chunks


RPP_SINGLE_WAVE = r'''<REAPER_PROJECT 0.1
  <ITEM
    <SOURCE WAVE
      FILE "media/kick.wav"
    >
  >
>
'''


RPP_MULTIPLE_SOURCES = r'''<REAPER_PROJECT 0.1
  <ITEM
    <SOURCE WAVE
      FILE "/abs/path/snare.wav"
    >
  >
  <ITEM
    <SOURCE MIDI
      FILE "midi/track.mid"
    >
  >
  <ITEM
    <SOURCE RPP
      FILE "../other_project/drums.RPP"
    >
  >
>
'''


RPP_EMPTY = "<REAPER_PROJECT 0.1\n>\n"


def test_parse_chunks_flat():
    text = "<CHUNK\n  KEY VAL\n>\n"
    chunks = parse_chunks(text)
    assert len(chunks) == 1
    assert chunks[0]["name"] == "CHUNK"
    assert "KEY VAL" in chunks[0]["lines"]


def test_parse_chunks_nested():
    chunks = parse_chunks(RPP_SINGLE_WAVE)
    assert chunks[0]["name"] == "REAPER_PROJECT"
    item = chunks[0]["children"][0]
    assert item["name"] == "ITEM"
    source = item["children"][0]
    assert source["name"] == "SOURCE"


def test_extract_sources_wave():
    with tempfile.TemporaryDirectory() as d:
        rpp = Path(d) / "test.RPP"
        rpp.write_text(RPP_SINGLE_WAVE)
        sources = extract_sources(rpp)
        assert len(sources) == 1
        assert sources[0]["type"] == "WAVE"
        assert sources[0]["path"].endswith("media/kick.wav")


def test_extract_sources_relative_path_resolution():
    with tempfile.TemporaryDirectory() as d:
        rpp = Path(d) / "sub" / "test.RPP"
        rpp.parent.mkdir()
        rpp.write_text(RPP_SINGLE_WAVE)
        sources = extract_sources(rpp)
        expected = (Path(d) / "sub" / "media" / "kick.wav").resolve()
        assert Path(sources[0]["path"]).resolve() == expected


def test_extract_sources_preserves_absolute_paths():
    with tempfile.TemporaryDirectory() as d:
        rpp = Path(d) / "test.RPP"
        rpp.write_text(RPP_MULTIPLE_SOURCES)
        sources = extract_sources(rpp)
        assert sources[0]["path"] == "/abs/path/snare.wav"


def test_extract_sources_all_types():
    with tempfile.TemporaryDirectory() as d:
        rpp = Path(d) / "test.RPP"
        rpp.write_text(RPP_MULTIPLE_SOURCES)
        sources = extract_sources(rpp)
        types = {s["type"] for s in sources}
        assert types == {"WAVE", "MIDI", "RPP"}


def test_extract_sources_empty_project():
    with tempfile.TemporaryDirectory() as d:
        rpp = Path(d) / "test.RPP"
        rpp.write_text(RPP_EMPTY)
        assert extract_sources(rpp) == []


def test_extract_sources_missing_file():
    sources = extract_sources(Path("/nonexistent/path.RPP"))
    assert sources == []


def test_parse_chunks_preserves_full_tag():
    chunks = parse_chunks("<SOURCE WAVE\n>\n")
    assert chunks[0]["full_tag"] == "SOURCE WAVE"
    assert chunks[0]["name"] == "SOURCE"
