.PHONY: format lint security ci

format:
	@bash scripts/format.sh

lint:
	@bash scripts/lint.sh

security:
	@bash scripts/security.sh

ci:
	@bash scripts/ci.sh

.DEFAULT_GOAL := ci
