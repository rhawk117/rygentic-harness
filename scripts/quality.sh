#!/usr/bin/env bash

set -uo pipefail
shopt -s globstar

readonly RUFF_CONFIG=(--config .ruff.toml --force-exclude)
readonly MARKDOWN_GLOBS=(docs/**/*.md *.md)

repository_root=$(git rev-parse --show-toplevel) || exit 1
cd "${repository_root}" || exit 1
# shellcheck source=scripts/log.sh
source scripts/log.sh

FAILURES=()

run() {
  local label=$1
  shift

  log::info "${label}"
  "$@" || {
    FAILURES+=("${label}")
    return 1
  }
}

usage() {
  printf 'usage: %s [--format | --lint]\n' "${0##*/}" >&2
}

run_formatter() {
  run 'Ruff Format' uv run ruff format "${RUFF_CONFIG[@]}" .
  run 'Ruff Fix' uv run ruff check "${RUFF_CONFIG[@]}" --fix-only --unsafe-fixes .
  run 'Markdown Format' uv run mdformat "${MARKDOWN_GLOBS[@]}"
}

run_linter() {
  local plugin

  run 'Ruff Format Check' uv run ruff format "${RUFF_CONFIG[@]}" --check .
  run 'Ruff Check' uv run ruff check "${RUFF_CONFIG[@]}" --no-fix .
  run 'Markdown Check' uv run mdformat --check "${MARKDOWN_GLOBS[@]}"
  run 'Python Line Cap' scripts/check-python-line-cap.sh

  run 'ty (3.14)' uv run ty check --config-file .ty.toml
  run 'ty (3.12 skills)' uv run ty check --config-file .ty.toml \
    --python-version 3.12 plugins/mightymodels/skills plugins/vibe-code/skills \
    plugins/vibe-code/src plugins/vibe-code/tests
  run 'pytest' uv run pytest

  for plugin in plugins/*/; do
    run "[${plugin#plugins/}] coverage" \
      uv run coverage report --rcfile=.coveragerc.ini --include="${plugin}*"
  done

  if ! command -v claude >/dev/null; then
    log::error 'claude not on PATH: npm install -g @anthropic-ai/claude-code'
    FAILURES+=('Claude CLI')
    return
  fi

  for plugin in plugins/*/; do
    run "[${plugin#plugins/}] plugin validate" claude plugin validate --strict "${plugin}"
  done
  run '[root] plugin validate' claude plugin validate --strict .
}

case "${1:-}" in
  --format) run_formatter ;;
  --lint) run_linter ;;
  '')
    run_formatter
    run_linter
    ;;
  *)
    usage
    exit 2
    ;;
esac

if ((${#FAILURES[@]} > 0)); then
  log::error 'quality checks failed:'
  printf '  - %s\n' "${FAILURES[@]}" >&2
  exit 1
fi

log::success 'quality checks passed'
