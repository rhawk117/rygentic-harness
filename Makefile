SHELL := /usr/bin/env bash
UV ?= uv
.DEFAULT_GOAL := help

.PHONY: help setup sync format lint quality pre-commit test build check
help: ## Show available targets
	@awk 'BEGIN {FS = ":.*## "; printf "Usage: make <target>\n\nTargets:\n"} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-12s %s\n", $$1, $$2}' $(MAKEFILE_LIST)
setup: ## Prepare the checkout and install the pre-commit hook
	./scripts/setup.sh
sync: ## Synchronize locked root dependencies
	$(UV) sync --locked --all-packages --group check
	$(UV) lock --check
format: ## Apply repository formatters
	./scripts/quality.sh --format
lint: ## Run repository linting and plugin checks
	./scripts/quality.sh --lint
test: ## Run the test suite and coverage reports
	./scripts/quality.sh --test
quality: ## Run formatting, linting and tests
	./scripts/quality.sh
pre-commit: ## Run all pre-commit hooks
	$(UV) run pre-commit run --all-files
check: sync pre-commit quality ## Run the complete local verification gate
