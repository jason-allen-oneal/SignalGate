from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from asgi_lifespan import LifespanManager

from signalgate.app import create_app


def write_json(p: Path, obj: object) -> None:
    p.write_text(json.dumps(obj, indent=2), encoding="utf-8")


@pytest.mark.asyncio
async def test_no_candidates_tools_gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Manifest has an OpenAI model that does NOT support tools.
    manifest = {
        "version": "0.1.0",
        "providerPreference": ["openai"],
        "models": {
            "openai_text": {
                "provider": "openai",
                "model_id": "gpt-4.1-mini",
                "eligible_tiers": ["balanced"],
                "supports": {"tools": False, "json_schema": True, "streaming": False},
                "limits": {"context_window_tokens": 8192, "max_output_tokens": 2048},
                "pricing": {"input_usd_per_1m": 0.0, "output_usd_per_1m": 0.0},
            }
        },
        "tiers": {
            "budget": ["openai_text"],
            "balanced": ["openai_text"],
            "premium": ["openai_text"],
        },
    }
    manifest_path = tmp_path / "manifest.json"
    write_json(manifest_path, manifest)

    config = {
        "version": "0.1.0",
        "server": {"host": "127.0.0.1", "port": 8765},
        "paths": {"manifest_path": str(manifest_path)},
        "features": {"enable_streaming": False},
        "upstreams": {
            "openai": {"base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY"}
        },
    }
    config_path = tmp_path / "config.json"
    write_json(config_path, config)
    monkeypatch.setenv("SIGNALGATE_CONFIG_PATH", str(config_path))

    app = create_app()
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "signalgate/auto",
                    "messages": [{"role": "user", "content": "hi"}],
                    "tools": [
                        {
                            "type": "function",
                            "function": {"name": "x", "parameters": {"type": "object"}},
                        }
                    ],
                },
            )

    assert resp.status_code == 503
    body = resp.json()
    assert body["_signalgate"]["error"]["code"] == "SG_NO_CANDIDATES"


@pytest.mark.asyncio
async def test_models_endpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Minimal config/manifest for app start
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
        "server": {"host": "127.0.0.1", "port": 8765},
        "paths": {"manifest_path": str(manifest_path)},
        "upstreams": {
            "openai": {"base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY"}
        },
    }
    config_path = tmp_path / "config.json"
    write_json(config_path, config)
    monkeypatch.setenv("SIGNALGATE_CONFIG_PATH", str(config_path))

    app = create_app()
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.get("/v1/models")

    assert resp.status_code == 200
    ids = [m["id"] for m in resp.json()["data"]]
    assert "signalgate/auto" in ids
    assert "signalgate/premium" in ids
