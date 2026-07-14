import json
import pathlib

import pytest

from reamind.jsonio import atomic_write_json, read_json


def test_write_then_read_roundtrip(tmp_path: pathlib.Path):
    p = tmp_path / "x.json"
    atomic_write_json(p, {"a": 1, "b": [1, 2, 3]})
    assert read_json(p) == {"a": 1, "b": [1, 2, 3]}


def test_write_leaves_no_temp_files(tmp_path: pathlib.Path):
    p = tmp_path / "x.json"
    atomic_write_json(p, {"a": 1})
    names = [f.name for f in tmp_path.iterdir()]
    assert names == ["x.json"]


def test_read_missing_raises(tmp_path: pathlib.Path):
    with pytest.raises(FileNotFoundError):
        read_json(tmp_path / "nope.json")


def test_write_is_valid_json_on_disk(tmp_path: pathlib.Path):
    p = tmp_path / "x.json"
    atomic_write_json(p, {"k": "v"})
    assert json.loads(p.read_text()) == {"k": "v"}
