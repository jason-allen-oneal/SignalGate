# SignalGate - Status Checklist

This file mirrors `docs/ROADMAP.md` as a single operational checklist.

Conventions
- Mark done items with `[x]`.
- Add links to PRs/commits or notes under each stage.
- Do not delete completed items. Append notes.

---

## Stage 0 - Foundation (v0.1.x)
- [x] Spec drafted and consistent (`docs/SPEC.md`)
- [x] Capability manifest schema (`docs/manifest.schema.json`)
- [x] Capability manifest example (`docs/manifest.example.json`)
- [x] Runtime config schema (`docs/config.schema.json`)
- [x] Runtime config example (`docs/config.example.json`)
- [x] KNN dataset contract (`docs/DATASET.md`)
- [x] KNN dataset record schema (`docs/knn_dataset.schema.json`)
- [x] Roadmap drafted (`docs/ROADMAP.md`)

Notes
- 

---

## Stage 1 - Minimal proxy skeleton (v0.2.x)
- [x] Runnable service on `127.0.0.1:8765` (port configurable)
- [x] `GET /healthz`
- [x] `GET /readyz`
- [x] `GET /v1/models` returns `signalgate/*`
- [x] `POST /v1/chat/completions` (non-streaming)
- [x] `_signalgate.request_id` + `_signalgate.router_version`
- [x] Unit tests for shape + error mapping

Notes
- Implemented in `signalgate/app.py` and exercised via pytest using ASGI transport.

---

## Stage 2 - Manifest-driven gating (v0.3.x)
- [x] Load + validate manifest at startup (schema-enforced)
- [x] Enforce capability gates (tools/json/streaming/context)
- [x] `SG_NO_CANDIDATES` behavior + tests

Notes
- Capability gating implemented in `signalgate/routing.py` (manifest-driven).
- Stage 1 routing currently forwards via OpenAI upstream only; non-OpenAI providers will error deterministically.

---

## Stage 3 - Tier classification (v0.4.x)
- [x] Embedding adapter interface + caching
- [x] KNN index loader + lookup (fixture dataset)
- [x] Uncertainty handling (threshold + margin)
- [x] High-risk floor: tools/JSON => tier >= balanced
- [x] Tests for threshold promotion

Notes
- Local embeddings supported via `llama-cpp-python` (install with `uv sync --extra embed`).
- Tests use `test-hash:<dim>` embedder to avoid compiled deps.

---

## Stage 4 - Provider/model selection engine (v0.5.x)
- [x] Candidate scoring (cost/latency/health/preference)
- [x] Provider preference default: Gemini first, OpenAI second
- [x] Stickiness (consistent hashing) + tests
- [x] Deterministic failover on unhealthy candidate

Notes
- Health-aware ordering avoids repeatedly selecting a model with an open breaker when healthy alternatives exist.

---

## Stage 5 - Robustness primitives (v0.6.x)
- [x] Backpressure: bounded concurrency + bounded queue
- [x] `SG_QUEUE_FULL` responses
- [x] Circuit breakers: rolling stats, trip, cooldown, half-open
- [x] Deterministic retry ladders (no-tools vs tools/JSON)
- [x] `_signalgate.error.*` returned on errors
- [x] Fault injection tests (timeouts/429/5xx)

Notes
- Implemented global/provider/model semaphores and per-model circuit breakers with cooldown + half-open.

---

## Stage 6 - Streaming + tool-call safety (v0.7.x)
- [x] Streaming support (`stream=true`)
- [x] Side-effect safe retry enforcement (no retry after tools may execute)
- [x] Optional `signalgate/chat-only` behavior

Notes
- Streaming implemented for OpenAI upstream.
- Gemini streaming implemented via streamGenerateContent translated to OpenAI SSE frames.

---

## Stage 7 - Shadow mode and canary controls (v0.8.x)
- [x] Shadow mode toggle (compute decision, fixed upstream)
- [x] Canary: allowlist and/or percent
- [x] Sticky hashing for canary stability
- [x] Decision trace logging always-on
- [x] Debug response toggles (neighbors/trace)

Notes
- Decision trace available in `_signalgate.decision_trace` when `features.enable_response_debug` is true.

---

## Stage 8 - Budget guardrails + two-phase tools (v0.9.x)
- [x] Budget enforcement (hour/day per tier/provider)
- [x] Deterministic degradation behavior documented and tested
- [x] Two-phase tools (plan-only then execute) behind flag
- [x] Shadow scoring hooks for threshold tuning

Notes
- Budget Manager tracks USD spend per tier/provider.

---

## Stage 9 - OpenClaw integration package (v0.10.x)
- [x] OpenClaw integration docs
- [x] Example config snippets (no auto-apply)
- [x] Operational runbook (ops + rollback)

Notes
- Integration guide created in `docs/OPENCLAW_INTEGRATION.md`.

---

## Stage 10 - v1.0.0 GA
- [ ] Default config tuned on real workload
- [x] Full regression suite + load test profile
- [x] Metrics dashboard spec + SLO targets
- [x] Incident mode toggles (pin balanced, disable classifier, etc)
- [ ] 30-day canary success (no SignalGate-attributed P0/P1)

Notes
- Incident mode supported via `incident_pin_tier` and `incident_disable_classifier`.
- Load profile: `scripts/load_test.py` + `docs/LOAD_TESTING.md`.
- Metrics spec: `docs/METRICS.md`. `GET /metrics` implemented (JSON counters).
- Cost accounting now populates `_signalgate.cost` when possible; budgets consume the estimate.
