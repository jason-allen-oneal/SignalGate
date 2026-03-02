from __future__ import annotations

import asyncio
import os
import time
import uuid
from collections import OrderedDict
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .budgets import BudgetManager
from .canary import CanaryConfig, is_canary_user
from .classifier import KNNTierClassifier
from .embeddings import Embedder, build_embedder
from .errors import SGError, sg_payload_too_large, sg_queue_full, sg_unauthorized
from .health import HealthManager
from .limits import LimitManager
from .metrics import MetricsConfig, append_jsonl
from .routing import (
    Candidate,
    RequiredCaps,
    Tier,
    rank_candidates,
    required_caps_from_request,
    select_candidate,
)
from .runtime import LoadedArtifacts, load_and_validate
from .sanitize import RequestFieldConfig, sanitize_chat_completions_payload
from .security import maybe_forward_user
from .upstreams.manager import Upstreams, build_upstreams
from .util import stable_hash
from .version import __version__


class RuntimeState:
    def __init__(self, artifacts: LoadedArtifacts):
        self.artifacts = artifacts

        limits_raw = artifacts.config_raw.get("limits", {}) or {}
        self.max_queue_depth = int(limits_raw.get("max_queue_depth", 200))
        self.queue_sem = asyncio.Semaphore(self.max_queue_depth)

        # In-flight concurrency controls (Stage 5)
        self.max_in_flight_global = int(limits_raw.get("max_in_flight_global", 16))
        self.max_in_flight_per_provider = int(limits_raw.get("max_in_flight_per_provider", 8))
        self.max_in_flight_per_model = int(limits_raw.get("max_in_flight_per_model", 4))
        self.limits = LimitManager.from_config_raw(artifacts.config_raw)

        # Health / circuit breakers (Stage 5)
        breakers_raw = artifacts.config_raw.get("breakers", {}) or {}
        self.breakers_enabled = bool(breakers_raw.get("enabled", True))
        self.health = HealthManager.from_config_raw(artifacts.config_raw)

        # Canary (Stage 7)
        can_raw = artifacts.config_raw.get("canary", {}) or {}
        self.canary_cfg = CanaryConfig(
            enabled=bool(artifacts.config.features.enable_canary),
            mode=str(can_raw.get("mode", "percent")),
            percent=float(can_raw.get("percent", 0)),
            allowlist=list(can_raw.get("allowlist", [])),
            hash_salt=str(can_raw.get("hash_salt", "signalgate")),
        )

        # Budgets (Stage 8)
        bud_raw = artifacts.config_raw.get("budgets", {}) or {}
        self.budgets = BudgetManager(
            enabled=bool(bud_raw.get("enabled", False)),
            window=str(bud_raw.get("window", "day")),
            limits=dict((bud_raw.get("usd") or {}).get("per_tier", {})),
        )
        # Merge provider limits
        self.budgets.limits.update(
            {
                f"provider:{k}": v
                for k, v in (bud_raw.get("usd") or {}).get("per_provider", {}).items()
            }
        )
        self.preserve_premium_for_high_risk = bool(
            (bud_raw.get("degradation") or {}).get("preserve_premium_for_high_risk", True)
        )

        # Shadow metrics (Stage 8): optional JSONL sink for routing outcomes.
        metrics_raw = artifacts.config_raw.get("metrics", {}) or {}
        self.metrics = MetricsConfig(
            enabled=bool(metrics_raw.get("enabled", False)),
            jsonl_path=str(metrics_raw.get("jsonl_path", "")),
        )

        self.upstreams: Upstreams = build_upstreams(artifacts.config, artifacts.config_raw)

        # Stage 3: local embedding + KNN tier classifier (optional, config-gated)
        cls_raw = artifacts.config_raw.get("classifier", {})
        self.classifier_enabled = bool(cls_raw.get("enabled", False))
        self.sim_threshold = float(cls_raw.get("sim_threshold", 0.75))
        self.margin_threshold = float(cls_raw.get("margin_threshold", 0.05))
        self.min_tier_for_high_risk: Tier = str(cls_raw.get("min_tier_for_high_risk", "balanced"))  # type: ignore

        # Incident Mode Toggles (Stage 10)
        self.incident_pin_tier: Tier | None = cls_raw.get("incident_pin_tier")
        self.incident_disable_classifier: bool = bool(
            cls_raw.get("incident_disable_classifier", False)
        )

        self._embedder: Embedder | None = None
        self._knn: KNNTierClassifier | None = None
        self._embed_cache: OrderedDict[str, Any] = OrderedDict()
        self._embed_cache_max = 1024

        if self.classifier_enabled:
            dataset_path = artifacts.config.paths.knn_dataset_path
            model_path = artifacts.config.paths.embedding_model_path
            if not dataset_path:
                raise SGError(
                    code="SG_INTERNAL",
                    message="classifier.enabled but paths.knn_dataset_path missing",
                    status_code=500,
                )
            if not model_path:
                raise SGError(
                    code="SG_INTERNAL",
                    message="classifier.enabled but paths.embedding_model_path missing",
                    status_code=500,
                )

            self._embedder = build_embedder(model_path)
            self._knn = KNNTierClassifier.from_jsonl(dataset_path)

    async def classify_tier(
        self, req_payload: dict[str, Any], caps: RequiredCaps
    ) -> tuple[Tier, dict[str, Any]]:
        if not self.classifier_enabled or not self._embedder or not self._knn:
            return "balanced", {"top1": None, "top2": None, "margin": None}

        # High-risk floor
        tier_floor: Tier | None = None
        if caps.tools or caps.json_schema:
            tier_floor = self.min_tier_for_high_risk

        # Canonical representation: last user message + request-shape markers
        # (No prompt rewriting. This representation is for embeddings only.)
        msgs = req_payload.get("messages") or []
        last_user = ""
        for m in reversed(msgs):
            if isinstance(m, dict) and m.get("role") == "user":
                c = m.get("content")
                if isinstance(c, str):
                    last_user = c
                break

        rep = {
            "text": last_user,
            "tools_present": bool(caps.tools),
            "json_required": bool(caps.json_schema),
        }
        rep_text = (
            f"{rep['text']}\n\n"
            f"[tools_present={rep['tools_present']};json_required={rep['json_required']}]"
        )

        cache_key = stable_hash({"rep": rep_text})
        if cache_key in self._embed_cache:
            q = self._embed_cache.pop(cache_key)
            # move to end
            self._embed_cache[cache_key] = q
        else:
            q = await self._embedder.embed(rep_text)
            self._embed_cache[cache_key] = q
            if len(self._embed_cache) > self._embed_cache_max:
                self._embed_cache.popitem(last=False)
        res = self._knn.predict(
            q, sim_threshold=self.sim_threshold, margin_threshold=self.margin_threshold
        )

        tier: Tier = res.tier

        # Uncertainty promotion
        if res.top1 < self.sim_threshold or res.margin < self.margin_threshold:
            tier = "balanced"

        # Apply high-risk tier floor
        if tier_floor == "premium":
            tier = "premium"
        elif tier_floor == "balanced" and tier == "budget":
            tier = "balanced"

        sim = {"top1": res.top1, "top2": res.top2, "margin": res.margin}
        return tier, sim

    async def aclose(self) -> None:
        await self.upstreams.aclose()


