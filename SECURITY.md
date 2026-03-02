# Security Policy

## Reporting a Vulnerability

If you believe you have found a security vulnerability in SignalGate, please do not open a public issue.

Instead, send a report with:
- what you found
- impact (what an attacker can do)
- reproduction steps
- suggested fix (if you have one)

Contact: open a private message to the maintainer on GitHub, or use the repository's configured security advisory feature if enabled.

## Security Model (high level)

SignalGate is typically deployed on loopback (127.0.0.1) or a Unix domain socket.

Key controls:
- Optional auth gate (`security.auth.*`).
- Upstream HTTPS enforcement + provider allowlist (`security.upstreams.*`).
- Request field stripping mode (`security.request_fields.mode=strip_unknown`).
- By default, user identifiers are hashed before forwarding upstream (`security.forward_user.mode=hash`).

Operational note: do not expose SignalGate directly to the public internet without an authenticating reverse proxy and explicit rate limits.
