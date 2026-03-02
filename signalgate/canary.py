from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class CanaryConfig:
    enabled: bool = False
    mode: str = "percent"  # "percent" or "allowlist"
    percent: float = 0.0
    allowlist: List[str] = None
    hash_salt: str = "signalgate"


def is_canary_user(user_id: str | None, cfg: CanaryConfig) -> bool:
    if not cfg.enabled:
        return False

    if cfg.mode == "allowlist":
        return user_id in (cfg.allowlist or [])

    if not user_id:
        return False

    # Percent-based sticky canary
    h = hashlib.sha256(f"{cfg.hash_salt}:{user_id}".encode("utf-8")).hexdigest()
    # Use first 8 chars for int conversion
    val = int(h[:8], 16) % 100
    return val < cfg.percent
