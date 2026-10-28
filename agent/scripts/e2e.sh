#!/usr/bin/env bash
# Start a fresh local agent server, run one check script against it, stop the server.
#   scripts/e2e.sh check_all.py
#   scripts/e2e.sh check_guide.py 3
set -euo pipefail
cd "$(dirname "$0")/.."
LOG="${MDA_LOG:-/tmp/pr-wrangler-dev.log}"

lsof -ti tcp:2024 | xargs kill 2>/dev/null || true
uv run mda dev --no-browser --no-reload --port 2024 >"$LOG" 2>&1 &
SERVER=$!
trap 'kill $SERVER 2>/dev/null; lsof -ti tcp:2024 | xargs kill 2>/dev/null || true' EXIT

for _ in $(seq 1 60); do
  curl -s http://127.0.0.1:2024/ok | grep -q true && break
  sleep 2
done
curl -s http://127.0.0.1:2024/ok | grep -q true || { echo "server did not start; see $LOG"; tail -20 "$LOG"; exit 1; }

cd scripts && uv run python "$@"
