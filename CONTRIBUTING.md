# Contributing

## Development setup

```bash
uv sync --extra dev --extra embed
```

## Tests

```bash
uv run pytest
```

Run without live upstream calls:

```bash
uv run pytest -m "not e2e"
```

## Style

- Keep changes small and reviewable.
- Prefer deterministic behavior over heuristics.
- Do not log prompts or sensitive payloads.
