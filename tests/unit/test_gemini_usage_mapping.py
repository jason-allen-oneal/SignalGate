from __future__ import annotations

import httpx
import pytest

from signalgate.upstreams.gemini import GeminiUpstream


@pytest.mark.asyncio
async def test_gemini_maps_usage_metadata(monkeypatch: pytest.MonkeyPatch):
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith(":generateContent")
        return httpx.Response(
            200,
            json={
                "candidates": [
                    {"content": {"parts": [{"text": "ok"}]}}
                ],
                "usageMetadata": {
                    "promptTokenCount": 11,
                    "candidatesTokenCount": 7,
                    "totalTokenCount": 18,
                },
            },
        )

    transport = httpx.MockTransport(handler)

    g = GeminiUpstream(
        base_url="http://test",
        api_version="v1beta",
        api_key_env="GEMINI_API_KEY",
        connect_seconds=1,
        read_seconds=1,
    )
    g._client = httpx.AsyncClient(transport=transport)

    monkeypatch.setenv("GEMINI_API_KEY", "x")

    resp = await g.chat_completions({"model": "m", "messages": [{"role": "user", "content": "hi"}]})

    assert resp["usage"] == {
        "prompt_tokens": 11,
        "completion_tokens": 7,
        "total_tokens": 18,
    }

    await g.aclose()
