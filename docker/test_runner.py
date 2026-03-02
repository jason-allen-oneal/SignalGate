from __future__ import annotations

import os
import time

import httpx


def main() -> int:
    base = os.environ.get("SIGNALGATE_URL", "http://signalgate:8765")
    token = os.environ.get("SIGNALGATE_TOKEN", "")

    headers = {"x-signalgate-token": token} if token else {}

    # health should be accessible (with retry for startup)
    max_retries = 30
    r = None
    for _i in range(max_retries):
        try:
            r = httpx.get(f"{base}/healthz", timeout=2)
            if r.status_code == 200:
                break
        except httpx.RequestError:
            pass
        time.sleep(1)

    if not r or r.status_code != 200:
        print(f"FAILED: service at {base} never became healthy")
        return 1

    # ready should include router_version
    r = httpx.get(f"{base}/readyz", timeout=10)
    assert r.status_code == 200
    assert "router_version" in r.json()

    # models
    r = httpx.get(f"{base}/v1/models", headers=headers, timeout=10)
    assert r.status_code == 200

    # auth should be required
    r = httpx.post(
        f"{base}/v1/chat/completions",
        json={"model": "signalgate/balanced", "messages": [{"role": "user", "content": "ping"}]},
        timeout=10,
    )
    assert r.status_code == 401

    # non-streaming success
    r = httpx.post(
        f"{base}/v1/chat/completions",
        headers=headers,
        json={"model": "signalgate/balanced", "messages": [{"role": "user", "content": "ping"}]},
        timeout=20,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["choices"][0]["message"]["content"] == "ok"
    assert "_signalgate" in body

    # streaming success
    with httpx.stream(
        "POST",
        f"{base}/v1/chat/completions",
        headers=headers,
        json={
            "model": "signalgate/premium",
            "stream": True,
            "messages": [{"role": "user", "content": "ping"}],
        },
        timeout=20,
    ) as s:
        assert s.status_code == 200
        data = s.read().decode("utf-8", errors="ignore")
        assert "data: [DONE]" in data

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:
        print(f"TEST FAILED: {e}")
        raise
