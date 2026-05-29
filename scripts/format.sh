#!/bin/bash
# 코드 포매터 일괄 실행 스크립트
# 사용법: bash scripts/format.sh [--check]
#   --check  실제 수정 없이 검사만 수행 (CI 모드)

set -e

# ── 프로젝트 루트로 이동 ─────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR/.."

# ── --check 플래그 파싱 ───────────────────────────────────
CHECK_MODE=false
if [[ "${1:-}" == "--check" ]]; then
  CHECK_MODE=true
fi

# ── 색상 정의 ─────────────────────────────────────────────
GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
RESET="\033[0m"

pass() { echo -e "${GREEN}[PASS]${RESET} $1"; }
info() { echo -e "${YELLOW}[RUN ]${RESET} $1"; }
fail() { echo -e "${RED}[FAIL]${RESET} $1"; }

echo ""
if $CHECK_MODE; then
  echo "===== 포매터 검사 모드 (--check) ====="
else
  echo "===== 코드 포매터 실행 ====="
fi
echo ""

FAILED=0

# ── 1. isort ─────────────────────────────────────────────
info "isort — import 정렬"
if $CHECK_MODE; then
  uv run isort --check-only . && pass "isort" || { fail "isort"; FAILED=1; }
else
  uv run isort . && pass "isort"
fi

# ── 2. black ─────────────────────────────────────────────
info "black — 코드 포맷"
if $CHECK_MODE; then
  uv run black --check . && pass "black" || { fail "black"; FAILED=1; }
else
  uv run black . && pass "black"
fi

# ── 3. ruff ──────────────────────────────────────────────
info "ruff — lint + auto-fix"
if $CHECK_MODE; then
  uv run ruff check . && pass "ruff" || { fail "ruff"; FAILED=1; }
else
  uv run ruff check --fix . && pass "ruff"
fi

# ── 결과 ─────────────────────────────────────────────────
echo ""
if [[ $FAILED -eq 0 ]]; then
  echo -e "${GREEN}===== 모든 포매터 완료 =====${RESET}"
else
  echo -e "${RED}===== 일부 검사 실패 — 위 오류를 확인하세요 =====${RESET}"
  exit 1
fi
