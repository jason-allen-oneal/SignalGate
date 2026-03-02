# SignalGate Testing

SignalGate uses a tiered test strategy.

## Default (local dev)
Runs unit + integration + regression tests. Live upstream tests are excluded.

```bash
uv sync --extra dev
uv run pytest
```

## E2E (live upstream)
Requires API keys and an explicit marker.

OpenAI:
```bash
export OPENAI_API_KEY=...
uv sync --extra dev
uv run pytest -m e2e
```

Gemini:
```bash
export GEMINI_API_KEY=...
uv sync --extra dev
uv run pytest -m e2e
```

## With local embeddings
`llama-cpp-python` is a compiled dependency, isolated behind an extra.

```bash
uv sync --extra dev --extra embed
```

Unit/regression tests do not require the GGUF embedding model or llama-cpp.
They use `test-hash:<dim>` embedder.

## Test layout
- `tests/unit/` - pure logic tests (breaker, classifier math, routing scoring)
- `tests/integration/` - in-process ASGI tests with stub upstreams
- `tests/regression/` - golden routing behavior using fixed fixtures
- `tests/e2e/` - live upstream calls (skipped unless `-m e2e` and keys present)
