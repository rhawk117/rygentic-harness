#!/usr/bin/env bash

# Applies formatting and safe autofixes in place. This is the only quality
# script that modifies repository files; intended for local use before `lint`.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# shellcheck disable=SC1091 source=scripts/log.sh
source "$SCRIPT_DIR/log.sh"

main() {
    log_step "ruff format"
    uv run ruff format .
    log_step_end

    log_step "ruff check --fix"
    uv run ruff check . --fix
    log_step_end

    if command -v shfmt >/dev/null 2>&1; then
        log_step "shfmt"
        shfmt -w scripts/*.sh
        log_step_end
    else
        log_warn "shfmt not installed; shell scripts left as-is"
    fi

    log_success "Formatting complete"
}

main "$@"
