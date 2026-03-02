from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional


@dataclass(frozen=False)
class SGError(Exception):
    code: str
    message: str
    status_code: int = 500
    retryable: bool = False
    upstream: Optional[dict[str, Any]] = None


class SGUnauthorized(SGError):
    pass


def sg_bad_request(message: str) -> SGError:
    return SGError(code="SG_BAD_REQUEST", message=message, status_code=400, retryable=False)


def sg_unauthorized(message: str = "Unauthorized") -> SGError:
    return SGError(code="SG_UNAUTHORIZED", message=message, status_code=401, retryable=False)


def sg_payload_too_large(message: str = "Payload too large") -> SGError:
    return SGError(code="SG_PAYLOAD_TOO_LARGE", message=message, status_code=413, retryable=False)


def sg_queue_full(message: str = "Queue full") -> SGError:
    return SGError(code="SG_QUEUE_FULL", message=message, status_code=429, retryable=True)


def sg_no_candidates(message: str = "No upstream candidates") -> SGError:
    return SGError(code="SG_NO_CANDIDATES", message=message, status_code=503, retryable=True)


def sg_breaker_open(message: str = "Circuit breaker open") -> SGError:
    return SGError(code="SG_BREAKER_OPEN", message=message, status_code=503, retryable=True)


def sg_upstream_timeout(upstream: dict[str, Any], message: str = "Upstream timeout") -> SGError:
    return SGError(
        code="SG_UPSTREAM_TIMEOUT",
        message=message,
        status_code=503,
        retryable=True,
        upstream=upstream,
    )


def sg_upstream_rate_limit(
    upstream: dict[str, Any], message: str = "Upstream rate limit"
) -> SGError:
    return SGError(
        code="SG_UPSTREAM_RATE_LIMIT",
        message=message,
        status_code=429,
        retryable=True,
        upstream=upstream,
    )


def sg_upstream_5xx(upstream: dict[str, Any], message: str = "Upstream error") -> SGError:
    return SGError(
        code="SG_UPSTREAM_5XX",
        message=message,
        status_code=503,
        retryable=True,
        upstream=upstream,
    )
