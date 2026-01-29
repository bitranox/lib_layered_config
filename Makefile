SHELL := /bin/bash

PYTHON ?= python3
SCRIPTS ?= $(PYTHON) -m scripts

.PHONY: help install dev test test-local run clean build push release coverage version-current bump bump-patch bump-minor bump-major dependencies dependencies-update menu

# Capture trailing words after "push" so `make push fix typo` works unquoted.
ifeq (push,$(firstword $(MAKECMDGOALS)))
  PUSH_ARGS := $(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))
  $(eval $(PUSH_ARGS):;@:)
endif

# Capture trailing words after "run" so `make run config` works unquoted.
ifeq (run,$(firstword $(MAKECMDGOALS)))
  RUN_ARGS := $(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))
  $(eval $(RUN_ARGS):;@:)
endif

help:
	$(SCRIPTS) help

install:
	$(SCRIPTS) install

dev:
	$(SCRIPTS) dev

test:
	$(SCRIPTS) test

run:
	$(SCRIPTS) run $(RUN_ARGS)

version-current:
	$(SCRIPTS) version-current

bump:
	$(SCRIPTS) bump

bump-patch:
	$(SCRIPTS) bump-patch

bump-minor:
	$(SCRIPTS) bump-minor

bump-major:
	$(SCRIPTS) bump-major

clean:
	$(SCRIPTS) clean

coverage:
	$(SCRIPTS) coverage

test-local:
	$(SCRIPTS) test-local

push:
	$(SCRIPTS) push $(PUSH_ARGS)

build:
	$(SCRIPTS) build

release:
	$(SCRIPTS) release

dependencies:
	$(SCRIPTS) dependencies

dependencies-update:
	$(SCRIPTS) dependencies-update

menu:
	$(SCRIPTS) menu
