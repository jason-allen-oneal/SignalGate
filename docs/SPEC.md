# Spec: SignalGate - semantic tier router for OpenClaw

## 0) Summary
We want a local, OpenAI-compatible proxy on `127.0.0.1:<port>` that receives normal OpenAI Chat Completions style requests from OpenClaw and forwards them to an underlying provider model chosen at call time.

Selection is made by:
- semantic classification (embedding + KNN on labeled historical workloads) -> {budget, balanced, premium}
- capability gates (tools, structured output, context window, streaming)
- provider preference weights (Gemini first, OpenAI second by default)

No prompt rewriting. Minimal policy surface.

## 1) Goals
- Reduce API costs by routing simple requests to cheaper models while preserving correctness for complex/tooling workloads.
- Provide a stable "virtual model" interface so OpenClaw configs can point at a single primary model later.
- Maintain full transparency: expose routed provider/model and cost/savings metrics.
- Fail safely: if router is unavailable, callers can fall back to existing models.

## 2) Non-goals
- No prompt rewriting, prompt compression, or chain-of-thought shaping.
- No complex rules engine. Only lightweight capability gates + similarity uncertainty handling.
- No multi-tenant auth. Do not expose directly to the public internet without an authenticating reverse proxy and explicit rate limits.

## 3) Terminology
- Tier: one of {budget, balanced, premium}.
- Provider: upstream vendor family (Gemini, OpenAI, etc).
- Model: a concrete upstream model id.
- Virtual model: a stable id served by this router (example: `signalgate/auto`).

## 4) External Interface (OpenAI-compatible)

### 4.1 Base URL
- `http://127.0.0.1:8765/v1` (port configurable)

### 4.2 Supported endpoints (minimum viable)
- `GET /v1/models`
- `POST /v1/chat/completions`

Optional but recommended:
- `GET /healthz` (liveness)
- `GET /readyz` (readiness, upstream reachability)
- `GET /metrics` (Prometheus or simple JSON)

### 4.3 Virtual model ids
Expose these models from `GET /v1/models`:
- `signalgate/auto` - normal entrypoint. SignalGate selects tier + provider + model.
- `signalgate/budget` - force tier >= budget.
- `signalgate/balanced` - force tier >= balanced.
- `signalgate/premium` - force tier >= premium.
- optional: `signalgate/chat-only` - force "no tools" for cost control and to prevent side effects.

Design rule: virtual model ids must be stable over time.

Naming: this project is called "SignalGate".

### 4.4 Response metadata
Return normal OpenAI-compatible response bodies, plus a metadata block in a namespaced field.

Recommendation:
- Add a top-level `_signalgate` object, and optionally mirror in `response.usage` via extension fields if needed.

Minimum fields:
- `_signalgate.routed_provider` (string)
- `_signalgate.routed_model` (string)
- `_signalgate.tier` (budget|balanced|premium)
- `_signalgate.similarity.top1` (float 0..1)
- `_signalgate.similarity.top2` (float 0..1)
- `_signalgate.similarity.margin` (float)
- `_signalgate.cost` (object with prompt_tokens, completion_tokens, usd_estimate, estimated_tokens)
- `_signalgate.savings_percent` (float percent, relative to configured baseline)
- `_signalgate.request_id` (string, unique per request)
- `_signalgate.router_version` (string)

Optional debug fields (guarded by config, default off):
- `_signalgate.knn_neighbors` (array of {id,label,similarity}, with ids hashed/anonymized)
- `_signalgate.decision_trace` (array of strings describing gates applied)

## 5) Routing Pipeline

### 5.1 Inputs
- The full request payload (messages, model id, tools, response_format, max_tokens, temperature, stream)
- Local router config (tier mappings, provider preferences, thresholds)
- Optional conversation key (to support stickiness)

### 5.2 Step A: Tier determination
- Compute embedding of the incoming prompt representation.
  - Representation should be consistent and minimal, for example:
    - join of the last N user messages
    - include a small summary of tool schema presence (not tool contents)
- KNN lookup against labeled embeddings -> predicted tier.

### 5.3 Step B: Uncertainty handling
If any condition triggers, promote tier to balanced:
- `top1_similarity < SIM_THRESHOLD`
- `(top1_similarity - top2_similarity) < MARGIN_THRESHOLD`

If the request requires tools/structured output, disallow budget regardless of classifier output.

### 5.4 Step C: Capability gates (hard filters)
Filter candidate upstream models by:
- Tool calling support required when `tools` present or `tool_choice` not none.
- Structured output support required when `response_format` indicates JSON or schema.
- Context window must fit estimated prompt tokens + reserved output tokens.
- Streaming support if `stream=true`.

