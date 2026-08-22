#!/usr/bin/env bash

# Prepare a checkout for work: sync dependencies, install hooks, verify them.
# Hook scripts under scripts/ stay Python 3.12-compatible; the package itself
# targets 3.14.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"



sync_dependency_groups() {
    log_step "syncing dependency groups"
    uv sync --all-groups
    log_step_end
}

install_precommit_hooks() {
    log_step "installing pre-commit and commit-msg hooks"
    uv run pre-commit install --hook-type pre-commit --hook-type commit-msg
    log_step_end
}

ensure_hooks_installed() {
    for hook in pre-commit commit-msg; do
        if [[ ! -f ".git/hooks/${hook}" ]]; then
            log_error ".git/hooks/${hook} was not installed"
            exit 1
        fi
    done
}

main() {
    cd "$REPO_ROOT"

    # shellcheck disable=SC1091 source=scripts/log.sh
    source "$SCRIPT_DIR/log.sh"
    sync_dependency_groups
    install_precommit_hooks
    ensure_hooks_installed
    log_success "Checkout ready"
}


main "$@"