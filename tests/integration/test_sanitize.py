from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from asgi_lifespan import LifespanManager

import signalgate.app as sg_app


def write_json(p: Path, obj: object) -> None:
    p.write_text(json.dumps(obj, indent=2), encoding="utf-8")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_strip_unknown_fields_does_not_break(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
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
                "pricing": {"input_usd_per_1m": 1.0, "output_usd_per_1m": 1.0},
            }
        },
        "tiers": {"budget": ["openai_ok"], "balanced": ["openai_ok"], "premium": ["openai_ok"]},
    }
    manifest_path = tmp_path / "manifest.json"
    write_json(manifest_path, manifest)

    config = {
        "version": "0.1.0",
        "server": {"host": "127.0.0.1", "port": 8765},
        "security": {
            "auth": {"enabled": False},
            "request_fields": {"mode": "strip_unknown"},
            "upstreams": {
                "allow_http": False,
                "allowlist": {
                    "openai": ["api.openai.com"],
                    "gemini": ["generativelanguage.googleapis.com"],
                },
            },
        },
        "paths": {"manifest_path": str(manifest_path)},
        "routing": {"enable_stickiness": False},
        "upstreams": {
            "openai": {"base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY"},
            "gemini": {"api_key_env": "GEMINI_API_KEY"},
        },
    }
    cfg_path = tmp_path / "config.json"
    write_json(cfg_path, config)
    monkeypatch.setenv("SIGNALGATE_CONFIG_PATH", str(cfg_path))

    app = sg_app.create_app()
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "signalgate/balanced",
                    "messages": [{"role": "user", "content": "hi", "unknown": "x"}],
                    "some_unknown_top_level": 123,
                },
            )

    # It will likely fail upstream (no OPENAI_API_KEY), but should not 400 on unknown fields.
    assert r.status_code in (503, 500)
    body = r.json()
    assert "_signalgate" in body
