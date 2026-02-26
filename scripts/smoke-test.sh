#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:5000}"
TEST_URL="${2:-https://www.youtube.com/watch?v=dQw4w9WgXcQ}"

curl -fsS "$BASE_URL/health" | jq .

curl -fsS -X POST "$BASE_URL/api/extract" \
  -H "Content-Type: application/json" \
  -d "{\"url\":\"$TEST_URL\"}" | jq .

echo "Smoke test passed"
