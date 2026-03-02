PRE-RELEASE

SignalGate: Semantic Routing for OpenClaw, Built for Reliability First

Today we are announcing SignalGate, a semantic routing layer for OpenClaw that decides - at call time - which model tier should handle each request. SignalGate sits behind a local OpenAI-compatible endpoint on 127.0.0.1, so existing OpenClaw pipelines stay intact while routing decisions become automatic, measurable, and reversible.

Why we built it
OpenClaw workloads are not uniform. Some prompts are trivial and should never hit premium inference. Others require tool-calling, structured output, or higher correctness under risk. SignalGate’s job is to stop treating every request like an emergency - and stop paying for it like one.

How it works (no magic, no rewriting)
SignalGate does not rewrite prompts and does not run a rules forest. It performs semantic tiering using local embeddings and a lightweight KNN classifier trained on labeled historical workloads. The classifier selects one of three tiers (budget, balanced, premium). Then SignalGate enforces hard capability gates (tools, JSON/schema requirements, streaming, context window) and routes to the best eligible upstream model based on provider preference and scoring.

Reliability features that matter in production
SignalGate ships with the guardrails you want before you ever make it “primary”:
Backpressure: bounded queue and bounded in-flight concurrency
Circuit breakers: per-model breakers with cooldown and half-open trials
Deterministic failover: predictable retry ladder, with side-effect-safe behavior (no retries after tools may execute)
Canary and shadow mode: deploy without flipping the whole fleet at once
Incident mode: pin to a safe tier or disable classification instantly

Local-first by default
SignalGate uses local embeddings (GGUF) so semantic routing can stay on-box. No hidden embedding calls. No additional external dependencies unless you choose them.

Transparent decisions
Every response carries a _signalgate metadata block including routed provider/model, tier selection details, and decision trace when debug mode is enabled. It is designed so operators can answer: “What happened?” without guessing.

Current status
SignalGate is in public preview. Next: a controlled canary period with real workload tuning, followed by making SignalGate the default primary routing path for OpenClaw in production environments.

END
