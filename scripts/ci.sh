#!/usr/bin/env bash

# Full continuous-integration gate: static analysis (delegated to lint.sh),
# then compile + tests, then the skills security scan. Every check is
# read-only. `all` (default) runs the complete gate and aggregates the result.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# shellcheck disable=SC1091 source=scripts/log.sh
source "$SCRIPT_DIR/log.sh"

run_lint() {
    bash "$SCRIPT_DIR/lint.sh" all
}

run_test() {
    local failed=0

    log_step "py-compile"
    if ! uv run python -m compileall -q evals/src tests scripts; then
        log_error "Compile check failed"
        failed=1
    fi
    log_step_end

    log_step "pytest"
    if ! uv run python -m pytest; then
        log_error "Tests failed"
        failed=1
    fi
    log_step_end

    return "$failed"
}

run_all() {
    local failed=0
    run_lint || failed=1
    run_test || failed=1

    if ((failed)); then
        log_error "CI gate failed"
        return 1
    fi
    log_success "CI gate passed"
}

case "${1:-all}" in
    lint) run_lint ;;
    test) run_test ;;
    all) run_all ;;
    *)
        log_error "Unknown subcommand: $1 (lint|test|all)"
        exit 2
        ;;
esac
