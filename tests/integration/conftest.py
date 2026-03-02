from __future__ import annotations

import json
from pathlib import Path

import pytest


def write_json(p: Path, obj: object) -> None:
    p.write_text(json.dumps(obj, indent=2), encoding="utf-8")


def write_jsonl(p: Path, lines: list[dict]) -> None:
    p.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")


@pytest.fixture
def minimal_manifest(tmp_path: Path) -> Path:
    manifest = {
        "version": "0.1.0",
        "providerPreference": ["gemini", "openai"],
        "models": {
            "gemini_bal": {
                "provider": "gemini",
                "model_id": "gemini-3-flash",
                "eligible_tiers": ["balanced"],
                "supports": {"tools": True, "json_schema": False, "streaming": False},
                "limits": {"context_window_tokens": 8192, "max_output_tokens": 2048},
                "pricing": {"input_usd_per_1m": 1.0, "output_usd_per_1m": 1.0},
                "routing": {"cost_weight": 1.0, "preference_bias": -0.5},
            },
            "openai_bal": {
                "provider": "openai",
                "model_id": "gpt-4.1-mini",
                "eligible_tiers": ["balanced"],
                "supports": {"tools": True, "json_schema": False, "streaming": True},
                "limits": {"context_window_tokens": 8192, "max_output_tokens": 2048},
                "pricing": {"input_usd_per_1m": 1.0, "output_usd_per_1m": 1.0},
                "routing": {"cost_weight": 1.0, "preference_bias": -0.2},
            },
        },
        "tiers": {
            "budget": ["gemini_bal"],
            "balanced": ["gemini_bal", "openai_bal"],
            "premium": ["openai_bal"],
        },
    }
    p = tmp_path / "manifest.json"
    write_json(p, manifest)
    return p


@pytest.fixture
def minimal_config(tmp_path: Path, minimal_manifest: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    cfg = {
        "version": "0.1.0",
        "server": {"host": "127.0.0.1", "port": 8765},
        "paths": {"manifest_path": str(minimal_manifest)},
        "features": {"enable_streaming": True, "enable_canary": False, "enable_shadow_mode": False},
        "routing": {"enable_stickiness": False},
        "upstreams": {
            "openai": {"base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY"},
            "gemini": {"api_key_env": "GEMINI_API_KEY"},
        },
        "breakers": {
            "enabled": True,
            "min_samples": 1,
            "consecutive_failures": 2,
            "cooldown_seconds": 1,
        },
    }
    p = tmp_path / "config.json"
    write_json(p, cfg)
    monkeypatch.setenv("SIGNALGATE_CONFIG_PATH", str(p))
    return p