### 5.5 Step D: Provider/model selection (soft scoring)
Among remaining candidates for the chosen tier:
- Score = cost_weight * cost_estimate + latency_weight * latency_estimate + health_penalty
- Provider preference is a bias term:
  - Gemini gets a negative bias (preferred)
  - OpenAI gets a smaller negative bias (second)
  - others neutral/positive

Optional: conversation stickiness
- Prefer the same provider/model for a session unless a hard gate or health issue forces change.

### 5.6 Step E: Execution and safe retry
- Send the request upstream.
- Retry policy must be side-effect aware:
  - If no tool calls have been executed yet: allow a single retry escalation (budget -> balanced -> premium).
  - If tool calls may have executed: do not retry automatically.

### 5.7 Side-effect risk detection (request-shape based)
Goal: reduce the worst class of failures (duplicated actions and incorrect structured outputs) without inspecting or rewriting prompt text.

Derive a `risk_profile` from request fields:
- High risk if any:
  - `tools` present or `tool_choice` not none
  - `response_format` requires JSON/schema
  - explicit "execution" mode indicated by the caller (future extension)

Policy:
- If high risk: enforce `tier >= balanced`.
- If high risk: disable multi-step retries (max 1 attempt; or 1 failover only if you can guarantee no side effects).
- If virtual model is `signalgate/chat-only`: force tool usage off and treat as low-risk.

### 5.8 Two-phase routing for tool workloads (optional)
This is an opt-in mode to reduce premium spend on tool-heavy conversations.

Pattern:
- Phase 1 (plan-only): use a cheaper model to produce a tool plan with strict constraints (no tool execution).
- Phase 2 (execute): only if the plan requires tool calls or uncertainty is high, route the execution request to a premium tool-capable model.

Constraints:
- No prompt rewriting. This is request orchestration only.
- Must be deterministic and auditable (decision trace).
- Must be disable-able globally and per virtual model.

### 5.9 Stickiness via consistent hashing
To reduce style drift and jittery performance:
- Use a stable conversation key (session id / channel id / user id hash) to pick a preferred provider/model within a tier.
- Keep stickiness until a hard gate trips (capability mismatch) or health logic forces failover.

### 5.10 Shadow scoring and threshold tuning (optional but recommended)
Always-on "shadow" metrics can improve routing quality without production risk.

- Shadow mode: compute tier/provider decisions, but route to a fixed upstream.
- Record:
  - similarity scores, predicted tier, chosen candidates
  - actual latency, error, retries, 429s
  - lightweight outcome signals (follow-up correction prompts, user explicit dissatisfaction flags when available)

Tuning:
- Periodically adjust `SIM_THRESHOLD` and `MARGIN_THRESHOLD` within bounded ranges based on observed misroutes.
- Never tune below safety floors for high-risk request shapes (tools/JSON).

### 5.11 Budget guardrails (policy layer)
Add a cost safety net that works even if classification drifts.

- Maintain per-tier and per-provider token/USD budgets (hourly/daily).
- If premium spend exceeds budget:
  - temporarily raise thresholds to promote more traffic to balanced
  - or require explicit `signalgate/premium` to override

## 6) Tier Mappings (configuration)
Router config defines, per tier, an ordered pool of candidates.

### 6.1 Capability manifest (source of truth)
Robustness rule: never hardcode model capabilities in routing code. Capabilities drift and vendors change behavior. Maintain a config-driven manifest and treat it as authoritative for gating.

Schema:
- `docs/manifest.schema.json` defines the JSON Schema for the manifest.
- CI should validate the manifest against this schema before deploy.

Runtime config:
- `docs/config.schema.json` defines the JSON Schema for SignalGate runtime configuration.
- `docs/config.example.json` provides a starting point.
- Config should specify `manifest_path`, classifier thresholds, breaker settings, budgets, feature flags, and (optionally) a cost baseline model key for `savings_percent`.

Each upstream model entry should include:
- provider (gemini|openai|other)
- model_id (string)
- tier eligibility (budget/balanced/premium)
- supports:
  - tools (boolean)
  - json_schema (boolean)
  - streaming (boolean)
- limits:
  - context_window_tokens (int)
  - max_output_tokens (int)
- pricing (optional but recommended): input_usd_per_1m, output_usd_per_1m
- routing weights: cost_weight, latency_weight, preference_bias
- health controls: breaker_enabled, custom_timeouts (optional overrides)

SignalGate must validate manifest at startup and refuse to start if required fields are missing.

### 6.2 Tier pools
Define tier pools as ordered candidate lists referencing manifest entries.

