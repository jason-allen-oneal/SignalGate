# Load testing

SignalGate includes a minimal load test profile that does not require external tools.

## Quick start

1) Start SignalGate locally (docker compose or uvicorn).
2) Run the load test:

```bash
uv run python scripts/load_test.py --base-url http://127.0.0.1:8765 --seconds 30 --concurrency 50
```

## What this is

- A repeatable smoke load profile intended to catch unbounded queue growth, obvious latency regressions, and error spikes.

## What this is not

- A substitute for a full performance harness (k6/locust/vegeta) or production benchmarking.
