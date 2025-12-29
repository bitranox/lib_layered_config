# Contributing Guide

Thanks for helping improve **lib_layered_config**. This document summarises the workflow, automation, and quality bars that keep the project healthy.

## 1. Workflow Overview

1. Fork and branch – use short, imperative branch names (`feature/deep-merge-policy`, `fix/env-loader`).
2. Make focused commits – keep unrelated refactors out of the same change.
3. Run `make test` locally before pushing (see the automation note below).
4. Update documentation and changelog entries impacted by the change.
5. Open a pull request referencing any relevant issues.

## 2. Commits & Pushes

- Commit messages should be imperative (`Add path resolver contracts`, `Fix dotenv parser`).
- The test harness (`make test`) performs an allow-empty commit named `test: auto commit before Codecov upload` immediately before it sends coverage to Codecov. Drop it afterwards with `git reset --soft HEAD~1` if you do not want to keep it.
- `make push` always performs a commit before pushing. It prompts for a message when run interactively, honours `COMMIT_MESSAGE="…"` when provided, and creates an empty commit if nothing is staged. The Textual menu (`make menu → push`) exposes the same behaviour via an input field.

## 3. Coding Standards

- Apply the repository's Clean Architecture / SOLID rules (see `CLAUDE.md`).
- Domain layer (`lib_layered_config.domain`) remains pure Python (stdlib only), free of I/O and logging.
- Application layer orchestrates use cases and depends only on domain abstractions.
- Adapters contain all boundary I/O (filesystem, env vars, logging) and are the only place structured logs are emitted.
- Public surface is consciously tiny: `Config`, `read_config`, `read_config_raw`, error classes, `default_env_prefix`, `bind_trace_id`, `get_logger`.

## 4. Tests & Tooling

- `make test` runs Ruff (lint + format check), import-linter, Pyright, and Pytest with coverage ≥90% plus doctests.
- Shared fixtures live under `tests/support`; prefer `create_layered_sandbox` over bespoke platform scaffolding.
- The dev extra (`pip install -e .[dev]`) installs Ruff, Pyright, Pytest, Bandit, pip-audit, Hypothesis, and typing/coverage helpers.
- Import contracts live in `pyproject.toml` (`[tool.importlinter]`). Update them if you move modules between layers.
- When adding new adapters, extend `tests/adapters/test_port_contracts.py` to verify ports remain satisfied and precedence rules stay intact.
- Notebook execution is marked with `@pytest.mark.slow`; quick iteration can run `pytest -m "not slow"`, while `make test` still executes the full suite.
- Coverage data is written to `/tmp/.coverage...` (see `[tool.coverage.run].data_file`); remove those files if you need to retry a run manually.

## 5. Documentation Checklist

Before opening a PR, confirm:

- [ ] `make test` passes locally (and you removed the auto-created Codecov commit if undesired).
- [ ] README usage snippets, tables, and doctests reflect the change.
- [ ] `CHANGELOG.md` documents user-visible behaviour.
- [ ] Example generators still run idempotently (`python - <<'PY'` snippets in docs when relevant).

## 6. Security & Configuration

- Never commit secrets. Tokens (Codecov, PyPI) belong in `.env` (ignored by git) or CI secrets.
- Sanitise structured log fields; avoid leaking secrets in log metadata.

Happy hacking!
