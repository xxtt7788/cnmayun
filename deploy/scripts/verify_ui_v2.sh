#!/usr/bin/env bash
# UI v2 公网验证脚本 — 分批次、带超时
set -euo pipefail

BASE_URL="http://127.0.0.1:8000"
TIMEOUT="--max-time 8"

check_element() {
    local url="$1"
    local name="$2"
    local pattern="$3"
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" $TIMEOUT "$url" 2>/dev/null || echo "000")
    if [ "$code" != "200" ]; then
        echo "  [FAIL] $name -> HTTP $code"
        return 1
    fi
    local count
    count=$(curl -s $TIMEOUT "$url" 2>/dev/null | grep -c "$pattern" || echo 0)
    if [ "$count" -gt 0 ]; then
        echo "  [OK]   $name -> HTTP $code, '$pattern' found ($count)"
    else
        echo "  [FAIL] $name -> HTTP $code, '$pattern' NOT found"
        return 1
    fi
}

echo "=== Batch 1: Public pages + CSS ==="
check_element "$BASE_URL/static/styles.css" "CSS" "site-header"
check_element "$BASE_URL/"                  "Home" "hero-eyebrow"
check_element "$BASE_URL/feed"              "Feed" "event-card"
check_element "$BASE_URL/companies"         "Companies" "company-link"
check_element "$BASE_URL/people"            "People" "person-card"
check_element "$BASE_URL/watchlists"        "Watchlists" "btn-primary"
check_element "$BASE_URL/login"             "Login" "auth-panel"

echo ""
echo "=== Batch 2: Admin pages (should redirect to login) ==="
for path in /daily-events /review /coverage /memory; do
    code=$(curl -s -o /dev/null -w "%{http_code}" $TIMEOUT "$BASE_URL$path" 2>/dev/null || echo "000")
    if [ "$code" = "303" ]; then
        echo "  [OK]   $path -> HTTP 303 (protected)"
    else
        echo "  [FAIL] $path -> HTTP $code (expected 303)"
    fi
done

echo ""
echo "=== Health ==="
curl -fsS $TIMEOUT "$BASE_URL/healthz" && echo "  [OK]   healthz" || echo "  [FAIL] healthz"

echo ""
echo "=== Done ==="
