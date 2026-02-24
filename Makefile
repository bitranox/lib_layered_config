# BMK MAKEFILE 2.7.1
# do not alter this file - it might be overwritten on new versions of BMK
# if You want to alter it, remove the first line # BMK MAKEFILE 1.0 - then it is a custom makefile and will not be overwritten
# bmk Makefile — thin wrapper calling bmk via uvx
#
# Usage:
#   make test                        # run test suite
#   make test --verbose              # forward extra flags
#   make bump-patch                  # bump patch version
#   make push fix login bug          # push with commit message
#   make custom deploy                # run custom command
#   make custom deploy --dry-run
#
# All targets invoke `uvx bmk@latest` so the latest published
# version is always used, regardless of local install state.
#
# Arguments after the target name are forwarded automatically.
# You can also use ARGS="..." explicitly if preferred.

SHELL := /bin/bash
.DEFAULT_GOAL := help

BMK := uvx bmk@latest
ARGS ?=

# ──────────────────────────────────────────────────────────────
# Argument forwarding via MAKECMDGOALS
# ──────────────────────────────────────────────────────────────
# Allows natural argument passing: make push fix login bug
# instead of: make push ARGS="fix login bug"

# All targets that accept trailing arguments
_BMK_TARGETS := test t test-human th testintegration testi ti testintegration-human tih \
	codecov coverage cov \
	build bld clean cln cl run \
	bump-major bump-minor bump-patch bump \
	commit c push psh p release rel r \
	dependencies deps d dependencies-update \
	config config-deploy config-generate-examples \
	send-email send-notification custom \
	info logdemo

ifneq (,$(filter $(_BMK_TARGETS),$(firstword $(MAKECMDGOALS))))
  # Capture everything after the first word as extra arguments
  _EXTRA := $(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))
  # Append to ARGS (so explicit ARGS="..." still works alongside)
  override ARGS += $(_EXTRA)
endif

# ──────────────────────────────────────────────────────────────
# Test & Quality
# ──────────────────────────────────────────────────────────────

.PHONY: test t
test:  ## Run test suite [alias: t]
	$(BMK) test $(ARGS)
t:
	$(BMK) test $(ARGS)

.PHONY: test-human th
test-human:  ## Run test suite with human-readable output [alias: th]
	$(BMK) test --human $(ARGS)
th:
	$(BMK) test --human $(ARGS)

.PHONY: testintegration testi ti
testintegration:  ## Run integration tests only [aliases: testi, ti]
	$(BMK) testintegration $(ARGS)
testi ti:
	$(BMK) testintegration $(ARGS)

.PHONY: testintegration-human tih
testintegration-human:  ## Run integration tests with human-readable output [alias: tih]
	$(BMK) testintegration --human $(ARGS)
tih:
	$(BMK) testintegration --human $(ARGS)

.PHONY: codecov coverage cov
codecov:  ## Upload coverage report to Codecov [aliases: coverage, cov]
	$(BMK) codecov $(ARGS)
coverage cov:
	$(BMK) codecov $(ARGS)

# ──────────────────────────────────────────────────────────────
# Build & Clean
# ──────────────────────────────────────────────────────────────

.PHONY: build bld
build:  ## Build wheel and sdist artifacts [alias: bld]
	$(BMK) build $(ARGS)
bld:
	$(BMK) build $(ARGS)

.PHONY: clean cln cl
clean:  ## Remove build artifacts and caches [aliases: cln, cl]
	$(BMK) clean $(ARGS)
cln cl:
	$(BMK) clean $(ARGS)

# ──────────────────────────────────────────────────────────────
# Run
# ──────────────────────────────────────────────────────────────

.PHONY: run
run:  ## Run the project CLI via uvx
	$(BMK) run $(ARGS)

# ──────────────────────────────────────────────────────────────
# Version Bumping
# ──────────────────────────────────────────────────────────────

