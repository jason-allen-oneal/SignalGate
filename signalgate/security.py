from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from urllib.parse import urlparse

from .errors import SGError


@dataclass(frozen=True)
class SecurityConfig:
    auth_enabled: bool = False
    auth_header: str = "x-signalgate-token"
    auth_token_env: str = "SIGNALGATE_TOKEN"
    auth_allow_health: bool = True

    max_body_bytes: int = 1_000_000

    upstream_allow_http: bool = False
    upstream_allowlist: dict[str, list[str]] | None = None

    forward_user_mode: str = "hash"  # drop|hash|passthrough
    user_hash_salt_env: str = "SIGNALGATE_USER_SALT"

    request_fields_mode: str = "passthrough"  # passthrough|strip_unknown


def load_security_config(cfg_raw: dict) -> SecurityConfig:
    sec = cfg_raw.get("security", {}) or {}
    return SecurityConfig(
        auth_enabled=bool(sec.get("auth", {}).get("enabled", False)),
        auth_header=str(sec.get("auth", {}).get("header", "x-signalgate-token")).lower(),
        auth_token_env=str(sec.get("auth", {}).get("token_env", "SIGNALGATE_TOKEN")),
        auth_allow_health=bool(sec.get("auth", {}).get("allow_health", True)),
        max_body_bytes=int(sec.get("max_body_bytes", 1_000_000)),
        upstream_allow_http=bool(sec.get("upstreams", {}).get("allow_http", False)),
        upstream_allowlist=sec.get("upstreams", {}).get("allowlist"),
        forward_user_mode=str(sec.get("forward_user", {}).get("mode", "hash")),
        user_hash_salt_env=str(sec.get("forward_user", {}).get("salt_env", "SIGNALGATE_USER_SALT")),
        request_fields_mode=str((sec.get("request_fields") or {}).get("mode", "passthrough")),
    )


def enforce_upstream_url(url: str, *, provider: str, sec: SecurityConfig) -> None:
    p = urlparse(url)
    if not p.scheme or not p.netloc:
        raise SGError(
            code="SG_INTERNAL", message=f"Invalid upstream base_url for {provider}", status_code=500
        )

    if p.scheme != "https" and not sec.upstream_allow_http:
        raise SGError(
            code="SG_INTERNAL",
            message=f"Insecure upstream scheme for {provider} ({p.scheme})",
            status_code=500,
        )

    if sec.upstream_allowlist and provider in sec.upstream_allowlist:
        allowed = sec.upstream_allowlist[provider]
        host = p.hostname or ""
        if host not in allowed:
            raise SGError(
                code="SG_INTERNAL",
                message=f"Upstream host not allowlisted for {provider}: {host}",
                status_code=500,
            )


def maybe_forward_user(user: str | None, sec: SecurityConfig) -> str | None:
    if not user:
        return None

    mode = sec.forward_user_mode
    if mode == "drop":
        return None
    if mode == "passthrough":
        return user

    # hash
    salt = os.environ.get(sec.user_hash_salt_env, "")
    raw = f"{salt}:{user}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()
