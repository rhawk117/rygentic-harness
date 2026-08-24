#!/usr/bin/env bash

# Static analysis gate, read-only. Subcommands: format | ruff | typecheck |
# shell | markdown | security | all (default). Mirrors scripts/ci.sh's lint
# phase; `make format` fixes what `format` flags.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

# shellcheck disable=SC1091 source=scripts/log.sh
source "$SCRIPT_DIR/log.sh"

run_format() {
	local failed=0

	log_step "ruff format --check"
	if ! uv run ruff format . --check; then
		log_error "Format check failed; run 'make format'"
		failed=1
	fi
	log_step_end

	return "$failed"
}

run_ruff() {
	local failed=0

	log_step "ruff check (no fixes)"
	if ! uv run ruff check . --no-fix; then
		log_error "Lint check failed"
		failed=1
	fi
	log_step_end

	return "$failed"
}

run_typecheck() {
	local failed=0

	log_step "ty check"
	if ! uv run ty check; then
		log_error "Type check failed"
		failed=1
	fi
	log_step_end

	return "$failed"
}

run_shell() {
	local failed=0

	if ! command -v shellcheck >/dev/null 2>&1; then
		log_warn "shellcheck not installed; skipping shell lint"
		return 0
	fi

	log_step "shellcheck"
	if ! shellcheck -x scripts/*.sh; then
		log_error "Shell lint failed"
		failed=1
	fi
	log_step_end

	if command -v shfmt >/dev/null 2>&1; then
		log_step "shfmt --diff"
		if ! shfmt -d scripts/*.sh; then
			log_error "Shell format check failed; run 'make format'"
			failed=1
		fi
		log_step_end
	fi

	return "$failed"
}

run_markdown() {
	local failed=0

	require_cmd npx

	log_step "markdownlint"
	if ! npx --yes markdownlint-cli2; then
		log_error "Markdown lint failed"
		failed=1
	fi
	log_step_end

	return "$failed"
}

run_security() {
	local failed=0

	log_step "prompt-injection scan (skills + agents)"
	if ! bash "$SCRIPT_DIR/security.sh"; then
		log_error "Security scan failed"
		failed=1
	fi
	log_step_end

	return "$failed"
}

run_all() {
	local failed=0
	run_format || failed=1
	run_ruff || failed=1
	run_typecheck || failed=1
	run_shell || failed=1
	run_markdown || failed=1
	run_security || failed=1

	if ((failed)); then
		log_error "Lint gate failed"
		return 1
	fi
	log_success "Lint gate passed"
}

case "${1:-all}" in
format) run_format ;;
ruff) run_ruff ;;
typecheck) run_typecheck ;;
shell) run_shell ;;
markdown) run_markdown ;;
security) run_security ;;
all) run_all ;;
*)
	log_error "Unknown subcommand: $1 (format|ruff|typecheck|shell|markdown|security|all)"
	exit 2
	;;
esac
