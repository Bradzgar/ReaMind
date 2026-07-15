from reamind.providers.base import ToolSpec


def test_toolspec_destructive_defaults_false():
    spec = ToolSpec(name="foo", description="d", parameters={}, executor="reaper")
    assert spec.destructive is False
    assert spec.return_confirmation is False


def test_toolspec_destructive_true():
    spec = ToolSpec(
        name="delete_track",
        description="d",
        parameters={},
        executor="reaper",
        destructive=True,
    )
    assert spec.destructive is True


def test_toolspec_to_openai_excludes_internal_fields():
    spec = ToolSpec(
        name="foo", description="d",
        parameters={"type": "object", "properties": {}},
        executor="reaper", destructive=True,
    )
    openai = spec.to_openai()
    assert "destructive" not in str(openai)
    assert "return_confirmation" not in str(openai)
    assert openai["function"]["name"] == "foo"
