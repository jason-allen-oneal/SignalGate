from __future__ import annotations

import json
from pathlib import Path

import pytest

from signalgate.app import RuntimeState
from signalgate.routing import required_caps_from_request
from signalgate.runtime import load_and_validate


def write_json(p: Path, obj: object) -> None:
    p.write_text(json.dumps(obj, indent=2), encoding="utf-8")


def write_jsonl(p: Path, lines: list[dict]) -> None:
    p.write_text("\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8")


@pytest.mark.asyncio
@pytest.mark.regression
async def test_tools_floor_forces_balanced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Use test-hash embedder and dataset.
    from signalgate.embeddings import HashEmbedder

    emb = HashEmbedder(dim=16)
    e_easy = await emb.embed("easy\n\n[tools_present=False;json_required=False]")
    e_hard = await emb.embed("hard\n\n[tools_present=False;json_required=False]")

    dataset_path = tmp_path / "knn.jsonl"
    write_jsonl(
        dataset_path,
        [
            {
                "id": "1",
                "label": "budget",
                "embedding": e_easy.tolist(),
                "created_at": "2026-03-01T00:00:00Z",
            },
            {
                "id": "2",
                "label": "premium",
                "embedding": e_hard.tolist(),
                "created_at": "2026-03-01T00:00:01Z",
            },
        ],
    )

    manifest = {
        "version": "0.1.0",
        "providerPreference": ["openai"],
        "models": {
            "openai": {
                "provider": "openai",
                "model_id": "gpt-4.1-mini",
                "eligible_tiers": ["budget", "balanced", "premium"],
                "supports": {"tools": True, "json_schema": True, "streaming": False},
                "limits": {"context_window_tokens": 8192, "max_output_tokens": 2048},
                "pricing": {"input_usd_per_1m": 1.0, "output_usd_per_1m": 1.0},
            }
        },
        "tiers": {"budget": ["openai"], "balanced": ["openai"], "premium": ["openai"]},
    }
    manifest_path = tmp_path / "manifest.json"
    write_json(manifest_path, manifest)

    config = {
        "version": "0.1.0",
        "server": {"host": "127.0.0.1", "port": 8765},
        "paths": {
            "manifest_path": str(manifest_path),
            "knn_dataset_path": str(dataset_path),
            "embedding_model_path": "test-hash:16",
        },
        "classifier": {
            "enabled": True,
            "sim_threshold": 0.0,
            "margin_threshold": 0.0,
            "min_tier_for_high_risk": "balanced",
        },
        "upstreams": {
            "openai": {"base_url": "https://api.openai.com/v1", "api_key_env": "OPENAI_API_KEY"}
        },
    }
    config_path = tmp_path / "config.json"
    write_json(config_path, config)
    monkeypatch.setenv("SIGNALGATE_CONFIG_PATH", str(config_path))

    artifacts = load_and_validate()
    rt = RuntimeState(artifacts)

    payload = {
        "model": "signalgate/auto",
        "messages": [{"role": "user", "content": "easy"}],
        "tools": [
            {"type": "function", "function": {"name": "x", "parameters": {"type": "object"}}}
        ],
    }
    caps = required_caps_from_request(payload, streaming_supported=False)
    tier, _sim = await rt.classify_tier(payload, caps)

    assert tier in ("balanced", "premium")
    assert tier != "budget"
