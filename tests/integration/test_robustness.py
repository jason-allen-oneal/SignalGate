from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
import pytest
from asgi_lifespan import LifespanManager

import signalgate.app as sg_app
from signalgate.errors import SGError


def write_json(p: Path, obj: object) -> None:
    p.write_text(json.dumps(obj, indent=2), encoding="utf-8")


class BlockingUpstreams:
    def __init__(self, evt: asyncio.Event):
        self.evt = evt

    async def aclose(self) -> None:
        return None

    async def chat_completions(self, *, provider: str, payload: dict):
        await self.evt.wait()
        return {
            "id": "x",
            "object": "chat.completion",
            "created": 0,
            "model": payload.get("model"),
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                }
            ],
            "usage": None,
        }


class FailingUpstreams:
    def __init__(self, exc: SGError):
        self.exc = exc

    async def aclose(self) -> None:
        return None

    async def chat_completions(self, *, provider: str, payload: dict):
        raise self.exc


@pytest.mark.asyncio
async def test_queue_full_returns_429(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    evt = asyncio.Event()

    def _build_upstreams(cfg, cfg_raw):
        return BlockingUpstreams(evt)

    monkeypatch.setattr(sg_app, "build_upstreams", _build_upstreams)

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
        "limits": {"max_queue_depth": 1},
        "upstreams": {
            "openai": {"base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY"}
        },
    }
    config_path = tmp_path / "config.json"
    write_json(config_path, config)
    monkeypatch.setenv("SIGNALGATE_CONFIG_PATH", str(config_path))

    app = sg_app.create_app()
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # Fire one request that blocks.
            t1 = asyncio.create_task(
                client.post(
                    "/v1/chat/completions",
                    json={
                        "model": "signalgate/auto",
                        "messages": [{"role": "user", "content": "hi"}],
                    },
                )
            )
            # Give it a moment to acquire queue slot.
            await asyncio.sleep(0.05)

            # Second request should see queue full.
            r2 = await client.post(
                "/v1/chat/completions",
                json={"model": "signalgate/auto", "messages": [{"role": "user", "content": "hi"}]},
            )
            assert r2.status_code == 429
            assert r2.json()["_signalgate"]["error"]["code"] == "SG_QUEUE_FULL"

            # Unblock and await first.
            evt.set()
            r1 = await t1
            assert r1.status_code == 200


@pytest.mark.asyncio
async def test_breaker_opens_after_consecutive_failures(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    exc = SGError(code="SG_UPSTREAM_TIMEOUT", message="timeout", status_code=503, retryable=True)

    def _build_upstreams(cfg, cfg_raw):
        return FailingUpstreams(exc)

    monkeypatch.setattr(sg_app, "build_upstreams", _build_upstreams)

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
        "breakers": {
            "enabled": True,
            "rolling_window_seconds": 120,
            "min_samples": 1,
            "consecutive_failures": 2,
            "error_rate": 1.0,
            "timeout_rate": 0.0,
            "cooldown_seconds": 999,
        },
        "upstreams": {
            "openai": {"base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY"}
        },
    }
    config_path = tmp_path / "config.json"
    write_json(config_path, config)
    monkeypatch.setenv("SIGNALGATE_CONFIG_PATH", str(config_path))

    app = sg_app.create_app()
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            for _ in range(2):
                r = await client.post(
                    "/v1/chat/completions",
                    json={
                        "model": "signalgate/auto",
                        "messages": [{"role": "user", "content": "hi"}],
                    },
                )
                assert r.status_code == 503

            r3 = await client.post(
                "/v1/chat/completions",
                json={"model": "signalgate/auto", "messages": [{"role": "user", "content": "hi"}]},
            )

            assert r3.status_code == 503
            assert r3.json()["_signalgate"]["error"]["code"] == "SG_BREAKER_OPEN"
