from __future__ import annotations

import json
from pathlib import Path

import pytest

from signalgate.errors import SGError
from signalgate.runtime import load_and_validate


def write_json(p: Path, obj: object) -> None:
    p.write_text(json.dumps(obj, indent=2), encoding="utf-8")


@pytest.fixture
def tmp_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Minimal valid manifest
    manifest = {
        "version": "0.1.0",
        "providerPreference": ["openai"],
        "models": {
            "openai_ok": {
                "provider": "openai",
                "model_id": "gpt-4.1-mini",
                "eligible_tiers": ["balanced"],
                "supports": {"tools": False, "json_schema": False, "streaming": False},
                "limits": {"context_window_tokens": 8192, "max_output_tokens": 2048},
                "pricing": {"input_usd_per_1m": 0.0, "output_usd_per_1m": 0.0},
            }
        },
        "tiers": {"budget": ["openai_ok"], "balanced": ["openai_ok"], "premium": ["openai_ok"]},
    }
    manifest_path = tmp_path / "manifest.json"
    write_json(manifest_path, manifest)

    config = {
        "version": "0.1.0",
        "server": {"host": "127.0.0.1", "port": 8765, "log_level": "info"},
        "paths": {"manifest_path": str(manifest_path)},
        "upstreams": {
            "openai": {"base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY"}
        },
    }
    config_path = tmp_path / "config.json"
    write_json(config_path, config)

    monkeypatch.setenv("SIGNALGATE_CONFIG_PATH", str(config_path))
    return config_path


def test_load_and_validate_ok(tmp_config: Path):
    art = load_and_validate()
    assert art.config.version == "0.1.0"
    assert art.manifest_raw["version"] == "0.1.0"
    assert "code=" in art.router_version


def test_invalid_config_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Missing required 'upstreams.openai'
    manifest = {
        "version": "0.1.0",
        "models": {},
        "tiers": {"budget": ["x"], "balanced": ["x"], "premium": ["x"]},
    }
    manifest_path = tmp_path / "manifest.json"
    write_json(manifest_path, manifest)

    config = {
        "version": "0.1.0",
        "server": {"host": "127.0.0.1", "port": 8765},
        "paths": {"manifest_path": str(manifest_path)},
        "upstreams": {},
    }
    config_path = tmp_path / "config.json"
    write_json(config_path, config)
    monkeypatch.setenv("SIGNALGATE_CONFIG_PATH", str(config_path))

    with pytest.raises(SGError):
        load_and_validate()
