#!/usr/bin/env bash
set -euo pipefail

SCRIPTS_DIRECTORY="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPOSITORY_ROOT="$(cd "${SCRIPTS_DIRECTORY}/.." && pwd)"

main() {
  cd "${REPOSITORY_ROOT}"

  # shellcheck disable=SC1091 source=scripts/log.sh
  source "${SCRIPTS_DIRECTORY}/log.sh"
  log::step "installing pre-commit hook"
  uv run pre-commit install --install-hooks
  log::step_end

  log::step "syncing dependency groups"
  uv sync --all-packages --all-groups
  log::step_end

  log::success "development environment setup"
}

main "$@"
