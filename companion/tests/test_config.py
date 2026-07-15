import pathlib

from reamind.config import Config, default_config, load, save


def test_default_config_has_local_provider():
    cfg = default_config()
    assert cfg.provider.name == "local"
    assert cfg.safety.max_tool_iterations == 8


def test_roundtrip_to_from_dict():
    cfg = default_config()
    cfg.provider.model = "qwen2.5:7b"
    again = Config.from_dict(cfg.to_dict())
    assert again.provider.model == "qwen2.5:7b"
    assert again.safety.confirm_destructive is True


def test_load_creates_default_when_missing(tmp_path: pathlib.Path):
    p = tmp_path / "sub" / "config.json"
    cfg = load(p)
    assert p.exists()
    assert cfg.provider.name == "local"


def test_save_then_load_preserves_changes(tmp_path: pathlib.Path):
    p = tmp_path / "config.json"
    cfg = default_config()
    cfg.projects_roots = ["/music/projects"]
    save(cfg, p)
    assert load(p).projects_roots == ["/music/projects"]


def test_from_dict_tolerates_missing_keys():
    cfg = Config.from_dict({})
    assert cfg.provider.name == "local"
    assert cfg.mcp_servers == []


def test_config_projects_roots_defaults_empty():
    c = Config()
    assert c.projects_roots == []


def test_config_quarantine_dir_default():
    c = Config()
    assert c.quarantine_dir == "~/.config/reamind/quarantine"


def test_config_projects_roots_roundtrips():
    c = Config()
    c.projects_roots = ["/home/user/Projects", "/mnt/media"]
    d = c.to_dict()
    loaded = Config.from_dict(d)
    assert loaded.projects_roots == ["/home/user/Projects", "/mnt/media"]


def test_config_quarantine_dir_roundtrips():
    c = Config()
    c.quarantine_dir = "/tmp/quarantine"
    d = c.to_dict()
    loaded = Config.from_dict(d)
    assert loaded.quarantine_dir == "/tmp/quarantine"
