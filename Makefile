SHELL := /bin/bash
.ONESHELL:
# Config
PY ?= python3
PIP ?= pip
PKG ?= lib_layered_config
GIT_REF ?= v0.0.1
REMOTE ?= origin
NIX_FLAKE ?= packaging/nix
HATCHLING_VERSION ?= 1.25.0
BREW_FORMULA ?= packaging/brew/Formula/lib-layered-config.rb
CONDA_RECIPE ?= packaging/conda/recipe
FAIL_UNDER ?= 80
# Coverage mode: on|auto|off (default: on locally)
# - on   : always run coverage
# - auto : enable on CI or when CODECOV_TOKEN is set
# - off  : never run coverage
COVERAGE ?= on

.PHONY: help install dev test run clean build push release version-current bump bump-patch bump-minor bump-major menu _bootstrap-dev

help: ## Show help
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Install package editable
	$(PY) scripts/install.py

dev: ## Install package with dev extras
	$(PY) scripts/dev.py

_bootstrap-dev:
	@if [ "$(SKIP_BOOTSTRAP)" = "1" ]; then \
	  echo "[bootstrap] Skipping dev dependency bootstrap (SKIP_BOOTSTRAP=1)"; \
	else \
	  if ! command -v ruff >/dev/null 2>&1 || ! command -v pyright >/dev/null 2>&1 || ! python -c "import pytest" >/dev/null 2>&1; then \
	    echo "[bootstrap] Installing dev dependencies via '$(PIP) install -e .[dev]'"; \
	    $(PIP) install -e .[dev]; \
	  else \
	    echo "[bootstrap] Dev tools present"; \
	  fi; \
	  if ! python -c "import sqlite3" >/dev/null 2>&1; then \
	    echo "[bootstrap] sqlite3 stdlib module not available; installing pysqlite3-binary"; \
	    $(PIP) install pysqlite3-binary || true; \
	  fi; \
	fi

test: _bootstrap-dev ## Lint, type-check, run tests with coverage, upload to Codecov
	$(PY) scripts/test.py --coverage=$(COVERAGE)

run: ## Display default environment prefix for the current slug
	$(PY) -c "from lib_layered_config import default_env_prefix; print(default_env_prefix("lib-layered-config"))"

version-current: ## Print current version from pyproject.toml
	$(PY) scripts/version_current.py

bump: ## Bump version: VERSION=X.Y.Z or PART=major|minor|patch (default: patch); updates pyproject.toml and CHANGELOG.md
	@set -e; \
	if [ -n "$(VERSION)" ]; then \
	  $(PY) scripts/bump.py --version "$(VERSION)"; \
	else \
	  $(PY) scripts/bump.py --part "$(PART)"; \
	fi

bump-patch: ## Bump patch version (X.Y.Z -> X.Y.(Z+1))
	$(PY) scripts/bump_patch.py

bump-minor: ## Bump minor version (X.Y.Z -> X.(Y+1).0)
	$(PY) scripts/bump_minor.py

bump-major: ## Bump major version ((X+1).0.0)
	$(PY) scripts/bump_major.py

clean: ## Remove caches, build artifacts, and coverage
	rm -rf \
	  .pytest_cache \
	  .ruff_cache \
	  .pyright \
	  .mypy_cache \
	  .tox .nox \
	  .eggs *.egg-info \
	  build dist \
	  htmlcov .coverage coverage.xml \
	  codecov.sh \
	  .cache \
	  result

push: ## Commit all changes once and push to GitHub (no CI monitoring)
	@if [ -z "$${COMMIT_MESSAGE+x}" ]; then \
	  read -p "[push] Commit message [chore: update]: " __msg; \
	  COMMIT_MESSAGE="$${__msg:-chore: update}"; \
	else \
	  COMMIT_MESSAGE="$${COMMIT_MESSAGE:-chore: update}"; \
	fi; \
	COMMIT_MESSAGE="$$COMMIT_MESSAGE" $(PY) scripts/push.py --remote=$(REMOTE)

build: ## Build wheel/sdist and attempt conda, brew, and nix builds (auto-installs tools if missing)
	$(PY) scripts/build.py


release: ## Create and push tag vX.Y.Z from pyproject, create GitHub release (if gh present), then sync packaging
	$(PY) scripts/release.py --remote=$(REMOTE)

menu: ## Interactive TUI menu
	$(PY) -u scripts/menu.py < /dev/tty > /dev/tty 2>&1
