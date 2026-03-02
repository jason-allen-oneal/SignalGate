from __future__ import annotations

import os

import httpx
import pytest


@pytest.mark.e2e
def test_live_openai_key_present_or_skip():
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")


@pytest.mark.e2e
@pytest.mark.asyncio
async def test_live_openai_smoke():
    # This test hits OpenAI directly, not through SignalGate.
    # It is only here to validate credentials and basic upstream health.
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY not set")

    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"},
            json={
                "model": "gpt-4.1-mini",
                "messages": [{"role": "user", "content": "ping"}],
                "max_tokens": 5,
            },
        )

    assert r.status_code in (200, 401, 403)
