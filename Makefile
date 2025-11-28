SHELL := /bin/bash

PYTHON ?= python3
SCRIPTS ?= $(PYTHON) -m scripts

.PHONY: help install dev test run clean build push release coverage version-current bump bump-patch bump-minor bump-major dependencies dependencies-update menu

help:
	$(SCRIPTS) help

install:
	$(SCRIPTS) install

dev:
	$(SCRIPTS) dev

test:
	$(SCRIPTS) test

run:
	$(SCRIPTS) run

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

push:
	$(SCRIPTS) push

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