.PHONY: bump-major
bump-major:  ## Bump major version (X+1).0.0
	$(BMK) bump major $(ARGS)

.PHONY: bump-minor
bump-minor:  ## Bump minor version X.(Y+1).0
	$(BMK) bump minor $(ARGS)

.PHONY: bump-patch
bump-patch:  ## Bump patch version X.Y.(Z+1)
	$(BMK) bump patch $(ARGS)

.PHONY: bump
bump: bump-patch  ## Bump patch version (default for bump)

# ──────────────────────────────────────────────────────────────
# Git Operations
# ──────────────────────────────────────────────────────────────

.PHONY: commit c
commit:  ## Create a git commit with timestamped message [alias: c]
	$(BMK) commit $(ARGS)
c:
	$(BMK) commit $(ARGS)

.PHONY: push psh p
push:  ## Run tests, commit, and push to remote [aliases: psh, p]
	$(BMK) push $(ARGS)
psh p:
	$(BMK) push $(ARGS)

.PHONY: release rel r
release:  ## Create a versioned release (tag + GitHub release) [aliases: rel, r]
	$(BMK) release $(ARGS)
rel r:
	$(BMK) release $(ARGS)

# ──────────────────────────────────────────────────────────────
# Dependencies
# ──────────────────────────────────────────────────────────────

.PHONY: dependencies deps d
dependencies:  ## Check and list project dependencies [aliases: deps, d]
	$(BMK) dependencies $(ARGS)
deps d:
	$(BMK) dependencies $(ARGS)

.PHONY: dependencies-update
dependencies-update:  ## Update dependencies to latest versions
	$(BMK) dependencies update $(ARGS)

# ──────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────

.PHONY: config
config:  ## Show current merged configuration
	$(BMK) config $(ARGS)

.PHONY: config-deploy
config-deploy:  ## Deploy configuration to system/user directories
	$(BMK) config-deploy $(ARGS)

.PHONY: config-generate-examples
config-generate-examples:  ## Generate example configuration files
	$(BMK) config-generate-examples $(ARGS)

# ──────────────────────────────────────────────────────────────
# Email
# ──────────────────────────────────────────────────────────────

.PHONY: send-email
send-email:  ## Send an email via configured SMTP
	$(BMK) send-email $(ARGS)

.PHONY: send-notification
send-notification:  ## Send a plain-text notification email
	$(BMK) send-notification $(ARGS)

# ──────────────────────────────────────────────────────────────
# Custom Commands
# ──────────────────────────────────────────────────────────────

.PHONY: custom
custom:  ## Run a custom command (make custom <name> [args...])
	$(BMK) custom $(ARGS)

# ──────────────────────────────────────────────────────────────
# Info & Demos
# ──────────────────────────────────────────────────────────────

.PHONY: info
info:  ## Print resolved package metadata
	$(BMK) info $(ARGS)

.PHONY: logdemo
logdemo:  ## Run logging demonstration
	$(BMK) logdemo $(ARGS)

.PHONY: version-current
version-current:  ## Print current version
	$(BMK) --version

# ──────────────────────────────────────────────────────────────
# Development
# ──────────────────────────────────────────────────────────────

.PHONY: dev
dev:  ## Install package with dev extras (editable)
	uv pip install -e ".[dev]"


.PHONY: install
install:  ## Editable install (no dev extras)
	uv pip install -e .

# ──────────────────────────────────────────────────────────────
# Help
# ──────────────────────────────────────────────────────────────

.PHONY: help
help:  ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-26s\033[0m %s\n", $$1, $$2}' | \
		sort

# ──────────────────────────────────────────────────────────────
# No-op overrides for trailing argument words (MUST be last)
# ──────────────────────────────────────────────────────────────
# Placed after all real target definitions so the no-op recipes
# override them.  This prevents "make push codecov fix" from
# executing the real codecov target — "codecov" is an argument
# to push, not a separate command.
ifneq (,$(_EXTRA))
$(_EXTRA):
	@:
endif
