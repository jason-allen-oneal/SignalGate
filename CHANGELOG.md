# Changelog

All notable changes to this project will be documented in this file.

## 1.0.3

- Stage 4: Health-aware candidate ordering (avoid selecting breaker-open candidates when healthy alternatives exist).
- Stage 6: Gemini streaming support (streamGenerateContent translated to OpenAI SSE frames).
- Stage 8: Two-phase tools routing behind a feature flag (balanced plan attempt then premium execute when needed).
- Stage 8: Optional JSONL metrics sink for routing outcome scoring (no prompt logging).
- Misc: App version now derives from package version.
