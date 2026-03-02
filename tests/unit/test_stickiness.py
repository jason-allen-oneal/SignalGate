from __future__ import annotations

from signalgate.routing import select_candidate


def test_sticky_key_selects_stable_model():
    manifest = {
        "version": "0.1.0",
        "providerPreference": ["openai"],
        "models": {
            "a": {
                "provider": "openai",
                "model_id": "m-a",
                "eligible_tiers": ["balanced"],
                "supports": {"tools": False, "json_schema": False, "streaming": False},
                "limits": {"context_window_tokens": 8192, "max_output_tokens": 2048},
                "pricing": {"input_usd_per_1m": 1.0, "output_usd_per_1m": 1.0},
                "routing": {"cost_weight": 1.0, "preference_bias": 0.0},
            },
            "b": {
                "provider": "openai",
                "model_id": "m-b",
                "eligible_tiers": ["balanced"],
                "supports": {"tools": False, "json_schema": False, "streaming": False},
                "limits": {"context_window_tokens": 8192, "max_output_tokens": 2048},
                "pricing": {"input_usd_per_1m": 1.0, "output_usd_per_1m": 1.0},
                "routing": {"cost_weight": 1.0, "preference_bias": 0.0},
            },
        },
        "tiers": {"budget": ["a"], "balanced": ["a", "b"], "premium": ["a", "b"]},
    }

    req = {"model": "signalgate/auto", "messages": [{"role": "user", "content": "hi"}]}

    c1, _, _ = select_candidate(
        virtual_model="signalgate/auto",
        req=req,
        manifest=manifest,
        provider_preference=["openai"],
        streaming_supported=False,
        tier_override="balanced",
        sticky_key="user-1",
        sticky_salt="salt",
    )
    c2, _, _ = select_candidate(
        virtual_model="signalgate/auto",
        req=req,
        manifest=manifest,
        provider_preference=["openai"],
        streaming_supported=False,
        tier_override="balanced",
        sticky_key="user-1",
        sticky_salt="salt",
    )

    assert c1.model_id == c2.model_id

    c3, _, _ = select_candidate(
        virtual_model="signalgate/auto",
        req=req,
        manifest=manifest,
        provider_preference=["openai"],
        streaming_supported=False,
        tier_override="balanced",
        sticky_key="user-2",
        sticky_salt="salt",
    )

    # Not guaranteed different, but often should be. At minimum it should be one of the cohort.
    assert c3.model_id in ("m-a", "m-b")
