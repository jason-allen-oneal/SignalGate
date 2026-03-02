from __future__ import annotations

import json
from pathlib import Path

import pytest

import signalgate.cli as cli


def write_json(p: Path, obj: object) -> None:
    p.write_text(json.dumps(obj, indent=2), encoding="utf-8")


def test_cli_uses_uds_when_configured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # minimal config+manifest just for cli load
    manifest = {
        "version": "0.1.0",
        "providerPreference": ["openai"],
        "models": {},
        "tiers": {"budget": ["x"], "balanced": ["x"], "premium": ["x"]},
    }
    mpath = tmp_path / "manifest.json"
    write_json(mpath, manifest)

    config = {
        "version": "0.1.0",
        "server": {"host": "127.0.0.1", "port": 8765, "uds_path": str(tmp_path / "sg.sock")},
        "paths": {"manifest_path": str(mpath)},
        "upstreams": {
            "openai": {"base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY"},
            "gemini": {"api_key_env": "GEMINI_API_KEY"},
        },
    }
    cpath = tmp_path / "config.json"
    write_json(cpath, config)
    monkeypatch.setenv("SIGNALGATE_CONFIG_PATH", str(cpath))

    called = {}

    def fake_run(app, **kwargs):
        called.update(kwargs)

    monkeypatch.setattr(cli.uvicorn, "run", fake_run)

    cli.main()
    assert called.get("uds") == str(tmp_path / "sg.sock")
