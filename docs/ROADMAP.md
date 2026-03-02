# SignalGate - Build Roadmap

Purpose: this roadmap is the build contract. Agents use it to know what we are building and what "done" means at each stage.

Rules
- Every stage has measurable exit criteria.
- No stage is "done" until tests pass and the artifact exists in-repo.
- Keep changes reversible. Use feature flags for risky behavior.

---

## Stage 0 - Foundation (v0.1.x)
Goal: freeze the spec and project structure so implementation work does not drift.

Deliverables
- Spec: `docs/SPEC.md` updated and consistent with code and docs.
- Capability manifest schema + example:
  - `docs/manifest.schema.json`
  - `docs/manifest.example.json`
- Runtime config schema + example:
  - `docs/config.schema.json`
  - `docs/config.example.json`
- KNN dataset contract:
  - `docs/DATASET.md`
  - `docs/knn_dataset.schema.json`
- Roadmap: this file.

Exit criteria
- Spec has: endpoints, virtual model ids, `_signalgate` metadata, failure modes, circuit breakers, budgets, stickiness, shadow/canary.
- Manifest schema covers required capability fields (tools/json/streaming/limits).
- Config schema exists for thresholds/breakers/budgets/feature flags.
- Dataset contract exists for future classifier work.

---

## Stage 1 - Minimal proxy skeleton (v0.2.x)
Goal: a running OpenAI-compatible service that can be called locally and forwards to a single fixed upstream.

Deliverables
- Runnable service on `127.0.0.1:8765` (port configurable).
- Endpoints implemented:
  - `GET /healthz`
  - `GET /readyz`
  - `GET /v1/models` (returns SignalGate virtual model ids)
  - `POST /v1/chat/completions` (non-streaming)
- Request id generation and `_signalgate.router_version` surfaced.

Exit criteria
- `curl` to `/v1/chat/completions` returns a valid OpenAI-style response.
- `_signalgate.request_id` present in response.
- Unit tests for request/response shape and error code mapping.

---

## Stage 2 - Manifest-driven gating (v0.3.x)
Goal: bring the manifest online and enforce capability gates deterministically.

Deliverables
- Load/validate manifest at startup against `docs/manifest.schema.json`.
- Capability gating implemented (tools/json/streaming/context window).
- `SG_NO_CANDIDATES` behavior implemented.

Exit criteria
- Service refuses to start on invalid manifest.
- Requests that require tools/JSON correctly filter candidates.
- Tests cover each gate and `SG_NO_CANDIDATES`.

---

## Stage 3 - Tier classification (v0.4.x)
Goal: implement tier selection (budget/balanced/premium) via embedding + KNN with uncertainty handling.

Deliverables
- Embedding adapter interface (local or provider) with caching by prompt hash.
- KNN index loader and lookup (dataset format defined).
- Uncertainty logic:
  - similarity threshold
  - margin threshold
  - high-risk floor: tools/JSON => tier >= balanced

Exit criteria
- Given a small labeled fixture dataset, tier prediction is deterministic.
- Embedding cache hit/miss metrics exposed.
- Tests: threshold and margin promotion to balanced.

---

## Stage 4 - Provider/model selection engine (v0.5.x)
Goal: choose the routed provider/model within a tier using scoring + provider preference.

Deliverables
- Candidate scoring function (cost + latency + health penalty + preference bias).
- Provider preference default: Gemini first, OpenAI second.
- Stickiness via consistent hashing (optional toggle, but implemented here).

Exit criteria
- For a given conversation key, selection is stable across restarts.
- If a candidate becomes unhealthy, selection fails over deterministically.
- Tests: stickiness stability, preference bias, health penalty effect.

---

## Stage 5 - Robustness primitives (v0.6.x)
Goal: survive real traffic: backpressure, breaker logic, deterministic failover, and safe retry.

Deliverables
- Bounded concurrency + bounded queue with `SG_QUEUE_FULL`.
- Circuit breakers per model:
  - rolling window stats
  - trip thresholds
  - cooldown + half-open trial
- Deterministic retry ladders for:
  - no-tools requests
  - tools/JSON requests
- Standardized `_signalgate.error.*` on error responses.

Exit criteria
- Fault injection tests pass (timeouts/429/5xx).
- Breakers trip and recover as specified.
- No unbounded queue growth under load testing.

---

## Stage 6 - Streaming + tool-call safety (v0.7.x)
Goal: support streaming and ensure we do not duplicate side effects.

Deliverables
- `stream=true` support for `POST /v1/chat/completions`.
- Side-effect safe retry enforcement:
  - never retry after tool execution may have occurred
- Optional: `signalgate/chat-only` virtual model behavior.

Exit criteria
- Streaming responses are valid and do not leak router internals.
- Retry logic behaves correctly in streaming and tool-call flows.

---

## Stage 7 - Shadow mode and canary controls (v0.8.x)
Goal: deploy safely without changing behavior globally.

Deliverables
- Shadow mode: compute decisions, route to fixed upstream.
- Canary routing:
  - allowlist and/or percentage
  - sticky hashing so users do not flip-flop
- Decision trace logging (always-on) and debug response toggles.

Exit criteria
- Shadow mode produces metrics without affecting upstream selection.
- Canary selection is stable and reversible.
- Audit logs show tier, similarity, routed model, and failover reasons.

---

## Stage 8 - Budget guardrails + two-phase tools (v0.9.x)
Goal: keep spend bounded and reduce premium usage in tool-heavy workloads.

Deliverables
- Budget enforcement (hour/day, per tier/provider) with deterministic degradation.
- Optional two-phase tool routing (plan-only then execute) behind a feature flag.
- Shadow scoring hooks for threshold tuning (bounded auto-tuning optional).

Exit criteria
- Simulated budget exhaustion produces the documented degradation behavior.
- Two-phase mode can be enabled for a subset of traffic and produces cost deltas.

---

## Stage 9 - OpenClaw integration package (v0.10.x)
Goal: make it easy to wire in without touching existing pipelines.

Deliverables
- Integration docs for OpenClaw (how to point baseUrl to SignalGate).
- Example OpenClaw config snippets (do not apply automatically).
- Operational runbook: start/stop, log locations, common errors.

Exit criteria
- A new OpenClaw agent can be pointed at SignalGate and works end-to-end.
- Rollback path documented (switch model primary back).

---

## Stage 10 - v1.0.0 GA
Goal: stable enough to become the primary model routing path for your environment.

Deliverables
- Default config tuned for your real workload.
- Full regression suite + load test profile.
- Metrics dashboard spec (what to chart) and SLO targets.
- "Incident mode" toggles:
  - pin to balanced
  - disable classification
  - disable two-phase
  - disable auto-tuning

Exit criteria
- 30 days of canary success with no P0/P1 incidents attributed to SignalGate.
- Documented SLOs met (availability, p95 latency budget, error-rate targets).
- Operator confidence: clear rollback and clear failure signals.
