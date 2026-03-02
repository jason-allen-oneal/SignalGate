from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal, Optional

from .errors import sg_bad_request, sg_no_candidates
from .util import rough_token_estimate

Tier = Literal["budget", "balanced", "premium"]


@dataclass(frozen=True)
class RequiredCaps:
    tools: bool
    json_schema: bool
    streaming: bool
    estimated_prompt_tokens: int
    max_output_tokens: int


@dataclass(frozen=True)
class Candidate:
    key: str
    provider: str
    model_id: str
    supports: dict[str, bool]
    limits: dict[str, int]
    pricing: dict[str, float]
    routing: dict[str, float]


def _tier_from_virtual_model(model: str) -> tuple[str, Tier]:
    if model == "signalgate/auto":
        # Auto tier can be overridden by classifier.
        return model, "balanced"
    if model == "signalgate/budget":
        return model, "budget"
    if model == "signalgate/balanced":
        return model, "balanced"
    if model == "signalgate/premium":
        return model, "premium"
    if model == "signalgate/chat-only":
        return model, "balanced"
    raise sg_bad_request(f"Unknown model '{model}'. Expected signalgate/*")


def required_caps_from_request(req: dict[str, Any], *, streaming_supported: bool) -> RequiredCaps:
    tools = bool(req.get("tools")) or (req.get("tool_choice") not in (None, "none"))

    response_format = req.get("response_format")
    json_schema = False
    if isinstance(response_format, dict):
        # OpenAI: {"type":"json_schema", ...} or {"type":"json_object"}
        t = response_format.get("type")
        if t in ("json_schema", "json_object"):
            json_schema = True

    streaming = bool(req.get("stream", False))
    if streaming and not streaming_supported:
        raise sg_bad_request("stream=true requested but streaming is disabled")

    max_output_tokens = int(req.get("max_tokens") or 0) or 1024

    # Prompt estimate: concat message contents.
    messages = req.get("messages")
    if not isinstance(messages, list) or not messages:
        raise sg_bad_request("Missing messages")

    text_parts: list[str] = []
    for m in messages:
        if not isinstance(m, dict):
            continue
        content = m.get("content")
        if isinstance(content, str):
            text_parts.append(content)
        elif isinstance(content, list):
            # Content parts (vision/etc). Keep text only.
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    t = part.get("text")
                    if isinstance(t, str):
                        text_parts.append(t)

    est_prompt_tokens = rough_token_estimate("\n".join(text_parts))

    return RequiredCaps(
        tools=tools,
        json_schema=json_schema,
        streaming=streaming,
        estimated_prompt_tokens=est_prompt_tokens,
        max_output_tokens=max_output_tokens,
    )


def rank_candidates(
    *,
    virtual_model: str,
    req: dict[str, Any],
    manifest: dict[str, Any],
    provider_preference: list[str],
    streaming_supported: bool,
    tier_override: Optional[Tier] = None,
) -> tuple[list[Candidate], Tier, RequiredCaps]:
    _, tier_default = _tier_from_virtual_model(virtual_model)
    tier = tier_override or tier_default

    caps = required_caps_from_request(req, streaming_supported=streaming_supported)

    if virtual_model == "signalgate/chat-only":
        caps = RequiredCaps(
            tools=False,
            json_schema=caps.json_schema,
            streaming=caps.streaming,
            estimated_prompt_tokens=caps.estimated_prompt_tokens,
            max_output_tokens=caps.max_output_tokens,
        )

    tiers = manifest.get("tiers", {})
    pool = tiers.get(tier)
    if not isinstance(pool, list) or not pool:
        raise sg_no_candidates(f"Tier pool missing for {tier}")

    models: dict[str, Any] = manifest.get("models", {})

    candidates: list[Candidate] = []
    for key in pool:
        if key not in models:
            continue
        entry = models[key]
        try:
            cand = Candidate(
                key=key,
                provider=str(entry.get("provider")),
                model_id=str(entry.get("model_id")),
                supports=dict(entry.get("supports") or {}),
                limits=dict(entry.get("limits") or {}),
                pricing={k: float(v) for k, v in (entry.get("pricing") or {}).items()},
                routing={k: float(v) for k, v in (entry.get("routing") or {}).items()},
            )
        except Exception:
            continue
        candidates.append(cand)

    def ok(c: Candidate) -> bool:
        if caps.tools and not c.supports.get("tools", False):
            return False
        if caps.json_schema and not c.supports.get("json_schema", False):
            return False
        if caps.streaming and not c.supports.get("streaming", False):
            return False
        ctx = int(c.limits.get("context_window_tokens") or 0)
        max_out = int(c.limits.get("max_output_tokens") or 0)
        needed = caps.estimated_prompt_tokens + caps.max_output_tokens
        if ctx and needed > ctx:
            return False
        if max_out and caps.max_output_tokens > max_out:
            return False
        return True

    filtered = [c for c in candidates if ok(c)]
    if not filtered:
        raise sg_no_candidates("No candidates satisfy capability gates")

    pref_index = {p: i for i, p in enumerate(provider_preference)}

    def estimate_cost_usd(c: Candidate) -> float:
        in_price = float(c.pricing.get("input_usd_per_1m", math.inf))
        out_price = float(c.pricing.get("output_usd_per_1m", math.inf))
        if math.isinf(in_price) or math.isinf(out_price):
            return math.inf
        return (
            (caps.estimated_prompt_tokens * in_price) + (caps.max_output_tokens * out_price)
        ) / 1_000_000.0

    def score(c: Candidate) -> tuple[int, float, float]:
        provider_rank = pref_index.get(c.provider, 9999)
        cost = estimate_cost_usd(c)
        cost_w = float(c.routing.get("cost_weight", 1.0))
        pref_bias = float(c.routing.get("preference_bias", 0.0))
        s = (cost_w * cost) + pref_bias
        return provider_rank, s, cost

    filtered.sort(key=score)
    return filtered, tier, caps


def select_candidate(
    *,
    virtual_model: str,
    req: dict[str, Any],
    manifest: dict[str, Any],
    provider_preference: list[str],
    streaming_supported: bool,
    tier_override: Optional[Tier] = None,
    sticky_key: str | None = None,
    sticky_salt: str = "signalgate",
) -> tuple[Candidate, Tier, RequiredCaps]:
    import hashlib

    ranked, tier, caps = rank_candidates(
        virtual_model=virtual_model,
        req=req,
        manifest=manifest,
        provider_preference=provider_preference,
        streaming_supported=streaming_supported,
        tier_override=tier_override,
    )

    if sticky_key:
        pref_index = {p: i for i, p in enumerate(provider_preference)}
        best_rank = pref_index.get(ranked[0].provider, 9999)
        cohort = [c for c in ranked if pref_index.get(c.provider, 9999) == best_rank]

        def h(c: Candidate) -> str:
            b = f"{sticky_salt}:{sticky_key}:{tier}:{c.key}".encode("utf-8")
            return hashlib.sha256(b).hexdigest()

        cohort.sort(key=h)
        return cohort[0], tier, caps

    return ranked[0], tier, caps
