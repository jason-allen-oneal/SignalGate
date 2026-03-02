# SignalGate
[![ci](https://github.com/jason-allen-oneal/SignalGate/actions/workflows/ci.yml/badge.svg)](https://github.com/jason-allen-oneal/SignalGate/actions/workflows/ci.yml)
[![License](https://img.shields.io/badge/license-AGPLv3-blue.svg)](LICENSE)

SignalGate is a semantic routing layer for OpenClaw. It exposes an OpenAI-compatible API on loopback and routes each request to the right upstream model tier (budget, balanced, premium) using local embeddings + KNN and hard capability gates.

Status: released. Current version: 1.0.3

## Why it exists
- Stop defaulting every prompt to the most expensive model.
- Keep OpenClaw pipelines intact (no prompt rewriting, no rule forests).
- Make routing observable, deterministic under failure, and safe for tool-driven automation.

## Architecture (high level)

### Entry point
- Local OpenAI-compatible base URL:
  - `http://127.0.0.1:8765/v1`
- Primary endpoints:
  - `GET /healthz`
  - `GET /readyz`
  - `GET /v1/models`
  - `GET /metrics` (lightweight JSON counters)
  - `POST /v1/chat/completions` (streaming and non-streaming)

### Virtual models
- `signalgate/auto` - semantic tier routing
- `signalgate/budget` - force budget tier
- `signalgate/balanced` - force balanced tier
- `signalgate/premium` - force premium tier
- `signalgate/chat-only` - disable tool usage for the request

### Routing pipeline
1) Security gates
- Optional auth header on loopback (raw token or `Bearer <token>`)
- Request body size limit
- Optional request field stripping

2) Capability gates (manifest-driven)
SignalGate filters candidates by required capabilities inferred from the request shape:
- tools / tool_choice
- JSON/schema response_format
- streaming
- context window and max output

3) Tier selection
- For `signalgate/auto`, SignalGate uses:
  - local embeddings (GGUF via llama.cpp)
  - KNN classifier trained on labeled workloads
  - uncertainty promotion (similarity threshold + margin threshold)
  - high-risk floor: tools/JSON => at least balanced

4) Candidate scoring + provider preference
- Provider preference biases selection (Gemini first, OpenAI second by default)
- Scoring uses manifest pricing + preference bias
- Stickiness (consistent hashing) reduces provider/model flip-flop

5) Execution + robustness
- Bounded queue and bounded concurrency (global/provider/model semaphores)
- Per-model circuit breakers (cooldown + half-open)
- Deterministic failover ladder
  - No-tools: allow one failover
  - Tools/JSON: no retry after side effects may occur

### Upstream adapters
- OpenAI upstream (chat/completions) including streaming passthrough
- Gemini upstream (generateContent / streamGenerateContent) via format adaptation (no rewriting)

## Security posture (default-secure)
Key controls are configured via `security.*` in runtime config:
- Auth token header (recommended)
- HTTPS-only upstream enforcement + hostname allowlist
- Upstream error-body redaction unless debug
- Default hashed user forwarding (or drop)
- Optional request field stripping (`strip_unknown`) to reduce pass-through surface

## Configuration
- Runtime config: `docs/config.schema.json` (example: `docs/config.example.json`)
- Capability manifest: `docs/manifest.schema.json` (example: `docs/manifest.example.json`)
- KNN dataset contract: `docs/DATASET.md`

Optional (v1.0.3):
- Two-phase tools routing: `features.enable_two_phase_tools=true` (tuning: `two_phase.min_margin_for_plan`).
- Metrics JSONL sink (routing outcomes only, no prompts): `metrics.enabled=true` + `metrics.jsonl_path`.
- Cost baseline for savings percent: `cost.baseline_model_key=<manifest model key>`.
- Cost uses upstream `usage` token counts when available. Estimation is off by default (`cost.allow_estimates=false`).

## Running

### Install
```bash
uv sync --extra dev --extra embed
```

### Start (TCP loopback)
```bash
export SIGNALGATE_CONFIG_PATH=./config.json
export SIGNALGATE_TOKEN=...  # if auth enabled
uv run signalgate
```

### Start (Unix domain socket)
In config:
- `server.uds_path=/tmp/signalgate.sock`

Run:
```bash
uv run signalgate
```

## Testing
See `docs/TESTING.md`.

## Load testing
See `docs/LOAD_TESTING.md`.

Default suite:
```bash
uv run pytest
```

Live upstream tests:
```bash
uv run pytest -m e2e
```

## OpenClaw integration
See `docs/OPENCLAW_INTEGRATION.md`.

## License
Licensed under the GNU Affero General Public License v3.0 or later (AGPL-3.0-or-later). See [LICENSE](LICENSE).
