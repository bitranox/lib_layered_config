# Contributing Guide

Thanks for helping improve **lib_layered_config**. This document summarises the workflow, automation, and quality bars that keep the project healthy.

## 1. Workflow Overview

1. Fork and branch - use short, imperative branch names (`feature/deep-merge-policy`, `fix/env-loader`).
2. Make focused commits - keep unrelated refactors out of the same change.
3. Run `make test` locally before pushing (see the automation note below).
4. Update documentation and changelog entries impacted by the change.
5. Open a pull request referencing any relevant issues.

## 2. Commits & Pushes

- Commit messages should be imperative (`Add path resolver contracts`, `Fix dotenv parser`).
- `make test` makes no commit.
- `make push MSG="..."` runs the gate, stages every change (`git add -A`), commits with that message and pushes. Without `MSG=` it asks for a message on a terminal and uses `chores` otherwise; with nothing to commit the commit is empty. See [DEVELOPMENT.md](DEVELOPMENT.md#make-targets).

## 3. Coding Standards

- Apply the repository's Clean Architecture / SOLID rules (see `CLAUDE.md`).
- Domain layer (`lib_layered_config.domain`) remains free of I/O and logging; its one third-party use is `json_codec`, which uses orjson where it is installed and can run.
- Application layer orchestrates use cases and depends only on domain abstractions.
- Adapters contain all boundary I/O (filesystem, env vars). Structured logs come from the adapters, the composition root, and the application merge's warnings, all through `lib_layered_config.observability`.
- The public surface is what `lib_layered_config.__all__` lists; anything else is internal. Add to it only on purpose, and document the addition in `docs/python-api.md`.

## 4. Tests & Tooling

- `make test` formats and fixes with Ruff, then runs the checks: Ruff, import-linter, Pyright, Pytest with doctests and coverage of at least 90%, Bandit and pip-audit; [DEVELOPMENT.md](DEVELOPMENT.md#test-pipeline-make-test) lists every stage.
- Shared fixtures live under `tests/support`; prefer `create_layered_sandbox` over bespoke platform scaffolding.
- The dev extra (`pip install -e .[dev]`) installs Ruff, Pyright, Pytest, Bandit, pip-audit, Hypothesis, and typing/coverage helpers.
- Import contracts live in `pyproject.toml` (`[tool.importlinter]`). Update them if you move modules between layers.
- When adding new adapters, extend `tests/adapters/test_port_contracts.py` to verify ports remain satisfied and precedence rules stay intact.
- Notebook execution is marked with `@pytest.mark.slow`; quick iteration can run `pytest -m "not slow"`, while `make test` still executes the full suite.
- Coverage data is written to `/tmp/.coverage...` (see `[tool.coverage.run].data_file`); remove those files if you need to retry a run manually.

## 5. Documentation Checklist

Before opening a PR, confirm:

- [ ] `make test` passes locally, and you committed what it reformatted.
- [ ] README usage snippets, tables, and doctests reflect the change.
- [ ] `CHANGELOG.md` documents user-visible behaviour.
- [ ] Example generators still run idempotently (`python - <<'PY'` snippets in docs when relevant).

## 6. Security & Configuration

- Never commit secrets. Tokens (Codecov, PyPI) belong in `.env` (ignored by git) or CI secrets.
- Sanitise structured log fields; avoid leaking secrets in log metadata.

Happy hacking!
