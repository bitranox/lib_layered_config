SHELL := /bin/bash

PYTHON ?= python3
SCRIPTS ?= $(PYTHON) -m scripts

.PHONY: help install dev test run clean build push release version-current bump bump-patch bump-minor bump-major menu

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

push:
	$(SCRIPTS) push

build:
	$(SCRIPTS) build

release:
	$(SCRIPTS) release

menu:
	$(SCRIPTS) menu
