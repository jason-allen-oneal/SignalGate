from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import SGError
from .schemas import load_json
from .security import SecurityConfig, enforce_upstream_url, load_security_config
from .settings import RuntimeConfig, load_runtime_config
from .version import __version__


@dataclass
class LoadedArtifacts:
    config: RuntimeConfig
    config_raw: dict[str, Any]
    config_schema: dict[str, Any]
    security: SecurityConfig
    manifest_raw: dict[str, Any]
    manifest_schema: dict[str, Any]

    @property
    def router_version(self) -> str:
        # Deterministic composition. Classifier artifacts version not yet implemented.
        from .util import stable_hash

        manifest_version = str(self.manifest_raw.get("version", ""))
        mh = stable_hash(self.manifest_raw)[:12]
        return (
            f"code={__version__};config={self.config.version};manifest={manifest_version};manifest_hash={mh}"
        )


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_and_validate() -> LoadedArtifacts:
    root = _project_root()
    config_schema = load_json(root / "docs" / "config.schema.json")
    manifest_schema = load_json(root / "docs" / "manifest.schema.json")

    cfg, cfg_raw = load_runtime_config()

    # Validate config and manifest against their schemas.
    # If invalid, fail fast at startup.
    import jsonschema

    try:
        jsonschema.validate(cfg_raw, config_schema)
    except jsonschema.ValidationError as e:
        raise SGError(
            code="SG_INTERNAL",
            message=f"Invalid runtime config: {e.message}",
            status_code=500,
            retryable=False,
        ) from e

    if not cfg.paths.manifest_path:
        raise SGError(
            code="SG_INTERNAL",
            message="Runtime config missing paths.manifest_path",
            status_code=500,
            retryable=False,
        )

    manifest_raw = load_json(cfg.paths.manifest_path)

    try:
        jsonschema.validate(manifest_raw, manifest_schema)
    except jsonschema.ValidationError as e:
        raise SGError(
            code="SG_INTERNAL",
            message=f"Invalid capability manifest: {e.message}",
            status_code=500,
            retryable=False,
        ) from e

    if not cfg.version:
        raise SGError(code="SG_INTERNAL", message="Runtime config missing version", status_code=500)

    sec = load_security_config(cfg_raw)

    # Enforce upstream constraints
    for name, u in cfg.upstreams.items():
        if u.base_url:
            enforce_upstream_url(u.base_url, provider=name, sec=sec)

    return LoadedArtifacts(
        config=cfg,
        config_raw=cfg_raw,
        config_schema=config_schema,
        security=sec,
        manifest_raw=manifest_raw,
        manifest_schema=manifest_schema,
    )
