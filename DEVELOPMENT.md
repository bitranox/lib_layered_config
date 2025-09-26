# Development

## Make Targets

| Target            | Description                                                                                |
|-------------------|--------------------------------------------------------------------------------------------|
| `help`            | Show this table                                                                            |
| `install`         | Editable install of the package                                                            |
| `dev`             | Install package with development extras (`ruff`, `pyright`, `pytest`, `bandit`, etc.)      |
| `test`            | Run lint (Ruff), import-linter, type-check (Pyright), pytest (with coverage ≥90%), Codecov |
| `run`             | Print the default environment prefix (sanity check)                                        |
| `version-current` | Print the current version from `pyproject.toml`                                            |
| `bump`            | Bump version (updates `pyproject.toml` + `CHANGELOG.md`)                                    |
| `bump-patch`      | Convenience alias for `make bump PART=patch`                                               |
| `bump-minor`      | Convenience alias for `make bump PART=minor`                                               |
| `bump-major`      | Convenience alias for `make bump PART=major`                                               |
| `clean`           | Remove caches, build artefacts, and coverage files                                         |
| `push`            | Run full test pipeline, prompt for commit message, and push to the selected remote         |
| `build`           | Build wheel/sdist and verify Conda/Homebrew/Nix packaging                                  |
| `menu`            | Textual-based TUI for running targets interactively                                        |

### Target Parameters (env vars)

- **Global**: `PY` (python interpreter), `PIP` (pip executable)
- **test**: `COVERAGE=on|auto|off` (default `on`), `SKIP_BOOTSTRAP=1`, `TEST_VERBOSE=1`, `CODECOV_TOKEN`
- **push**: `REMOTE=<name>` (default `origin`), `COMMIT_MESSAGE="..."`

## Test Pipeline (`make test`)

`make test` orchestrates the full local CI workflow:

1. Sync packaging definitions (`packaging/conda`, `packaging/brew`, `packaging/nix`) with `pyproject.toml`.
2. `ruff check .` (lint) and `ruff format --check`.
3. `python -m lint_imports --config pyproject.toml` (Clean Architecture contracts).
4. `pyright` (strict type checking).
5. `pytest` with doctests, coverage reports, and `--cov-fail-under=90`.
6. Optional Codecov upload (requires `CODECOV_TOKEN` or running in CI).

Coverage data is written to `.coverage`/`coverage.xml`. The harness creates an allow-empty commit named `test: auto commit before Codecov upload` before uploading so Codecov can associate the report with a SHA. Drop it afterwards with `git reset --soft HEAD~1` if undesired.

## Recommended Workflow

```bash
pip install -e .[dev]
ruff check .
pyright
pytest --maxfail=1
bandit -q -r src/lib_layered_config
pip-audit
```

Use `make test` for the full gate; the individual commands help when iterating quickly.

Coverage is enforced at 90% for the `src/lib_layered_config` package. `py.typed` ships with the distribution so external type checkers treat the library as typed by default.

## Architecture Rules

The import-linter configuration in `pyproject.toml` enforces:

- `lib_layered_config.domain` **cannot** import from application/adapters/core.
- `lib_layered_config.application` can only depend on domain.
- `lib_layered_config.adapters` may depend on domain/application but not the reverse.

Keep runtime code side-effect free at import time. Only adapters and the composition root perform I/O.

## Packaging Sync

`make test`, `make push`, and `python scripts/bump_version.py --sync-packaging` update:

- Conda recipe version + Python floor (≥3.12).
- Homebrew formula tarball + Python dependency.
- Nix flake version and interpreter choice.

Fill in distribution-specific hashes before publishing.

## Release Checklist

1. Update `CHANGELOG.md` with user-facing entries.
2. Bump the version (`make bump VERSION=X.Y.Z`).
3. Commit, tag (`git tag vX.Y.Z`), and push (`git push --tags`).
4. Ensure `PYPI_API_TOKEN` is configured for `.github/workflows/release.yml`.
5. Monitor CI (lint, types, tests, security, build, packaging verifications).

## Observability Guidelines

- Use `lib_layered_config.observability.log_*` helpers inside adapters to emit structured logs.
- Set a trace identifier with `lib_layered_config.bind_trace_id("abc123")` when tracing requests.
- Domain/application layers MUST remain log-free to uphold Clean Architecture boundaries.

## Examples & Docs

- `lib_layered_config.examples.generate.generate_examples` scaffolds commented example files for each layer (`app/`, `hosts/`, `user/`, `.env.example`).
- README snippets double as doctests; keep them short and deterministic.

Happy building!

