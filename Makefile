.DEFAULT_GOAL := help

.PHONY: help setup-check lint test playwright release-gate helm-validate db-reset

help: ## Show the local developer commands.
	@./scripts/dev/dev help

setup-check: ## Check local tools and installed dependencies.
	@./scripts/dev/dev setup-check

lint: ## Run Ruff lint and formatting checks, plus ShellCheck when installed.
	@./scripts/dev/dev lint

test: ## Run all Python tests (PostgreSQL integration tests are opt-in).
	@./scripts/dev/dev test

playwright: ## Run Playwright against a disposable local database and server.
	@./scripts/dev/dev playwright

release-gate: ## Run the existing read-only release-evidence gate.
	@./scripts/dev/dev release-gate

helm-validate: ## Lint and render every local Helm chart without deploying.
	@./scripts/dev/dev helm-validate

db-reset: ## Reset the loopback traditional_strength_test PostgreSQL database.
	@./scripts/dev/dev db-reset
