from __future__ import annotations

import json
import os
from typing import Any

import httpx

from ..errors import SGError, sg_upstream_5xx, sg_upstream_rate_limit, sg_upstream_timeout


class GeminiUpstream:
    """Minimal Gemini adapter.

    NOTE: This is a wire-format translation from OpenAI chat/completions payload to
    Gemini generateContent. It is not prompt rewriting, but it *is* message format
    adaptation.

    Supports non-streaming and streaming.

    Streaming uses Gemini streamGenerateContent and translates SSE frames into
    OpenAI chat.completion.chunk frames.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_version: str,
        api_key_env: str,
        connect_seconds: float,
        read_seconds: float,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_version = api_version
        self.api_key_env = api_key_env
        self._timeout = httpx.Timeout(
            connect=connect_seconds, read=read_seconds, write=read_seconds, pool=connect_seconds
        )
        self._client = httpx.AsyncClient(timeout=self._timeout)

    def _api_key(self) -> str:
        k = os.environ.get(self.api_key_env)
        if not k:
            raise SGError(
                code="SG_INTERNAL",
                message=f"Missing env var {self.api_key_env} for Gemini upstream",
                status_code=500,
                retryable=False,
            )
        return k

    @staticmethod
    def _openai_messages_to_gemini_contents(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        contents: list[dict[str, Any]] = []
        for m in messages:
            role = m.get("role")
            content = m.get("content")

            # Gemini roles: user | model
            gem_role = "user" if role in ("user", "system") else "model"

            text = ""
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                for part in content:
                    if (
                        isinstance(part, dict)
                        and part.get("type") == "text"
                        and isinstance(part.get("text"), str)
                    ):
                        text += part["text"]

            if role == "system" and text:
                text = f"SYSTEM: {text}"

            if text:
                contents.append({"role": gem_role, "parts": [{"text": text}]})

        if not contents:
            contents = [{"role": "user", "parts": [{"text": ""}]}]
        return contents

    async def chat_completions(self, payload: dict[str, Any]) -> dict[str, Any]:
        # Translate OpenAI chat/completions to Gemini generateContent.
        model_id = payload.get("model")
        if not isinstance(model_id, str) or not model_id:
            raise SGError(code="SG_BAD_REQUEST", message="Missing model", status_code=400)

        messages = payload.get("messages")
        if not isinstance(messages, list) or not messages:
            raise SGError(code="SG_BAD_REQUEST", message="Missing messages", status_code=400)

        url = f"{self.base_url}/{self.api_version}/models/{model_id}:generateContent"
        upstream_meta = {"provider": "gemini", "model": model_id, "url": self.base_url}

        req_body: dict[str, Any] = {
            "contents": self._openai_messages_to_gemini_contents(messages),
        }

        # Basic generation config mapping.
        gen_cfg: dict[str, Any] = {}
        if "temperature" in payload:
            gen_cfg["temperature"] = payload["temperature"]
        if "top_p" in payload:
            gen_cfg["topP"] = payload["top_p"]
        if "max_tokens" in payload:
            gen_cfg["maxOutputTokens"] = payload["max_tokens"]
        if gen_cfg:
            req_body["generationConfig"] = gen_cfg

        params = {"key": self._api_key()}

        try:
            resp = await self._client.post(url, params=params, json=req_body)
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

        data = resp.json()

        # Convert Gemini response to OpenAI chat/completions-ish.
        text_out = ""
        try:
            candidates = data.get("candidates") or []
            parts = candidates[0]["content"]["parts"]
            text_out = "".join([p.get("text", "") for p in parts if isinstance(p, dict)])
        except Exception:
            text_out = ""

        usage = None
        try:
            um = data.get("usageMetadata") or {}
            pt = um.get("promptTokenCount")
            ct = um.get("candidatesTokenCount")
            tt = um.get("totalTokenCount")
            if pt is not None and ct is not None:
                usage = {
                    "prompt_tokens": int(pt),
                    "completion_tokens": int(ct),
                    "total_tokens": int(tt) if tt is not None else int(pt) + int(ct),
                }
        except Exception:
            usage = None

        return {
            "id": f"gemini-{os.urandom(8).hex()}",
            "object": "chat.completion",
            "created": 0,
            "model": model_id,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text_out},
                    "finish_reason": "stop",
                }
            ],
            "usage": usage,
        }

    async def chat_completions_stream(self, payload: dict[str, Any]):
        """Stream Gemini content as OpenAI-compatible SSE bytes."""

        model_id = payload.get("model")
        if not isinstance(model_id, str) or not model_id:
            raise SGError(code="SG_BAD_REQUEST", message="Missing model", status_code=400)

        messages = payload.get("messages")
        if not isinstance(messages, list) or not messages:
            raise SGError(code="SG_BAD_REQUEST", message="Missing messages", status_code=400)

        url = f"{self.base_url}/{self.api_version}/models/{model_id}:streamGenerateContent"
        upstream_meta = {"provider": "gemini", "model": model_id, "url": self.base_url}

        req_body: dict[str, Any] = {
            "contents": self._openai_messages_to_gemini_contents(messages),
        }

        gen_cfg: dict[str, Any] = {}
        if "temperature" in payload:
            gen_cfg["temperature"] = payload["temperature"]
        if "top_p" in payload:
            gen_cfg["topP"] = payload["top_p"]
        if "max_tokens" in payload:
            gen_cfg["maxOutputTokens"] = payload["max_tokens"]
        if gen_cfg:
            req_body["generationConfig"] = gen_cfg

        params = {"key": self._api_key(), "alt": "sse"}

        stream_id = f"gemini-stream-{os.urandom(8).hex()}"
        emitted_role = False
        prev_text = ""
        last_usage: dict[str, int] | None = None

        def _emit(delta_text: str | None, *, finish_reason: str | None = None) -> bytes:
            nonlocal emitted_role

            delta: dict[str, Any] = {}
            if not emitted_role:
                delta["role"] = "assistant"
                emitted_role = True
            if delta_text:
                delta["content"] = delta_text

            obj = {
                "id": stream_id,
                "object": "chat.completion.chunk",
                "created": 0,
                "model": model_id,
                "choices": [
                    {
                        "index": 0,
                        "delta": delta,
                        "finish_reason": finish_reason,
                    }
                ],
            }
            b = json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            return b"data: " + b + b"\n\n"

        try:
            async with self._client.stream(
                "POST", url, params=params, json=req_body
            ) as s:
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

                async for line in s.aiter_lines():
                    if not line:
                        continue
                    if not line.startswith("data:"):
                        continue

                    data_s = line[len("data:") :].strip()
                    if not data_s:
                        continue
                    if data_s == "[DONE]":
                        break

                    try:
                        evt = json.loads(data_s)
                    except Exception:
                        continue

                    # Track usage when present.
                    try:
                        um = evt.get("usageMetadata") or {}
                        pt = um.get("promptTokenCount")
                        ct = um.get("candidatesTokenCount")
                        tt = um.get("totalTokenCount")
                        if pt is not None and ct is not None:
                            last_usage = {
                                "prompt_tokens": int(pt),
                                "completion_tokens": int(ct),
                                "total_tokens": int(tt) if tt is not None else int(pt) + int(ct),
                            }
                    except Exception:
                        pass

                    # Gemini stream events are full snapshots; emit deltas for OpenAI clients.
                    txt = ""
                    try:
                        candidates = evt.get("candidates") or []
                        parts = candidates[0]["content"]["parts"]
                        txt = "".join(
                            [p.get("text", "") for p in parts if isinstance(p, dict)]
                        )
                    except Exception:
                        txt = ""

                    if txt.startswith(prev_text):
                        delta = txt[len(prev_text) :]
                    else:
                        # Fallback: if snapshot regresses or differs, emit full content.
                        delta = txt

                    prev_text = txt

                    if delta:
                        yield _emit(delta)

                # Final frame (+ usage if known)
                if last_usage is not None:
                    obj = {
                        "id": stream_id,
                        "object": "chat.completion.chunk",
                        "created": 0,
                        "model": model_id,
                        "choices": [
                            {"index": 0, "delta": {}, "finish_reason": "stop"}
                        ],
                        "usage": last_usage,
                    }
                    b = json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode(
                        "utf-8"
                    )
                    yield b"data: " + b + b"\n\n"
                else:
                    yield _emit(None, finish_reason="stop")

                yield b"data: [DONE]\n\n"

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
