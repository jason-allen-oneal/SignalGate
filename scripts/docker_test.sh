#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

docker compose -f docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from test-runner
