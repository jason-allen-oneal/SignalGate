from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from ..errors import SGError
from ..settings import RuntimeConfig
from .gemini import GeminiUpstream
from .openai import OpenAIUpstream


class UpstreamClient(Protocol):
    async def chat_completions(self, payload: dict[str, Any]) -> dict[str, Any]:
        ...

    async def chat_completions_stream(self, payload: dict[str, Any]):
        ...

    async def aclose(self) -> None:
        ...


@dataclass
class Upstreams:
    clients: dict[str, UpstreamClient]

    async def aclose(self) -> None:
        for c in self.clients.values():
            await c.aclose()

    async def chat_completions(self, *, provider: str, payload: dict[str, Any]) -> dict[str, Any]:
        c = self.clients.get(provider)
        if not c:
            raise SGError(
                code="SG_NO_CANDIDATES",
                message=f"Unknown provider '{provider}'",
                status_code=503,
                retryable=True,
            )
        return await c.chat_completions(payload)

    async def chat_completions_stream(self, *, provider: str, payload: dict[str, Any]):
        c = self.clients.get(provider)
        if not c:
            raise SGError(
                code="SG_BAD_REQUEST",
                message=f"Streaming not supported for provider '{provider}'",
                status_code=400,
                retryable=False,
            )
        async for chunk in c.chat_completions_stream(payload):
            yield chunk


def build_upstreams(cfg: RuntimeConfig, cfg_raw: dict[str, Any]) -> Upstreams:
    timeouts = cfg_raw.get("timeouts", {})
    connect_s = float(timeouts.get("connect_seconds", 3))
    read_s = float(timeouts.get("read_seconds", 60))

    clients: dict[str, UpstreamClient] = {}

    for name, u in cfg.upstreams.items():
        if u.kind == "openai_compat":
            if not u.base_url:
                raise SGError(
                    code="SG_INTERNAL",
                    message=f"Upstream '{name}' missing base_url",
                    status_code=500,
                    retryable=False,
                )
            clients[name] = OpenAIUpstream(
                base_url=u.base_url,
                api_key_env=u.api_key_env,
                connect_seconds=connect_s,
                read_seconds=read_s,
            )
        elif u.kind == "gemini":
            if not u.base_url:
                raise SGError(
                    code="SG_INTERNAL",
                    message=f"Upstream '{name}' missing base_url",
                    status_code=500,
                    retryable=False,
                )
            clients[name] = GeminiUpstream(
                base_url=u.base_url,
                api_version=u.api_version or "v1beta",
                api_key_env=u.api_key_env,
                connect_seconds=connect_s,
                read_seconds=read_s,
            )
        else:
            raise SGError(
                code="SG_INTERNAL",
                message=f"Unknown upstream kind for '{name}': {u.kind}",
                status_code=500,
                retryable=False,
            )

    return Upstreams(clients=clients)
