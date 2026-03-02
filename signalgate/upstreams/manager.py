from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..errors import SGError
from ..settings import RuntimeConfig
from .gemini import GeminiUpstream
from .openai import OpenAIUpstream


@dataclass
class Upstreams:
    openai: OpenAIUpstream
    gemini: GeminiUpstream

    async def aclose(self) -> None:
        await self.openai.aclose()
        await self.gemini.aclose()

    async def chat_completions(self, *, provider: str, payload: dict[str, Any]) -> dict[str, Any]:
        if provider == "openai":
            return await self.openai.chat_completions(payload)
        if provider == "gemini":
            return await self.gemini.chat_completions(payload)
        raise SGError(
            code="SG_NO_CANDIDATES",
            message=f"Unknown provider '{provider}'",
            status_code=503,
            retryable=True,
        )

    async def chat_completions_stream(self, *, provider: str, payload: dict[str, Any]):
        if provider == "openai":
            async for chunk in self.openai.chat_completions_stream(payload):
                yield chunk
            return
        if provider == "gemini":
            async for chunk in self.gemini.chat_completions_stream(payload):
                yield chunk
            return
        raise SGError(
            code="SG_BAD_REQUEST",
            message=f"Streaming not supported for provider '{provider}'",
            status_code=400,
            retryable=False,
        )


def build_upstreams(cfg: RuntimeConfig, cfg_raw: dict[str, Any]) -> Upstreams:
    timeouts = cfg_raw.get("timeouts", {})
    connect_s = float(timeouts.get("connect_seconds", 3))
    read_s = float(timeouts.get("read_seconds", 60))

    openai = OpenAIUpstream(
        base_url=cfg.upstream_openai.base_url,
        api_key_env=cfg.upstream_openai.api_key_env,
        connect_seconds=connect_s,
        read_seconds=read_s,
    )

    gemini = GeminiUpstream(
        base_url=cfg.upstream_gemini.base_url,
        api_version=cfg.upstream_gemini.api_version,
        api_key_env=cfg.upstream_gemini.api_key_env,
        connect_seconds=connect_s,
        read_seconds=read_s,
    )

    return Upstreams(openai=openai, gemini=gemini)
