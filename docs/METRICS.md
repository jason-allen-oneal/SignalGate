# Metrics and SLO targets

This document defines what to measure for SignalGate and suggested SLO targets.

SignalGate has two metric outputs:

- `GET /metrics` - lightweight JSON counters (safe default)
- Optional JSONL metrics sink (routing outcomes only, no prompts): `metrics.*` in config

## What to chart (dashboard spec)

Routing and volume:
- Requests per minute (total)
- Requests by tier (budget/balanced/premium)
- Requests by provider and model
- Two-phase tools rate (enabled vs escalated)

Reliability:
- Error rate (total and by error code)
- Upstream 429 rate and 5xx rate (when surfaced)
- Circuit breaker state transitions (open/half-open/closed) per model

Latency:
- End-to-end latency p50/p95/p99
- Upstream latency (if captured separately)

Cost (when pricing and token counts are available):
- Estimated USD per minute
- Estimated USD by tier and provider
- Savings percent distribution (relative to configured baseline)

## Suggested SLO targets

These are starting points. Tune them to your workload and deployment.

Availability:
- 99.9% of requests return a non-5xx response from SignalGate (excluding caller cancellations)

Latency:
- p95 end-to-end latency <= 2.0s for non-streaming chat under normal load
- p99 end-to-end latency <= 5.0s under normal load

Errors:
- SignalGate-attributed 5xx rate <= 0.1%
- Upstream 429 rate sustained <= 1% (if higher, reduce concurrency or adjust provider pool)

Routing safety:
- Tool-call requests: 0 automatic retries after tool execution is possible

## Load test profile

See `docs/LOAD_TESTING.md` for the built-in smoke load profile.
