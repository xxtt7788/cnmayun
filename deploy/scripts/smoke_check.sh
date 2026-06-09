#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"

echo "checking $BASE_URL/healthz"
curl -H "Accept-Encoding: identity" -fsS "$BASE_URL/healthz"
echo

echo "checking $BASE_URL/readyz"
if curl -H "Accept-Encoding: identity" -fsS "$BASE_URL/readyz"; then
  echo
  echo "readyz passed"
else
  echo
  echo "readyz did not pass; inspect preflight output before public launch"
fi
