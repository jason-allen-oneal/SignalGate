from __future__ import annotations

import os
from typing import Any

import httpx

from ..errors import SGError, sg_upstream_5xx, sg_upstream_rate_limit, sg_upstream_timeout


class OpenAIUpstream:
    def __init__(
        self,
        *,
        base_url: str,
        api_key_env: str,
        connect_seconds: float,
        read_seconds: float,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self._timeout = httpx.Timeout(
            connect=connect_seconds, read=read_seconds, write=read_seconds, pool=connect_seconds
        )
        self._client = httpx.AsyncClient(timeout=self._timeout)

    def _headers(self) -> dict[str, str]:
        api_key = os.environ.get(self.api_key_env)
        if not api_key:
            raise SGError(
                code="SG_INTERNAL",
                message=f"Missing env var {self.api_key_env} for OpenAI upstream",
                status_code=500,
                retryable=False,
            )
        return {"Authorization": f"Bearer {api_key}"}

    async def chat_completions(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.base_url}/chat/completions"
        upstream_meta = {"provider": "openai", "model": payload.get("model"), "url": self.base_url}
        try:
            resp = await self._client.post(url, headers=self._headers(), json=payload)
        except (
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
            httpx.WriteTimeout,
            httpx.PoolTimeout,
        ) as err:
            raise sg_upstream_timeout(upstream_meta) from err
        except httpx.HTTPError as err:
            raise SGError(
                code="SG_UPSTREAM_5XX",
                message=f"Upstream HTTP error: {err}",
                status_code=503,
                retryable=True,
            ) from err

        if resp.status_code == 429:
            raise sg_upstream_rate_limit(upstream_meta)
        if 500 <= resp.status_code <= 599:
            raise sg_upstream_5xx(upstream_meta)
        if resp.status_code >= 400:
            # Pass through upstream error message but keep it short.
            try:
                data = resp.json()
            except Exception:
                data = {"error": {"message": resp.text[:500]}}
            raise SGError(
                code="SG_UPSTREAM_5XX",
                message=f"Upstream error ({resp.status_code})",
                status_code=503,
                retryable=False,
                upstream={"status": resp.status_code, **upstream_meta, "body": data.get("error")},
            )

        return resp.json()

    async def chat_completions_stream(self, payload: dict[str, Any]):
        """Return an async iterator of raw SSE bytes from OpenAI.

        SignalGate must not modify streaming frames (client compatibility). Any router
        metadata should be returned via HTTP headers.
        """

        url = f"{self.base_url}/chat/completions"
        upstream_meta = {"provider": "openai", "model": payload.get("model"), "url": self.base_url}

        try:
            async with self._client.stream("POST", url, headers=self._headers(), json=payload) as s:
                if s.status_code == 429:
                    raise sg_upstream_rate_limit(upstream_meta)
                if 500 <= s.status_code <= 599:
                    raise sg_upstream_5xx(upstream_meta)
                if s.status_code >= 400:
                    try:
                        data = await s.aread()
                        body = data.decode("utf-8", errors="ignore")[:500]
                        err = {"message": body}
                    except Exception:
                        err = {"message": "(unreadable upstream error)"}
                    raise SGError(
                        code="SG_UPSTREAM_5XX",
                        message=f"Upstream error ({s.status_code})",
                        status_code=503,
                        retryable=False,
                        upstream={"status": s.status_code, **upstream_meta, "body": err},
                    )

                async for chunk in s.aiter_bytes():
                    yield chunk
        except (
            httpx.ConnectTimeout,
            httpx.ReadTimeout,
            httpx.WriteTimeout,
            httpx.PoolTimeout,
        ) as err:
            raise sg_upstream_timeout(upstream_meta) from err
        except httpx.HTTPError as err:
            raise SGError(
                code="SG_UPSTREAM_5XX",
                message=f"Upstream HTTP error: {err}",
                status_code=503,
                retryable=True,
            ) from err

    async def aclose(self) -> None:
        await self._client.aclose()
