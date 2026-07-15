from reamind.providers.base import ToolSpec


def test_get_provider_status_spec():
    spec = ToolSpec(
        name="get_provider_status",
        description="Get current provider settings and connectivity status",
        parameters={"type": "object", "properties": {}, "required": []},
        executor="local",
        destructive=False,
        return_confirmation=False,
    )
    assert spec.name == "get_provider_status"
    assert spec.executor == "local"
    assert spec.destructive is False


def test_switch_provider_spec():
    spec = ToolSpec(
        name="switch_provider",
        description="Switch to a different LLM provider or model. Updates base_url, model, api_key, and tool_mode. Requires confirmation — this may incur costs.",
        parameters={
            "type": "object",
            "properties": {
                "base_url": {"type": "string", "description": "Provider API endpoint"},
                "model": {"type": "string", "description": "Model name"},
                "api_key": {"type": "string", "description": "API key for the provider"},
                "tool_mode": {"type": "string", "description": "Tool calling mode: native, prompted-json, or auto"},
                "confirm_ok": {"type": "boolean", "description": "Set to true to confirm the switch"},
            },
            "required": ["confirm_ok"],
        },
        executor="local",
        destructive=True,
        return_confirmation=True,
    )
    assert spec.name == "switch_provider"
    assert spec.executor == "local"
    assert spec.destructive is True
    assert spec.return_confirmation is True
