from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from .util import rough_token_estimate


@dataclass(frozen=True)
class CostEstimate:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    usd_estimate: float | None
    estimated_tokens: bool
    pricing: dict[str, float] | None = None


def _safe_int(v: Any) -> int | None:
    try:
        return int(v)
    except Exception:
        return None


def tokens_from_openai_usage(usage: Any) -> tuple[int, int] | None:
    if not isinstance(usage, dict):
        return None
    pt = _safe_int(usage.get("prompt_tokens"))
    ct = _safe_int(usage.get("completion_tokens"))
    if pt is None or ct is None:
        return None
    return pt, ct


def estimate_tokens_from_response(
    *, caps_prompt_tokens: int, resp: dict[str, Any]
) -> tuple[int, int]:
    # Prompt: use caps estimate.
    pt = int(caps_prompt_tokens)

    # Completion: rough estimate from assistant text.
    out_text = ""
    try:
        choices = resp.get("choices") or []
        msg = choices[0].get("message")
        if isinstance(msg, dict) and isinstance(msg.get("content"), str):
            out_text = msg["content"]
    except Exception:
        out_text = ""

    ct = rough_token_estimate(out_text)
    return pt, ct


def usd_from_pricing(
    *, pricing: dict[str, float], prompt_tokens: int, completion_tokens: int
) -> float | None:
    in_price = pricing.get("input_usd_per_1m")
    out_price = pricing.get("output_usd_per_1m")
    if in_price is None or out_price is None:
        return None
    try:
        in_price_f = float(in_price)
        out_price_f = float(out_price)
        if math.isinf(in_price_f) or math.isinf(out_price_f):
            return None
        return ((prompt_tokens * in_price_f) + (completion_tokens * out_price_f)) / 1_000_000.0
    except Exception:
        return None


def compute_cost(
    *,
    pricing: dict[str, float] | None,
    caps_prompt_tokens: int,
    resp: dict[str, Any],
) -> CostEstimate:
    usage_tokens = tokens_from_openai_usage(resp.get("usage"))

    if usage_tokens is not None:
        pt, ct = usage_tokens
        estimated = False
    else:
        pt, ct = estimate_tokens_from_response(caps_prompt_tokens=caps_prompt_tokens, resp=resp)
        estimated = True

    usd = usd_from_pricing(pricing=pricing or {}, prompt_tokens=pt, completion_tokens=ct) if pricing else None

    return CostEstimate(
        prompt_tokens=pt,
        completion_tokens=ct,
        total_tokens=pt + ct,
        usd_estimate=usd,
        estimated_tokens=estimated,
        pricing=pricing if pricing else None,
    )


def savings_percent(*, routed_usd: float | None, baseline_usd: float | None) -> float | None:
    if routed_usd is None or baseline_usd is None:
        return None
    if baseline_usd <= 0:
        return None
    return ((baseline_usd - routed_usd) / baseline_usd) * 100.0
