# Release process

SignalGate releases are tag driven.

## Version rules

- `pyproject.toml` is the source of truth for the package version.
- Release tags must use `v<version>`, for example `v1.0.3`.
- The release workflow fails if the tag version does not match `project.version`.

## Release checklist

1. Update `pyproject.toml`.
2. Update `README.md` status/version text if needed.
3. Run `uv sync --extra dev`.
4. Run `uv run ruff check .`.
5. Run `uv run pytest -m "not e2e" -ra`.
6. Run live upstream tests separately when credentials are available.
7. Tag the release with `git tag v<version>` and push the tag.

The release workflow builds the distribution and writes SHA-256 checksums for the generated artifacts.
