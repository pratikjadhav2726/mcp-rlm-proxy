"""
Unit tests for configuration loading, including ProxySettings.
"""

import json
import os
import tempfile
import pytest

from mcp_proxy.config import ProxySettings, load_config


class TestProxySettings:
    """Tests for ProxySettings dataclass."""

    def test_defaults(self):
        ps = ProxySettings()
        assert ps.max_response_size == 8000
        assert ps.cache_max_entries == 50
        assert ps.cache_ttl_seconds == 300
        assert ps.enable_auto_truncation is True

    def test_from_dict(self):
        ps = ProxySettings.from_dict({
            "maxResponseSize": 4000,
            "cacheMaxEntries": 100,
            "cacheTTLSeconds": 600,
            "enableAutoTruncation": False,
        })
        assert ps.max_response_size == 4000
        assert ps.cache_max_entries == 100
        assert ps.cache_ttl_seconds == 600
        assert ps.enable_auto_truncation is False

    def test_from_dict_partial(self):
        ps = ProxySettings.from_dict({"maxResponseSize": 1000})
        assert ps.max_response_size == 1000
        # Others are defaults
        assert ps.cache_max_entries == 50


class TestLoadConfig:
    """Tests for load_config returning (servers, proxy_settings)."""

    def test_load_with_proxy_settings(self, tmp_path):
        config = {
            "mcpServers": {
                "test": {
                    "command": "echo",
                    "args": ["hello"],
                }
            },
            "proxySettings": {
                "maxResponseSize": 5000,
                "cacheTTLSeconds": 120,
            },
        }
        config_file = tmp_path / "mcp.json"
        config_file.write_text(json.dumps(config))

        servers, ps = load_config(str(config_file))
        assert len(servers) == 1
        assert servers[0]["name"] == "test"
        assert ps.max_response_size == 5000
        assert ps.cache_ttl_seconds == 120
        assert ps.cache_max_entries == 50  # default

    def test_load_without_proxy_settings(self, tmp_path):
        config = {
            "mcpServers": {
                "test": {"command": "echo", "args": []},
            }
        }
        config_file = tmp_path / "mcp.json"
        config_file.write_text(json.dumps(config))

        servers, ps = load_config(str(config_file))
        assert len(servers) == 1
        # Defaults
        assert ps.max_response_size == 8000

    def test_load_missing_file(self, tmp_path):
        servers, ps = load_config(str(tmp_path / "nonexistent.json"))
        assert servers == []
        assert isinstance(ps, ProxySettings)

    def test_load_empty_mcpServers(self, tmp_path):
        config = {"mcpServers": {}}
        config_file = tmp_path / "mcp.json"
        config_file.write_text(json.dumps(config))

        servers, ps = load_config(str(config_file))
        assert servers == []

    def test_load_missing_mcpServers_key(self, tmp_path):
        config = {"other": "stuff"}
        config_file = tmp_path / "mcp.json"
        config_file.write_text(json.dumps(config))

        with pytest.raises(ValueError, match="Missing 'mcpServers'"):
            load_config(str(config_file))
