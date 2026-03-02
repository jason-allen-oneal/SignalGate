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
async def test_auth_required_blocks_requests(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
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
            "auth": {
                "enabled": True,
                "header": "x-signalgate-token",
                "token_env": "SIGNALGATE_TOKEN",
                "allow_health": True,
            },
            "upstreams": {
                "allow_http": False,
                "allowlist": {
                    "openai": ["api.openai.com"],
                    "gemini": ["generativelanguage.googleapis.com"],
                },
            },
            "max_body_bytes": 1000000,
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
    monkeypatch.setenv("SIGNALGATE_TOKEN", "secret")

    app = sg_app.create_app()
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r1 = await client.get("/healthz")
            assert r1.status_code == 200

            r2 = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "signalgate/balanced",
                    "messages": [{"role": "user", "content": "hi"}],
                },
            )
            assert r2.status_code == 401

            r3 = await client.post(
                "/v1/chat/completions",
                headers={"x-signalgate-token": "secret"},
                json={
                    "model": "signalgate/balanced",
                    "messages": [{"role": "user", "content": "hi"}],
                },
            )
            # Upstream likely fails due to missing OPENAI_API_KEY, but auth should pass.
            assert r3.status_code in (503, 500)
            assert "_signalgate" in r3.json()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_payload_too_large_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
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
            "max_body_bytes": 10,
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
            # Send a request with an explicit Content-Length to trigger the middleware.
            headers = {"content-type": "application/json", "content-length": "9999"}
            r = await client.post("/v1/chat/completions", headers=headers, content=b"{}")
            assert r.status_code == 413
            assert r.json()["_signalgate"]["error"]["code"] == "SG_PAYLOAD_TOO_LARGE"
