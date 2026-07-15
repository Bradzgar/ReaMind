import os
import pathlib
from pathlib import Path

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
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        parent = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        assert c.quarantine_dir == str(parent / "reamind" / "quarantine")
    else:
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


def test_mcp_config_defaults():
    from reamind.config import MCPConfig
    c = MCPConfig()
    assert c.name == ""
    assert c.transport == "stdio"
    assert c.command == ""
    assert c.args == []
    assert c.env is None
    assert c.url == ""


def test_mcp_config_roundtrip_stdio():
    from reamind.config import MCPConfig
    c = MCPConfig(
        name="filesystem",
        transport="stdio",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-filesystem", "/path"],
        env={"NODE_ENV": "production"},
    )
    d = c.to_dict()
    c2 = MCPConfig.from_dict(d)
    assert c2.name == "filesystem"
    assert c2.transport == "stdio"
    assert c2.command == "npx"
    assert c2.args == ["-y", "@modelcontextprotocol/server-filesystem", "/path"]
    assert c2.env == {"NODE_ENV": "production"}
    assert c2.url == ""


def test_mcp_config_roundtrip_sse():
    from reamind.config import MCPConfig
    c = MCPConfig(
        name="remote",
        transport="sse",
        url="https://example.com/mcp",
    )
    d = c.to_dict()
    c2 = MCPConfig.from_dict(d)
    assert c2.name == "remote"
    assert c2.transport == "sse"
    assert c2.url == "https://example.com/mcp"
    assert c2.command == ""


def test_config_mcp_servers_serialized_as_dicts():
    from reamind.config import Config, MCPConfig
    cfg = Config()
    cfg.mcp_servers = [
        MCPConfig(name="srv1", transport="stdio", command="echo", args=["hello"]),
        MCPConfig(name="srv2", transport="sse", url="https://x.com/mcp"),
    ]
    d = cfg.to_dict()
    servers = d["mcp_servers"]
    assert len(servers) == 2
    assert servers[0]["name"] == "srv1"
    assert servers[0]["transport"] == "stdio"
    assert servers[1]["name"] == "srv2"


def test_config_mcp_servers_deserialized_from_dicts():
    from reamind.config import Config, MCPConfig
    d = {
        "mcp_servers": [
            {"name": "srv1", "transport": "stdio", "command": "echo"},
            {"name": "srv2", "transport": "sse", "url": "https://x.com/mcp"},
        ]
    }
    cfg = Config.from_dict(d)
    assert len(cfg.mcp_servers) == 2
    assert isinstance(cfg.mcp_servers[0], MCPConfig)
    assert cfg.mcp_servers[0].name == "srv1"
    assert cfg.mcp_servers[0].transport == "stdio"
    assert isinstance(cfg.mcp_servers[1], MCPConfig)
    assert cfg.mcp_servers[1].url == "https://x.com/mcp"


def test_config_roundtrip_includes_mcp_servers():
    from reamind.config import Config, MCPConfig
    cfg = Config()
    cfg.mcp_servers = [MCPConfig(name="test", command="echo", args=["hi"])]
    d = cfg.to_dict()
    cfg2 = Config.from_dict(d)
    assert len(cfg2.mcp_servers) == 1
    assert cfg2.mcp_servers[0].name == "test"
    assert cfg2.mcp_servers[0].args == ["hi"]
