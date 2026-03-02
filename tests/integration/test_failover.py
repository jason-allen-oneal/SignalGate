from __future__ import annotations

import httpx
import pytest
from asgi_lifespan import LifespanManager

import signalgate.app as sg_app
from signalgate.errors import SGError


class StubUpstreams:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    async def aclose(self) -> None:
        return None

    async def chat_completions(self, *, provider: str, payload: dict):
        self.calls.append((provider, payload.get("model")))
        # Fail first provider, succeed second.
        if provider == "gemini":
            raise SGError(
                code="SG_UPSTREAM_TIMEOUT", message="timeout", status_code=503, retryable=True
            )
        return {
            "id": "ok",
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
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

    async def chat_completions_stream(self, *, provider: str, payload: dict):
        raise SGError(
            code="SG_BAD_REQUEST", message="not streaming", status_code=400, retryable=False
        )


@pytest.fixture
def fast_breaker_config(tmp_path, minimal_manifest, monkeypatch: pytest.MonkeyPatch):
    cfg = {
        "version": "0.1.0",
        "server": {"host": "127.0.0.1", "port": 8765},
        "paths": {"manifest_path": str(minimal_manifest)},
        "features": {"enable_streaming": True, "enable_canary": False, "enable_shadow_mode": False},
        "routing": {"enable_stickiness": False},
        "upstreams": {
            "openai": {"base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY"},
            "gemini": {"api_key_env": "GEMINI_API_KEY"},
        },
        "breakers": {
            "enabled": True,
            "min_samples": 1,
            "consecutive_failures": 1,
            "cooldown_seconds": 60,
        },
    }
    p = tmp_path / "config.json"
    p.write_text(__import__("json").dumps(cfg, indent=2), encoding="utf-8")
    monkeypatch.setenv("SIGNALGATE_CONFIG_PATH", str(p))
    return p


@pytest.mark.asyncio
@pytest.mark.integration
async def test_no_tools_allows_single_failover(minimal_config, monkeypatch: pytest.MonkeyPatch):
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
    assert body["_signalgate"]["routed_provider"] == "openai"
    assert ("gemini", "gemini-3-flash") in stub.calls


@pytest.mark.asyncio
@pytest.mark.integration
async def test_tools_disables_failover(minimal_config, monkeypatch: pytest.MonkeyPatch):
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
                    "tools": [
                        {
                            "type": "function",
                            "function": {"name": "x", "parameters": {"type": "object"}},
                        }
                    ],
                },
            )

    assert r.status_code == 503
    # should only have tried gemini and then stopped
    assert stub.calls and stub.calls[0][0] == "gemini"
    assert all(p == "gemini" for p, _m in stub.calls)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_breaker_open_is_deprioritized_for_next_request(
    fast_breaker_config, monkeypatch: pytest.MonkeyPatch
):
    stub = StubUpstreams()

    def _build_upstreams(cfg, cfg_raw):
        return stub

    monkeypatch.setattr(sg_app, "build_upstreams", _build_upstreams)

    app = sg_app.create_app()
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # First request trips Gemini breaker then fails over to OpenAI.
            r1 = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "signalgate/balanced",
                    "messages": [{"role": "user", "content": "hi"}],
                },
            )
            assert r1.status_code == 200
            assert ("gemini", "gemini-3-flash") in stub.calls

            stub.calls.clear()

            # Second request should go straight to OpenAI (avoid breaker-open latency).
            r2 = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "signalgate/balanced",
                    "messages": [{"role": "user", "content": "hi"}],
                },
            )
            assert r2.status_code == 200

    assert stub.calls and stub.calls[0][0] == "openai"
    assert all(p != "gemini" for p, _m in stub.calls)
