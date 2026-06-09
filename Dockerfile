FROM python:3.11-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SIGNALGATE_CONFIG_PATH=/app/config/config.json

RUN addgroup --system signalgate \
    && adduser --system --ingroup signalgate --home /app signalgate

WORKDIR /app

COPY pyproject.toml README.md LICENSE ./
COPY signalgate ./signalgate
COPY docs ./docs

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir . \
    && mkdir -p /app/config /app/data \
    && chown -R signalgate:signalgate /app

USER signalgate

EXPOSE 8765
VOLUME ["/app/config", "/app/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/healthz', timeout=2).read()"

CMD ["signalgate"]
