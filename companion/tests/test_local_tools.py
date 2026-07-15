from pathlib import Path

from reamind.config import Config, ProviderConfig, save
from reamind.jsonio import read_json
from reamind.local_tools import (
    build_local_executor,
    server_status,
    update_provider_config,
    write_status,
)
from reamind.providers.base import ToolCall


def test_server_status_returns_servers_list(monkeypatch):
    def fake_detect():
        return [
            {"name": "ollama", "base_url": "http://localhost:11434"},
        ]

    monkeypatch.setattr(
        "reamind.local_tools.detect_servers", fake_detect
    )

    def fake_models(base_url, fetch=None):
        return ["qwen2.5:7b"]

    monkeypatch.setattr(
        "reamind.local_tools.list_models", fake_models
    )

    result = server_status()
    assert result["ok"] is True
    servers = result["result"]["servers"]
    assert len(servers) == 1
    assert servers[0]["name"] == "ollama"
    assert servers[0]["models"] == ["qwen2.5:7b"]


def test_server_status_empty_when_none_found(monkeypatch):
    monkeypatch.setattr(
        "reamind.local_tools.detect_servers", lambda: []
    )
    result = server_status()
    assert result["ok"] is True
    assert result["result"]["servers"] == []


def test_update_provider_config_changes_fields(tmp_path):
    config = Config()
    call = ToolCall(id="c1", name="update_provider_config", arguments={"model": "llama3.1:8b", "base_url": "http://x:1234"})
    result = update_provider_config(call, config, tmp_path / "config.json", save)
    assert result["ok"] is True
    assert config.provider.model == "llama3.1:8b"
    assert config.provider.base_url == "http://x:1234"
    loaded = read_json(tmp_path / "config.json")
    assert loaded["provider"]["model"] == "llama3.1:8b"


def test_write_status_writes_servers_and_current_model(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "reamind.local_tools.detect_servers",
        lambda: [{"name": "ollama", "base_url": "http://localhost:11434"}],
    )
    monkeypatch.setattr(
        "reamind.local_tools.list_models",
        lambda url, fetch=None: ["qwen2.5:7b"],
    )

    config = Config()
    config.provider.model = "qwen2.5:7b"
    config.provider.base_url = "http://localhost:11434"

    bridge = tmp_path / "bridge"
    bridge.mkdir()
    write_status(bridge, config)

    s = read_json(bridge / "status.json")
    assert s["current_model"] == "qwen2.5:7b"
    assert len(s["servers"]) == 1


def test_build_local_executor_routes_tools(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "reamind.local_tools.detect_servers",
        lambda: [{"name": "ollama", "base_url": "http://localhost:11434"}],
    )
    monkeypatch.setattr(
        "reamind.local_tools.list_models",
        lambda url, fetch=None: ["m1"],
    )

    config = Config()
    bridge = tmp_path / "bridge"
    bridge.mkdir()

    exec_fn = build_local_executor(config, tmp_path / "cfg.json", bridge)

    r1 = exec_fn(ToolCall(id="c1", name="server_status", arguments={}))
    assert r1["ok"] is True
    assert "servers" in r1["result"]

    r2 = exec_fn(ToolCall(id="c2", name="update_provider_config", arguments={"model": "x"}))
    assert r2["ok"] is True

    r3 = exec_fn(ToolCall(id="c3", name="bogus", arguments={}))
    assert r3["ok"] is False
    assert "unknown" in r3["error"]


def test_apply_template_reads_and_dispatches_steps(tmp_path, monkeypatch):
    templates_dir = tmp_path / "templates"
    templates_dir.mkdir()
    template_path = templates_dir / "test_tmpl.json"
    import json
    template_path.write_text(json.dumps([
        {"tool": "create_track", "args": {"name": "TestTrack"}},
    ]))

    monkeypatch.setattr("reamind.local_tools.__file__", str(tmp_path / "x" / "y" / "z.py"))

    from reamind.local_tools import apply_template

    call = ToolCall(id="c1", name="apply_template", arguments={"template_name": "test_tmpl"})
    reaper_calls = []

    def fake_executor(c):
        reaper_calls.append(c)
        return {"ok": True, "result": {}}

    result = apply_template(call, fake_executor)
    assert result["ok"] is True
    assert result["result"]["steps_completed"] == 1
    assert len(reaper_calls) == 1
    assert reaper_calls[0].name == "create_track"