Example:
- tier.budget: [gemini_flash, openai_mini]
- tier.balanced: [gemini_flash_preview, openai_small]
- tier.premium: [gemini_pro, openai_top]

Provider/model ids should match whatever OpenClaw uses today.

### 6.3 Capability gate behavior
- All hard filters (tools, JSON, context window, streaming) must be computed from the manifest.
- If a request requires a capability and no candidates match, return `SG_NO_CANDIDATES` (or promote tier if configured).

### 6.4 Manifest versioning
- Any manifest change must bump `_signalgate.router_version`.
- Maintain a changelog entry (at least: date, changed models, reason).

## 7) Cost accounting
- Track tokens in/out from upstream usage fields.
- Maintain a price catalog for each upstream model (manual config).
- Baseline cost: configured reference model (likely the current default).
- Savings percent: `1 - (routed_cost / baseline_cost)`.

If prices are unknown, still provide transparent fields but mark as `null`/`unknown`.

## 8) Observability
Log events with:
- request id
- virtual model id
- tier decision + similarity scores
- routed provider/model
- latency (router + upstream)
- retry events
- cost estimates

Privacy: default to storing prompt hashes and neighbor ids, not raw prompt text.

Response debug policy (robustness):
- Always log neighbor ids/labels/similarity (hashed ids; label is the class label, not user data).
- Do not include neighbors in the response by default.
- Enable response neighbors only under an explicit debug flag, because response metadata may flow into upstream logs.

## 9) Security model
- Bind to loopback only.
- No external auth assumed.
- Do not log secrets.
- If embeddings are computed via an external API, treat that as equal-sensitivity to the main model call.

## 10) Failure modes and safe defaults
- If router cannot embed/classify: default to balanced.
- If no candidate passes capability gates: default to premium (or fail with a clear error if strict mode).
- If router is down: return fast error so OpenClaw can fall back.

## 11) Robustness requirements (must-have)

Design principle: when SignalGate is primary, correctness and uptime matter more than perfect routing. Under uncertainty or partial failure, it must converge to a safe, predictable behavior.

### 11.1 Timeouts and backpressure (defaults)
- Router wall clock deadline: 60s (hard cap).
- Upstream timeouts (per attempt):
  - connect timeout: 3s
  - first-byte timeout: 15s (non-streaming)
  - read timeout: 60s (streaming)
- Concurrency limits (semaphores):
  - global upstream max in-flight: 16
  - per provider max in-flight: 8
  - per model max in-flight: 4
- Queue:
  - max queued requests: 200
  - when exceeded: fail fast with 503 and a clear error code in `_signalgate`.

Rationale: bounded latency and bounded memory win. Fast failure is survivable; unbounded queues are not.

### 11.2 Circuit breakers and health scoring (defaults)
Maintain per-model rolling stats with a short window to react quickly:
- rolling window: 120s
- minimum samples before tripping: 20
- trip conditions (any):
  - consecutive failures >= 5
  - error rate >= 30%
  - timeout rate >= 20%
- cooldown: 120s (model is removed from candidate pools)
- half-open: after cooldown, allow 1 trial request; if success, close breaker; if failure, reopen.

Health scoring should also incorporate:
- recent 429 rate (rate limiting)
- median and p95 latency per model

Expose summarized health via `/readyz` and incorporate into selection as `health_penalty`.

### 11.3 Deterministic idempotency and safe retries
- Generate `_signalgate.request_id` for every request.
- Accept an explicit idempotency key if provided by caller and forward upstream where supported.
- Auto-retry rules:
  - Never auto-retry after a tool call may have executed (side effects).
  - Otherwise allow at most 1 retry.

### 11.4 Retry ladder and failover order (deterministic)
Failover should be predictable and aligned with your provider priorities.

Default provider preference order:
- Gemini first
- OpenAI second
- Other providers last

Default retry ladder (no-tools requests):
1) try chosen tier's preferred Gemini model
2) on timeout/5xx: retry once to the same tier's preferred OpenAI model
3) if still failing: return error (do not keep bouncing)

Default retry ladder (tools present or structured output required):
1) try balanced-or-higher preferred Gemini tool-capable model
2) on timeout/5xx: retry once to OpenAI premium tool-capable model
3) if still failing: return error

429 handling:
- Do not immediate-retry the same model.
- Prefer failover to the next provider within the same tier if available.
- If no alternative exists, return 429 upstream to caller quickly (do not stall inside SignalGate).

### 11.5 Caching
- Cache embeddings by stable prompt hash.
- Cache classifier output (tier + similarity scores) for a short TTL (default 30s) to absorb bursts.
- Do not cache full completions (too risky for privacy and correctness).

