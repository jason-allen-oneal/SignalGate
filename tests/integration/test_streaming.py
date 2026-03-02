from __future__ import annotations

import httpx
import pytest
from asgi_lifespan import LifespanManager

import signalgate.app as sg_app


class StreamUpstreams:
    async def aclose(self) -> None:
        return None

    async def chat_completions(self, *, provider: str, payload: dict):
        raise AssertionError("non-streaming called")

    async def chat_completions_stream(self, *, provider: str, payload: dict):
        # yield a minimal OpenAI-style SSE sequence
        yield (
            b'data: {"id":"1","object":"chat.completion.chunk","choices":[{"delta":'
            b'{"role":"assistant","content":"hi"}}]}\n\n'
        )
        yield b"data: [DONE]\n\n"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_streaming_endpoint_returns_event_stream(
    minimal_config, monkeypatch: pytest.MonkeyPatch
):
    def _build_upstreams(cfg, cfg_raw):
        return StreamUpstreams()

    monkeypatch.setattr(sg_app, "build_upstreams", _build_upstreams)

    app = sg_app.create_app()
    async with LifespanManager(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            r = await client.post(
                "/v1/chat/completions",
                json={
                    "model": "signalgate/premium",
                    "stream": True,
                    "messages": [{"role": "user", "content": "hi"}],
                },
            )
            assert r.status_code == 200
            assert r.headers.get("content-type", "").startswith("text/event-stream")
            body = r.text

    assert "data: [DONE]" in body
