from __future__ import annotations

import json

import httpx
import pytest
from asgi_lifespan import LifespanManager

from signalgate import app as sg_app


class StubUpstreams:
    async def chat_completions(self, *, provider: str, payload: dict):
        # Return OpenAI-shaped response with usage so costing is deterministic.
        return {
            "id": "stub",
            "object": "chat.completion",
            "created": 0,
            "model": payload.get("model", ""),
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "ok"},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }

    async def chat_completions_stream(self, *, provider: str, payload: dict):
        raise RuntimeError("not used")

    async def aclose(self) -> None:
        return None


@pytest.fixture
def cost_config(tmp_path, monkeypatch: pytest.MonkeyPatch):
    manifest = {
        "version": "0.1.0",
        "providerPreference": ["gemini", "openai"],
        "models": {
            "gemini_bal": {
                "provider": "gemini",
                "model_id": "gemini-3-flash",
                "eligible_tiers": ["balanced"],
                "supports": {"tools": False, "json_schema": False, "streaming": False},
                "limits": {"context_window_tokens": 8192, "max_output_tokens": 2048},
                "pricing": {"input_usd_per_1m": 1.0, "output_usd_per_1m": 1.0},
                "routing": {"preference_bias": -0.1, "latency_weight": 0.0, "cost_weight": 1.0},
            },
            "openai_bal": {
                "provider": "openai",
                "model_id": "gpt-4.1-mini",
                "eligible_tiers": ["balanced"],
                "supports": {"tools": False, "json_schema": False, "streaming": False},
                "limits": {"context_window_tokens": 8192, "max_output_tokens": 2048},
                "pricing": {"input_usd_per_1m": 2.0, "output_usd_per_1m": 2.0},
                "routing": {"preference_bias": 0.0, "latency_weight": 0.0, "cost_weight": 1.0},
            },
        },
        "tiers": {
            "budget": ["gemini_bal"],
            "balanced": ["gemini_bal", "openai_bal"],
            "premium": ["openai_bal"],
        },
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    cfg = {
        "version": "0.1.0",
        "server": {"host": "127.0.0.1", "port": 8765},
        "paths": {"manifest_path": str(manifest_path)},
        "features": {
            "enable_streaming": False,
            "enable_canary": False,
            "enable_shadow_mode": False,
        },
        "routing": {"enable_stickiness": False},
        "cost": {"baseline_model_key": "openai_bal"},
        "upstreams": {
            "openai": {"base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY"},
            "gemini": {"api_key_env": "GEMINI_API_KEY"},
        },
    }
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

    monkeypatch.setenv("SIGNALGATE_CONFIG_PATH", str(cfg_path))
    return cfg_path


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cost_and_savings_and_metrics(cost_config, monkeypatch: pytest.MonkeyPatch):
    stub = StubUpstreams()

    def _build_upstreams(cfg, cfg_raw):
        return stub

    monkeypatch.setattr(sg_app, "build_upstreams", _build_upstreams)

    app = sg_app.create_app()
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "signalgate/balanced",
                    "messages": [{"role": "user", "content": "hi"}],
                },
            )
            assert r.status_code == 200
            body = r.json()
            meta = body.get("_signalgate")
            assert meta
            assert meta["routed_provider"] == "gemini"
            assert meta["cost"]
            assert meta["cost"]["prompt_tokens"] == 10
            assert meta["cost"]["completion_tokens"] == 5
            assert meta["cost"]["usd_estimate"] == pytest.approx(0.000015, rel=1e-6)
            assert meta["savings_percent"] == pytest.approx(50.0, rel=1e-6)

            m = await client.get("/metrics")
            assert m.status_code == 200
            mbody = m.json()
            assert mbody["requests_total"] >= 1
            assert mbody["routed_total"].get("provider:gemini", 0) >= 1