def create_app() -> FastAPI:
    from contextlib import asynccontextmanager

    state: dict[str, Any] = {}

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        artifacts = load_and_validate()
        state["rt"] = RuntimeState(artifacts)
        try:
            yield
        finally:
            rt: RuntimeState | None = state.get("rt")
            if rt:
                await rt.aclose()

    app = FastAPI(title="SignalGate", version=__version__, lifespan=lifespan)

    @app.middleware("http")
    async def _auth_and_limits(request: Request, call_next):
        try:
            rt: RuntimeState | None = state.get("rt")
            if rt:
                sec = rt.artifacts.security

                # Body size limit: use content-length when present.
                clen = request.headers.get("content-length")
                if clen:
                    try:
                        if int(clen) > sec.max_body_bytes:
                            raise sg_payload_too_large()
                    except ValueError:
                        pass

                # Auth check
                if sec.auth_enabled:
                    path = request.url.path
                    if sec.auth_allow_health and path in ("/healthz", "/readyz"):
                        return await call_next(request)

                    token = request.headers.get(sec.auth_header)
                    expected = os.environ.get(sec.auth_token_env)
                    if not expected:
                        raise SGError(
                            code="SG_INTERNAL",
                            message=f"Missing env var {sec.auth_token_env} for auth",
                            status_code=500,
                        )

                    # Accept raw token or "Bearer <token>" for compatibility
                    # with OpenAI-style clients.
                    if token and token.startswith("Bearer "):
                        token = token[len("Bearer ") :]

                    if not token or token != expected:
                        raise sg_unauthorized()

            return await call_next(request)
        except SGError as exc:
            return await _sg_error_handler(request, exc)

    def _meta(rt: RuntimeState, request_id: str, *, tier: str | None = None) -> dict[str, Any]:
        return {
            "request_id": request_id,
            "router_version": rt.artifacts.router_version,
            "tier": tier,
        }

    @app.exception_handler(SGError)
    async def _sg_error_handler(_req: Request, exc: SGError):
        rt: RuntimeState | None = state.get("rt")
        request_id = str(uuid.uuid4())
        meta = {
            "request_id": request_id,
            "router_version": rt.artifacts.router_version if rt else "",
        }

        upstream = exc.upstream
        # Never return upstream bodies unless response debug is enabled.
        if upstream and rt and not rt.artifacts.config.features.enable_response_debug:
            upstream = dict(upstream)
            upstream.pop("body", None)

        body = {
            "error": {
                "message": exc.message,
                "type": "signalgate_error",
                "code": exc.code,
            },
            "_signalgate": {
                **meta,
                "error": {
                    "code": exc.code,
                    "message": exc.message,
                    "retryable": bool(exc.retryable),
                    "upstream": upstream,
                },
            },
        }
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.get("/healthz")
    async def healthz():
        return {"ok": True}

    @app.get("/readyz")
    async def readyz():
        rt: RuntimeState = state["rt"]
        return {
            "ok": True,
            "router_version": rt.artifacts.router_version,
            "breakers": rt.health.snapshot(),
            "limits": {
                "max_queue_depth": rt.max_queue_depth,
                "max_in_flight_global": rt.max_in_flight_global,
                "max_in_flight_per_provider": rt.max_in_flight_per_provider,
                "max_in_flight_per_model": rt.max_in_flight_per_model,
            },
        }

    @app.get("/v1/models")
    async def list_models():
        models = [
            {"id": "signalgate/auto", "object": "model"},
            {"id": "signalgate/budget", "object": "model"},
            {"id": "signalgate/balanced", "object": "model"},
            {"id": "signalgate/premium", "object": "model"},
            {"id": "signalgate/chat-only", "object": "model"},
        ]
        return {"object": "list", "data": models}

    def _candidate_health_rank(rt: RuntimeState, c: Candidate) -> int:
        # 0 = healthy (closed)
        # 1 = half-open (trial available)
        # 2 = unavailable (open or trial in flight)
        if not rt.breakers_enabled:
            return 0
        br = rt.health.breaker(c.provider, c.model_id)
        if not br.is_available():
            return 2
        if br.state == "half_open":
            return 1
        return 0

    def _order_candidates_by_health(
        rt: RuntimeState, candidates: list[Candidate]
    ) -> list[Candidate]:
        if not candidates:
            return candidates
        healthy: list[Candidate] = []
        unhealthy: list[Candidate] = []
        for c in candidates:
            if _candidate_health_rank(rt, c) >= 2:
                unhealthy.append(c)
            else:
                healthy.append(c)
        # If we have any healthy candidates, keep unhealthy candidates at the tail.
        # This makes failover deterministic while avoiding repeated "breaker open" latency.
        return healthy + unhealthy if healthy else candidates

    def _response_has_tool_calls(resp: dict[str, Any]) -> bool:
        try:
            choices = resp.get("choices")
            if not isinstance(choices, list) or not choices:
                return False
            msg = choices[0].get("message")
            if isinstance(msg, dict) and msg.get("tool_calls"):
                return True
            fr = choices[0].get("finish_reason")
            return fr in ("tool_calls", "function_call")
        except Exception:
            return False

    @app.post("/v1/chat/completions")
    async def chat_completions(req: Request):
        rt: RuntimeState = state["rt"]

        # Fail-fast queue slot acquisition
        try:
            # asyncio.Semaphore has no acquire_nowait; use a tiny timeout to emulate fail-fast.
            await asyncio.wait_for(rt.queue_sem.acquire(), timeout=0.001)
        except TimeoutError as e:
            raise sg_queue_full() from e

        t0 = time.time()
        request_id = str(uuid.uuid4())
        try:
            payload = await req.json()
            # Optional request field stripping (security hardening)
            rf_mode = getattr(rt.artifacts.security, "request_fields_mode", "passthrough")
            payload = sanitize_chat_completions_payload(
                payload, cfg=RequestFieldConfig(mode=rf_mode)
            )

            if not isinstance(payload, dict):
                raise SGError(code="SG_BAD_REQUEST", message="Invalid JSON body", status_code=400)

            model = payload.get("model")
            if not isinstance(model, str):
                raise SGError(code="SG_BAD_REQUEST", message="Missing model", status_code=400)

            streaming_supported = bool(rt.artifacts.config.features.enable_streaming)
            caps0 = required_caps_from_request(payload, streaming_supported=streaming_supported)

            tier_override: Tier | None = None
            similarity = {"top1": None, "top2": None, "margin": None}
            trace = []

            # Incident Mode (Stage 10)
            if rt.incident_pin_tier:
                tier_override = rt.incident_pin_tier
                trace.append(f"incident_mode: pinned to {tier_override}")

            # Canary logic (Stage 7)
            in_canary = True
            if rt.canary_cfg.enabled and not tier_override:
                user_id = payload.get("user") if isinstance(payload.get("user"), str) else None
                in_canary = is_canary_user(user_id, rt.canary_cfg)
                trace.append(f"canary_enabled={rt.canary_cfg.enabled};in_canary={in_canary}")

            if model == "signalgate/auto" and in_canary and not tier_override:
                if rt.incident_disable_classifier:
                    tier_override = "balanced"
                    trace.append("incident_mode: classifier disabled, forced balanced")
                else:
                    tier_override, similarity = await rt.classify_tier(payload, caps0)
                    trace.append(f"classified_tier={tier_override}")
            elif not in_canary:
                trace.append("canary_bypass: forced balanced")

            routing_cfg = rt.artifacts.config_raw.get("routing", {})
            enable_stickiness = bool(routing_cfg.get("enable_stickiness", True))
            sticky_key = None
            if enable_stickiness:
                sticky_key = payload.get("user") if isinstance(payload.get("user"), str) else None

            candidate, tier, caps = select_candidate(
                virtual_model=model,
                req=payload,
                manifest=rt.artifacts.manifest_raw,
                provider_preference=list(
                    rt.artifacts.manifest_raw.get("providerPreference")
                    or ["gemini", "openai", "other"]
                ),
                streaming_supported=streaming_supported,
                tier_override=tier_override,
                sticky_key=sticky_key,
                sticky_salt=str(
                    (rt.artifacts.config_raw.get("canary", {}) or {}).get("hash_salt", "signalgate")
                ),
            )
            trace.append(f"selected_tier={tier};sticky_key={sticky_key is not None}")
            tier_selected = tier

            upstream_payload = dict(payload)
            upstream_payload["model"] = candidate.model_id

            # Do not forward raw user identifiers upstream by default.
            forwarded_user = maybe_forward_user(
                payload.get("user") if isinstance(payload.get("user"), str) else None,
                rt.artifacts.security,
            )
            if forwarded_user is None:
                upstream_payload.pop("user", None)
            else:
                upstream_payload["user"] = forwarded_user

            # Multi-provider upstream adapters are available in v1, but capability gating
            # still determines which providers can satisfy the request.

            # Budget enforcement (Stage 8)
            if tier == "premium":
                # Dummy cost check for budget gating (uses manifest pricing if available)
                # In real use, we record actual usage after the call.
                # Here we just check if we are ALREADY exceeded.
                if rt.budgets.check_and_record(tier=tier, provider="", cost=0):
                    if not (rt.preserve_premium_for_high_risk and (caps.tools or caps.json_schema)):
                        tier = "balanced"
                        trace.append("budget_exceeded: degraded to balanced")
                    else:
                        trace.append("budget_exceeded: preserved premium for high-risk")

            # Build ordered candidate list for deterministic failover (Stage 5)
            ranked, _tier, _caps = rank_candidates(
                virtual_model=model,
                req=payload,
                manifest=rt.artifacts.manifest_raw,
                provider_preference=list(
                    rt.artifacts.manifest_raw.get("providerPreference")
                    or ["gemini", "openai", "other"]
                ),
                streaming_supported=streaming_supported,
                tier_override=tier,
            )

            # Retry ladder: allow one failover. For tools/JSON, allow escalation to premium.
            candidate_list = list(ranked)
            if (caps.tools or caps.json_schema) and tier != "premium":
                ranked_p, _, _ = rank_candidates(
                    virtual_model=model,
                    req=payload,
                    manifest=rt.artifacts.manifest_raw,
                    provider_preference=list(
                        rt.artifacts.manifest_raw.get("providerPreference")
                        or ["gemini", "openai", "other"]
                    ),
                    streaming_supported=streaming_supported,
                    tier_override="premium",
                )
                for c in ranked_p:
                    if all(
                        (c.provider, c.model_id) != (x.provider, x.model_id) for x in candidate_list
                    ):
                        candidate_list.append(c)

            # Shadow mode (Stage 7)
            if rt.artifacts.config.features.enable_shadow_mode:
                shadow_raw = rt.artifacts.config_raw.get("shadow", {})
                shadow_raw.get("fixed_provider", "openai")
                fixed_model = shadow_raw.get("fixed_model")
                # Override the candidate for the actual call, but keep 'tier' etc for meta
                shadow_cand = None
                # Search manifest for the fixed model
                for m_key, m_val in rt.artifacts.manifest_raw.get("models", {}).items():
                    if m_val.get("model_id") == fixed_model:
                        shadow_cand = Candidate(
                            key=m_key,
                            provider=str(m_val.get("provider")),
                            model_id=str(m_val.get("model_id")),
                            supports=dict(m_val.get("supports") or {}),
                            limits=dict(m_val.get("limits") or {}),
                            pricing={k: float(v) for k, v in (m_val.get("pricing") or {}).items()},
                            routing={k: float(v) for k, v in (m_val.get("routing") or {}).items()},
                        )
                        break
                if shadow_cand:
                    candidate_list = [shadow_cand]

            # Stage 4: health-aware ordering (avoid repeatedly selecting an open breaker)
            ordered = _order_candidates_by_health(rt, candidate_list)
            if ordered and candidate_list and (
                (ordered[0].provider, ordered[0].model_id)
                != (candidate_list[0].provider, candidate_list[0].model_id)
            ):
                trace.append(
                    f"health_reorder: first={ordered[0].provider}:{ordered[0].model_id}"
                )
            candidate_list = ordered

            async def attempt(cand):
                br = rt.health.breaker(cand.provider, cand.model_id)
                br.allow()

                await rt.limits.global_sem.acquire()
                psem = rt.limits.provider(
                    cand.provider, max_in_flight=rt.max_in_flight_per_provider
                )
                msem = rt.limits.model(
                    cand.provider, cand.model_id, max_in_flight=rt.max_in_flight_per_model
                )
                await psem.acquire()
                await msem.acquire()
                try:
                    resp = await rt.upstreams.chat_completions(
                        provider=cand.provider, payload=upstream_payload | {"model": cand.model_id}
                    )
                    br.record_success()
                    return resp, cand
                except SGError as e:
                    is_timeout = e.code == "SG_UPSTREAM_TIMEOUT"
                    if e.code.startswith("SG_UPSTREAM") or e.code in (
                        "SG_UPSTREAM_TIMEOUT",
                        "SG_UPSTREAM_RATE_LIMIT",
                        "SG_UPSTREAM_5XX",
                    ):
                        br.record_failure(is_timeout=is_timeout)
                    raise
                finally:
                    msem.release()
                    psem.release()
                    rt.limits.global_sem.release()

            if caps.streaming:
                used0 = candidate_list[0]

                br = rt.health.breaker(used0.provider, used0.model_id)
                br.allow()

                await rt.limits.global_sem.acquire()
                psem = rt.limits.provider(
                    used0.provider, max_in_flight=rt.max_in_flight_per_provider
                )
                msem = rt.limits.model(
                    used0.provider, used0.model_id, max_in_flight=rt.max_in_flight_per_model
                )
                await psem.acquire()
                await msem.acquire()

                async def gen():
                    try:
                        async for chunk in rt.upstreams.chat_completions_stream(
                            provider=used0.provider,
                            payload=upstream_payload | {"model": used0.model_id},
                        ):
                            yield chunk
                        br.record_success()
                    except SGError as e:
                        is_timeout = e.code == "SG_UPSTREAM_TIMEOUT"
                        if e.code.startswith("SG_UPSTREAM") or e.code in (
                            "SG_UPSTREAM_TIMEOUT",
                            "SG_UPSTREAM_RATE_LIMIT",
                            "SG_UPSTREAM_5XX",
                        ):
                            br.record_failure(is_timeout=is_timeout)
                        raise
                    finally:
                        msem.release()
                        psem.release()
                        rt.limits.global_sem.release()

                from fastapi.responses import StreamingResponse

                headers = {
                    "x-signalgate-request-id": request_id,
                    "x-signalgate-router-version": rt.artifacts.router_version,
                    "x-signalgate-routed-provider": used0.provider,
                    "x-signalgate-routed-model": used0.model_id,
                }
                return StreamingResponse(gen(), media_type="text/event-stream", headers=headers)

            attempted: list[tuple[str, str]] = []

            async def run_candidate_list(cands: list[Candidate], *, max_attempts: int):
                last_err: SGError | None = None
                used: Candidate | None = None
                resp: dict[str, Any] | None = None

                for cand in cands[:max_attempts]:
                    attempted.append((cand.provider, cand.model_id))
                    try:
                        resp, used = await attempt(cand)
                        return resp, used, None
                    except SGError as e:
                        last_err = e
                        if not e.retryable:
                            break
                        continue

                return None, None, last_err

            two_phase: dict[str, Any] | None = None
            used: Candidate | None = None
            upstream_resp: dict[str, Any] | None = None

            # Stage 8: optional two-phase tools routing to reduce premium spend.
            two_phase_raw = rt.artifacts.config_raw.get("two_phase", {}) or {}
            min_margin_for_plan = float(two_phase_raw.get("min_margin_for_plan", 0.03))

            if (
                rt.artifacts.config.features.enable_two_phase_tools
                and caps.tools
                and not caps.streaming
                and model in ("signalgate/auto", "signalgate/balanced")
                and tier == "premium"
                and model != "signalgate/premium"
                and not rt.artifacts.config.features.enable_shadow_mode
            ):
                margin = similarity.get("margin")
                if margin is None or float(margin) < min_margin_for_plan:
                    trace.append("two_phase_tools: skipped (uncertain classifier)")
                else:
                    ranked_bal, _, _ = rank_candidates(
                        virtual_model=model,
                        req=payload,
                        manifest=rt.artifacts.manifest_raw,
                        provider_preference=list(
                            rt.artifacts.manifest_raw.get("providerPreference")
                            or ["gemini", "openai", "other"]
                        ),
                        streaming_supported=streaming_supported,
                        tier_override="balanced",
                    )
                    phase1_list = _order_candidates_by_health(rt, list(ranked_bal))
                    trace.append(
                        f"two_phase_tools: phase1=balanced;candidates={len(phase1_list)}"
                    )

                    resp1, used1, _err1 = await run_candidate_list(phase1_list, max_attempts=2)

                    if resp1 is not None and not _response_has_tool_calls(resp1):
                        upstream_resp = resp1
                        used = used1
                        tier = "balanced"
                        two_phase = {
                            "enabled": True,
                            "escalated": False,
                            "min_margin_for_plan": min_margin_for_plan,
                        }
                        trace.append("two_phase_tools: satisfied in phase1 (no tool_calls)")
                    else:
                        two_phase = {
                            "enabled": True,
                            "escalated": True,
                            "min_margin_for_plan": min_margin_for_plan,
                        }
                        trace.append("two_phase_tools: escalated to premium")

            if upstream_resp is None:
                max_attempts = 1 if caps.tools else 2
                resp2, used2, err2 = await run_candidate_list(
                    candidate_list, max_attempts=max_attempts
                )
                if resp2 is None:
                    assert err2 is not None
                    raise err2
                upstream_resp = resp2
                used = used2

            assert upstream_resp is not None
            assert used is not None

            meta = {
                "routed_provider": used.provider,
                "routed_model": used.model_id,
                "tier": tier,
                "tier_selected": tier_selected,
                "request_id": request_id,
                "router_version": rt.artifacts.router_version,
                "similarity": similarity,
                "two_phase": two_phase,
                "attempts": attempted,
                "decision_trace": trace
                if rt.artifacts.config.features.enable_response_debug
                else None,
                "cost": None,
                "savings_percent": None,
                "latency_ms": int((time.time() - t0) * 1000),
            }

            # Add metadata at top level to avoid breaking OpenAI parsing.
            if isinstance(upstream_resp, dict):
                upstream_resp["_signalgate"] = meta
                # Record real cost in budget (if usage available)
                usage = upstream_resp.get("usage")
                if usage and tier == "premium":
                    # rough calc
                    rt.budgets.check_and_record(tier=tier, provider=used.provider, cost=0.001)

                # Shadow metrics sink (Stage 8)
                if rt.metrics.enabled and rt.metrics.jsonl_path:
                    append_jsonl(
                        rt.metrics.jsonl_path,
                        {
                            "ts": time.time(),
                            "request_id": request_id,
                            "virtual_model": model,
                            "tier_selected": tier_selected,
                            "tier_final": tier,
                            "routed_provider": used.provider,
                            "routed_model": used.model_id,
                            "similarity": similarity,
                            "two_phase": two_phase,
                            "attempts": attempted,
                            "latency_ms": meta.get("latency_ms"),
                        },
                    )

            return upstream_resp
        finally:
            rt.queue_sem.release()

    return app


app = create_app()