### 11.6 Shadow mode and canary
- Shadow mode must be a first-class toggle: compute decisions, but route to a fixed upstream.
- Canary mode: route by allowlist and/or percentage. Must be consistent (sticky hashing) so users do not flip-flop.

### 11.7 Decision trace (debugging without chaos)
- Always log a decision trace (gates applied, candidates filtered, why failover happened).
- Only return `decision_trace` and KNN neighbors in responses when debug mode is explicitly enabled.

### 11.8 Standard error codes and client-facing behavior
When SignalGate returns an error, it should be:
- fast (bounded)
- explicit (machine-parsable)
- safe (no leaking sensitive content)

Add these fields on error responses:
- `_signalgate.error.code` (string)
- `_signalgate.error.message` (short, ops-safe)
- `_signalgate.error.retryable` (boolean)
- `_signalgate.error.upstream` (optional: provider/model + http status category)

Recommended error codes:
- `SG_BAD_REQUEST` - invalid input payload
- `SG_QUEUE_FULL` - backpressure triggered
- `SG_EMBEDDING_FAILED` - embedding computation failed
- `SG_CLASSIFIER_FAILED` - KNN lookup failed
- `SG_NO_CANDIDATES` - no upstream models satisfied capability gates
- `SG_BREAKER_OPEN` - circuit breaker open for all candidates
- `SG_UPSTREAM_TIMEOUT` - upstream timed out
- `SG_UPSTREAM_RATE_LIMIT` - upstream 429
- `SG_UPSTREAM_5XX` - upstream server error
- `SG_INTERNAL` - unexpected router error

HTTP status mapping (suggested):
- 400: `SG_BAD_REQUEST`
- 429: `SG_QUEUE_FULL` or `SG_UPSTREAM_RATE_LIMIT`
- 503: `SG_BREAKER_OPEN`, `SG_NO_CANDIDATES`, `SG_UPSTREAM_TIMEOUT` (if you want callers to fail over)
- 500: `SG_INTERNAL`

### 11.9 Stickiness, drift control, and regression safety
- Stickiness (consistent hashing) must be stable across restarts given the same inputs.
- Any change to:
  - embedding model
  - KNN index/training set
  - similarity thresholds
  - tier mappings
  requires a version bump in `_signalgate.router_version` and must be evaluated in shadow mode first.

### 11.10 Adaptive thresholds (auto-tuning) with guardrails
If auto-tuning is enabled:
- Tuning must be bounded (min/max) and reversible.
- Apply changes slowly (example: once per day) and only when sample size is sufficient.
- Separate thresholds for high-risk vs low-risk request shapes.
- Keep a manual override to pin thresholds during incident response.

### 11.11 Budget guardrails (runtime enforcement)
- Enforce budgets at the router, not only via dashboards.
- Budgets should support:
  - per provider
  - per tier
  - per time window (hour/day)
- When a budget is exceeded, behavior must be deterministic (documented):
  - degrade premium to balanced for non-high-risk requests
  - preserve premium for high-risk (tools/JSON) unless explicitly disallowed

## 12) Testing plan
- Offline eval: confusion matrix from labeled dataset.
- Online shadow mode: compute route but do not change upstream; log decision.
- Shadow scoring: compare predicted route vs forced baseline, track error/latency deltas.
- Canary: route a subset of sessions/users (sticky hashing, no flip-flop).
- Regression suite: fixed prompts -> expected tier and provider.
- Fault injection: upstream timeouts, 429, 5xx, partial streaming disconnects.
- Budget tests: simulated premium budget exhaustion triggers deterministic degradation.
- Stickiness tests: same conversation key selects same provider/model across restarts.

## 13) Open questions
- Exact tier mappings for Gemini and OpenAI in this environment.
- Embedding model choice and drift strategy.
- Whether to support responses endpoint and function calling variants beyond chat/completions.

## 14) Versioning policy (required)
SignalGate must provide a deterministic, auditable version string.

- `_signalgate.router_version` should be a composed string including:
  - SignalGate code version (git tag or build id)
  - manifest version (from capability manifest)
  - runtime config version
  - classifier artifacts version (dataset + index + embedding model)

Any change to routing behavior must bump at least one component and must be visible in logs and response metadata.

## 15) Stage 1 fixed-upstream behavior (OpenAI)
Until multi-provider routing is enabled, Stage 1 can forward all requests to a single OpenAI upstream.

Requirements
- Upstream base URL: `https://api.openai.com/v1` (configurable)
- API key must be supplied via environment variable (configured as `upstreams.openai.api_key_env`)
- SignalGate must not persist the API key and must not log it.
- If upstream errors/timeouts occur, return standardized `_signalgate.error.*` and a retryable flag.

