from unittest.mock import patch

import pytest

from reamind.config import Config, ProviderConfig
from reamind.provider_factory import build_provider
from reamind.providers.local import LocalProvider


class TestBuildProvider:
    def test_uses_explicit_base_url(self):
        config = Config()
        config.provider.base_url = "https://api.openai.com/v1"
        config.provider.model = "gpt-4"
        config.provider.api_key = "sk-test"
        with patch("reamind.provider_factory.detect_servers") as ds:
            ds.return_value = [{"name": "ollama", "base_url": "http://localhost:11434"}]
            provider = build_provider(config, check_live=False)
        assert isinstance(provider, LocalProvider)
        assert provider.base_url == "https://api.openai.com/v1"
        assert provider.model == "gpt-4"
        assert provider.api_key == "sk-test"

    def test_raises_when_base_url_set_but_no_model(self):
        config = Config()
        config.provider.base_url = "https://api.openai.com/v1"
        config.provider.api_key = "sk-test"
        with pytest.raises(ValueError, match="model"):
            build_provider(config)

    def test_auto_detect_ollama(self):
        config = Config()
        with patch("reamind.provider_factory.detect_servers") as ds:
            ds.return_value = [{"name": "ollama", "base_url": "http://localhost:11434"}]
            with patch("reamind.provider_factory.list_models") as lm:
                lm.return_value = ["llama3"]
                provider = build_provider(config)
        assert provider.base_url == "http://localhost:11434"
        assert provider.model == "llama3"

    def test_auto_detect_no_servers_raises(self):
        config = Config()
        with patch("reamind.provider_factory.detect_servers") as ds:
            ds.return_value = []
            with pytest.raises(RuntimeError, match="No local model server"):
                build_provider(config)

    def test_check_live_success(self):
        config = Config()
        config.provider.base_url = "https://api.example.com/v1"
        config.provider.model = "model-x"
        config.provider.api_key = "k"
        provider = build_provider(config, check_live=False)
        assert isinstance(provider, LocalProvider)

    def test_check_live_failure_raises(self):
        config = Config()
        config.provider.base_url = "http://127.0.0.1:19999/v1"
        config.provider.model = "test"
        provider = build_provider(config, check_live=False)
        assert isinstance(provider, LocalProvider)
