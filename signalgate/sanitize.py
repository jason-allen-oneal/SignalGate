from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from .errors import sg_bad_request


@dataclass(frozen=True)
class RequestFieldConfig:
    mode: str = "passthrough"  # passthrough|strip_unknown


DEFAULT_ALLOWED_TOP_LEVEL: set[str] = {
    "model",
    "messages",
    "temperature",
    "top_p",
    "max_tokens",
    "stream",
    "tools",
    "tool_choice",
    "response_format",
    "user",
    "n",
    "stop",
    "presence_penalty",
    "frequency_penalty",
    "seed",
    "logprobs",
    "top_logprobs",
}

DEFAULT_ALLOWED_MESSAGE_KEYS: set[str] = {
    "role",
    "content",
    "name",
    "tool_call_id",
    "tool_calls",
}


def sanitize_chat_completions_payload(
    payload: dict[str, Any],
    *,
    cfg: RequestFieldConfig,
    allowed_top_level: Iterable[str] = DEFAULT_ALLOWED_TOP_LEVEL,
    allowed_message_keys: Iterable[str] = DEFAULT_ALLOWED_MESSAGE_KEYS,
) -> dict[str, Any]:
    """Strip unknown fields from OpenAI Chat Completions payload.

    Security goal: reduce attack surface and prevent surprising pass-through fields.
    This is NOT prompt rewriting. It does not modify message content, only removes
    keys we do not explicitly support.

    Notes:
    - Only shallow stripping is performed at the top level.
    - Messages are shallow-sanitized to a minimal key set.
    """

    if cfg.mode not in ("passthrough", "strip_unknown"):
        raise sg_bad_request("Invalid security.request_fields.mode")

    if cfg.mode == "passthrough":
        return payload

    allow_top = set(allowed_top_level)
    allow_msg = set(allowed_message_keys)

    out: dict[str, Any] = {k: v for k, v in payload.items() if k in allow_top}

    # Sanitize messages shape
    messages = out.get("messages")
    if messages is None:
        return out

    if not isinstance(messages, list):
        raise sg_bad_request("messages must be a list")

    new_msgs: list[dict[str, Any]] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        nm = {k: v for k, v in m.items() if k in allow_msg}
        new_msgs.append(nm)
    out["messages"] = new_msgs

    return out
