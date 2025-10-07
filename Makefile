SHELL := /bin/bash

PYTHON ?= python3
SCRIPTS ?= $(PYTHON) -m scripts
COVERAGE ?= on
REMOTE ?= origin

.PHONY: help install dev test run clean build push release version-current bump bump-patch bump-minor bump-major menu

help: ## Show help
	@awk '/^[a-zA-Z_-]+:.*##/ {split($$0,a,"## "); printf "\033[36m%-20s\033[0m %s\n", a[1], a[2]}' $(MAKEFILE_LIST)

install: ## Install package editable
	$(SCRIPTS) install

dev: ## Install package with dev extras
	$(SCRIPTS) dev

test: ## Lint, type-check, run tests with coverage, upload to Codecov
	$(SCRIPTS) test --coverage $(COVERAGE)

run: ## Run project CLI (forwards arguments)
	$(SCRIPTS) run -- --help || true

version-current: ## Print current version from pyproject.toml
	$(SCRIPTS) version-current

bump: ## Bump version: VERSION=X.Y.Z or PART=major|minor|patch (default: patch)
	@if [ -n "$(VERSION)" ]; then \
		$(SCRIPTS) bump --version $(VERSION); \
	elif [ -n "$(PART)" ]; then \
		$(SCRIPTS) bump --part $(PART); \
	else \
		$(SCRIPTS) bump; \
	fi

bump-patch: ## Bump patch version (X.Y.Z -> X.Y.(Z+1))
	$(SCRIPTS) bump-patch

bump-minor: ## Bump minor version (X.Y.Z -> X.(Y+1).0)
	$(SCRIPTS) bump-minor

bump-major: ## Bump major version ((X+1).0.0)
	$(SCRIPTS) bump-major

clean: ## Remove caches, build artifacts, and coverage
	$(SCRIPTS) clean

push: ## Commit all changes once and push to GitHub (no CI monitoring)
	$(SCRIPTS) push --remote $(REMOTE)

build: ## Build wheel/sdist and attempt optional packaging builds
	$(SCRIPTS) build

release: ## Create and push tag, optionally create GitHub release
	$(SCRIPTS) release --remote $(REMOTE)

menu: ## Interactive TUI menu
	$(PYTHON) -u scripts/menu.py < /dev/tty > /dev/tty 2>&1
