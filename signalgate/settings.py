from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .schemas import load_json


@dataclass(frozen=True)
class ServerConfig:
    host: str = "127.0.0.1"
    port: int = 8765
    log_level: str = "info"
    router_wall_deadline_seconds: float = 60.0


@dataclass(frozen=True)
class PathsConfig:
    manifest_path: str
    knn_dataset_path: str | None = None
    knn_index_path: str | None = None
    embedding_model_path: str | None = None


@dataclass(frozen=True)
class UpstreamConfig:
    kind: str
    base_url: str | None
    api_key_env: str
    api_version: str | None = None
    default_model: str | None = None


@dataclass(frozen=True)
class FeaturesConfig:
    enable_streaming: bool = False
    enable_shadow_mode: bool = False
    enable_canary: bool = False
    enable_two_phase_tools: bool = False
    enable_auto_tuning: bool = False
    enable_response_debug: bool = False


@dataclass(frozen=True)
class RuntimeConfig:
    version: str
    server: ServerConfig
    paths: PathsConfig
    upstreams: dict[str, UpstreamConfig]
    features: FeaturesConfig
    raw: dict[str, Any]


def load_runtime_config() -> tuple[RuntimeConfig, dict[str, Any]]:
    """Load runtime config JSON and return (typed_config, raw_dict).

    Config path selection:
    - SIGNALGATE_CONFIG_PATH env var
    - else "./config.json" if present
    - else docs/config.example.json
    """

    p = os.environ.get("SIGNALGATE_CONFIG_PATH")
    if not p:
        if Path("config.json").exists():
            p = "config.json"
        else:
            p = str(Path(__file__).resolve().parent.parent / "docs" / "config.example.json")

    raw = load_json(p)

    server_raw = raw.get("server", {})
    paths_raw = raw.get("paths", {})
    upstreams_raw = raw.get("upstreams", {})
    features_raw = raw.get("features", {})

    upstreams: dict[str, UpstreamConfig] = {}

    if not isinstance(upstreams_raw, dict) or not upstreams_raw:
        upstreams_raw = {}

    for name, u in upstreams_raw.items():
        if not isinstance(u, dict):
            continue

        kind = u.get("kind")
        if not kind:
            # Backward compatibility: infer only for legacy keys.
            if name == "openai":
                kind = "openai_compat"
            elif name == "gemini":
                kind = "gemini"
            else:
                raise ValueError(
                    f"Upstream '{name}' missing kind (expected openai_compat|gemini)"
                )

        if kind == "openai_compat":
            base_url = str(u.get("base_url", "https://api.openai.com/v1"))
            api_key_env = str(u.get("api_key_env", "OPENAI_API_KEY"))
            upstreams[name] = UpstreamConfig(
                kind="openai_compat",
                base_url=base_url,
                api_key_env=api_key_env,
                default_model=u.get("default_model"),
            )
        elif kind == "gemini":
            base_url = str(u.get("base_url", "https://generativelanguage.googleapis.com"))
            api_key_env = str(u.get("api_key_env", "GEMINI_API_KEY"))
            api_version = str(u.get("api_version", "v1beta"))
            upstreams[name] = UpstreamConfig(
                kind="gemini",
                base_url=base_url,
                api_key_env=api_key_env,
                api_version=api_version,
            )
        else:
            raise ValueError(f"Unknown upstream kind '{kind}' for '{name}'")

    cfg = RuntimeConfig(
        version=str(raw.get("version", "")),
        server=ServerConfig(
            host=str(server_raw.get("host", "127.0.0.1")),
            port=int(server_raw.get("port", 8765)),
            log_level=str(server_raw.get("log_level", "info")),
            router_wall_deadline_seconds=float(server_raw.get("router_wall_deadline_seconds", 60)),
        ),
        paths=PathsConfig(
            manifest_path=str(paths_raw.get("manifest_path", "")),
            knn_dataset_path=paths_raw.get("knn_dataset_path"),
            knn_index_path=paths_raw.get("knn_index_path"),
            embedding_model_path=paths_raw.get("embedding_model_path"),
        ),
        upstreams=upstreams,
        features=FeaturesConfig(
            enable_streaming=bool(features_raw.get("enable_streaming", False)),
            enable_shadow_mode=bool(features_raw.get("enable_shadow_mode", False)),
            enable_canary=bool(features_raw.get("enable_canary", False)),
            enable_two_phase_tools=bool(features_raw.get("enable_two_phase_tools", False)),
            enable_auto_tuning=bool(features_raw.get("enable_auto_tuning", False)),
            enable_response_debug=bool(features_raw.get("enable_response_debug", False)),
        ),
        raw=raw,
    )
    return cfg, raw
