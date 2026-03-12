#!/usr/bin/env bash
# migrate-verify.sh — Validate the Container Apps migration
#
# Usage:
#   ./scripts/migrate-verify.sh              # Check localhost:8000
#   ./scripts/migrate-verify.sh https://api.example.com   # Check remote
#
set -euo pipefail

BASE_URL="${1:-http://localhost:8000}"
PASS=0
FAIL=0

green()  { printf '\033[0;32m%s\033[0m\n' "$*"; }
red()    { printf '\033[0;31m%s\033[0m\n' "$*"; }
yellow() { printf '\033[0;33m%s\033[0m\n' "$*"; }

check() {
    local label="$1" url="$2" expected_status="${3:-200}"
    local status
    status=$(curl -s -o /dev/null -w '%{http_code}' "$url" 2>/dev/null || echo "000")
    if [ "$status" = "$expected_status" ]; then
        green "  ✅ $label — HTTP $status"
        PASS=$((PASS + 1))
    else
        red "  ❌ $label — expected $expected_status, got $status"
        FAIL=$((FAIL + 1))
    fi
}

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Migration Verification — ${BASE_URL}"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

yellow "1. Health & readiness probes"
check "GET /health" "${BASE_URL}/health"
check "GET /ready"  "${BASE_URL}/ready"

yellow "2. API endpoints (expect 4xx for unauthenticated requests)"
check "GET  /api/documents/status"       "${BASE_URL}/api/documents/status" 200
check "POST /api/upload/sas-token (no body)" "${BASE_URL}/api/upload/sas-token" 422

yellow "3. Python import check"
if python -c "from app.main import app; print('OK')" 2>/dev/null; then
    green "  ✅ app.main imports cleanly"
    PASS=$((PASS + 1))
else
    red "  ❌ app.main import failed"
    FAIL=$((FAIL + 1))
fi

if python -c "from app.worker import ConversionWorker; print('OK')" 2>/dev/null; then
    green "  ✅ app.worker imports cleanly"
    PASS=$((PASS + 1))
else
    red "  ❌ app.worker import failed"
    FAIL=$((FAIL + 1))
fi

yellow "4. Running pytest (backend tests)"
if pytest tests/ -q --tb=short 2>/dev/null; then
    green "  ✅ All tests pass"
    PASS=$((PASS + 1))
else
    red "  ❌ Some tests failed"
    FAIL=$((FAIL + 1))
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Results: ${PASS} passed, ${FAIL} failed"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

if [ "$FAIL" -gt 0 ]; then
    red "Migration verification FAILED"
    exit 1
else
    green "Migration verification PASSED ✅"
    exit 0
fi
