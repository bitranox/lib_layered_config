# Development

## Make Targets

| Target            | Description                                                                                |
|-------------------|--------------------------------------------------------------------------------------------|
| `help`            | Show help                                                                                  |
| `install`         | Install package editable                                                                   |
| `dev`             | Install package with dev extras                                                            |
| `test`            | Lint, type-check, run tests with coverage, upload to Codecov                               |
| `run`             | Run module CLI (requires dev install or src on PYTHONPATH)                                 |
| `version-current` | Print current version from pyproject.toml                                                  |
| `bump`            | Bump version (updates pyproject.toml and CHANGELOG.md)                                     |
| `bump-patch`      | Bump patch version (X.Y.Z -> X.Y.(Z+1))                                                    |
| `bump-minor`      | Bump minor version (X.Y.Z -> X.(Y+1).0)                                                    |
| `bump-major`      | Bump major version ((X+1).0.0)                                                             |
| `clean`           | Remove caches, build artifacts, and coverage                                               |
| `push`            | Run tests, prompt for/accept a commit message, create (allow-empty) commit, push to remote |
| `build`           | Build wheel/sdist and attempt conda, brew, and nix builds (auto-installs tools if missing) |
| `menu`            | Interactive TUI to run targets and edit parameters (requires dev dep: textual)             |

### Target Parameters (env vars)

- **Global**
  - `PY` (default: `python3`) — interpreter used to run scripts
  - `PIP` (default: `pip`) — pip executable used by bootstrap/install

- **install**
  - No specific parameters (respects `PY`, `PIP`).

- **dev**
  - No specific parameters (respects `PY`, `PIP`).

- **test**
  - `COVERAGE=on|auto|off` (default: `on`) — controls pytest coverage run and Codecov upload
  - `SKIP_BOOTSTRAP=1` — skip auto-install of dev tools if missing
  - `TEST_VERBOSE=1` — echo each command executed by the test harness
  - Also respects `CODECOV_TOKEN` when uploading to Codecov

- **run**
  - No parameters via `make` (always shows `--help`). For custom args: `python scripts/run_cli.py -- <args>`.

- **version-current**
  - No parameters

- **bump**
  - `VERSION=X.Y.Z` — explicit target version
  - `PART=major|minor|patch` — semantic part to bump (default if `VERSION` not set: `patch`)

- **bump-patch** / **bump-minor** / **bump-major**
  - No parameters; shorthand for `make bump PART=...`

- **clean**
  - No parameters

- **push**
  - `REMOTE=<name>` (default: `origin`) — git remote to push to
  - `COMMIT_MESSAGE="..."` — optional commit message used by the automation; if unset, the target prompts (or uses the default `chore: update` when non-interactive).

- **build**
  - No parameters via `make`. Advanced: call the script directly, e.g. `python scripts/build.py --no-conda --no-nix`.

- **release**
  - `REMOTE=<name>` (default: `origin`) — git remote to push to
  - Advanced (via script): `python scripts/release.py --retries 5 --retry-wait 3.0`

## Interactive Menu (Textual)

`make menu` launches a Textual-powered TUI to browse targets, edit parameters, and run them with live output.

Install dev extras if you haven’t:

```bash
pip install -e .[dev]
```

Run the menu:

```bash
make menu
```

### Target Details

- `test`: single entry point for local CI — runs ruff lint + format check, pyright, pytest (including doctests) with coverage (enabled by default), and uploads coverage to Codecov if configured (reads `.env`).
  - Auto-bootstrap: `make test` will try to install dev tools (`pip install -e .[dev]`) if `ruff`/`pyright`/`pytest` are missing. Set `SKIP_BOOTSTRAP=1` to skip this behavior.
- `build`: creates wheel/sdist, then attempts Conda, Homebrew, and Nix builds. It auto-installs missing tools (Miniforge, Homebrew, Nix) when needed.
- `version-current`: prints current version from `pyproject.toml`.
- `bump`: updates `pyproject.toml` version and inserts a new section in `CHANGELOG.md`. Use `VERSION=X.Y.Z make bump` or `make bump-minor`/`bump-major`/`bump-patch`.
- Additional scripts (`pipx-*`, `uv-*`, `which-cmd`, `verify-install`) provide install/run diagnostics.

## Development Workflow

```bash
make test                 # ruff + pyright + pytest + coverage (default ON)
SKIP_BOOTSTRAP=1 make test  # skip auto-install of dev deps
COVERAGE=off make test       # disable coverage locally
COVERAGE=on make test        # force coverage and generate coverage.xml/codecov.xml

**Automation notes**

- `make test` commits (allow-empty) before uploading coverage; drop the commit with `git reset --soft HEAD~1` if you do not want to keep it.
- `make push` prompts for a commit message (or accepts `COMMIT_MESSAGE="..."`) and always performs a commit—even when nothing is staged—before pushing.
```

### Packaging sync (Conda/Brew/Nix)

- `make test` and `make push` automatically align the packaging skeletons in `packaging/` with the current `pyproject.toml`:
  - Conda: updates `{% set version = "X.Y.Z" %}` and both `python >=X.Y` constraints to match `requires-python`.
  - Homebrew: updates the source URL tag to `vX.Y.Z` and sets `depends_on "python@X.Y"` to match `requires-python`.
  - Nix: updates the package version and switches `pkgs.pythonXYZPackages` / `pkgs.pythonXYZ` to match the minimum Python version from `requires-python`.
- To run just the sync without bumping versions: `python scripts/bump_version.py --sync-packaging`.
- On release tags (`v*.*.*`), CI validates that packaging files are consistent with `pyproject.toml`.

### Versioning & Metadata

- Single source of truth for package metadata is `pyproject.toml` (`[project]`).
- Runtime metadata is resolved via `importlib.metadata` (see `src/lib_layered_config/__init__conf__.py`).
- Do not duplicate the version in code; bump only `pyproject.toml` and update `CHANGELOG.md`.
- Console script name is discovered from entry points; defaults to `lib_layered_config`.

### Packaging Skeletons

Starter files for package managers live under `packaging/`:

- Conda: `packaging/conda/recipe/meta.yaml`
- Homebrew: `packaging/brew/Formula/lib-layered-config.rb`
- Nix: `packaging/nix/flake.nix`

These templates auto-sync from `pyproject.toml` during version bumps and `make test`/`make push`, but you still need to fill placeholders (e.g., sha256) before publishing.

### CI & Publishing

GitHub Actions workflows:

- `.github/workflows/ci.yml` — lint/type/test, build wheel/sdist, verify pipx/uv installs, Nix and Conda builds.
- `.github/workflows/release.yml` — on tags `v*.*.*`, builds artifacts and publishes to PyPI when `PYPI_API_TOKEN` is configured.

Release checklist:

1. Bump `pyproject.toml` version and update `CHANGELOG.md`.
2. Tag the commit (`git tag vX.Y.Z && git push --tags`).
3. Ensure `PYPI_API_TOKEN` secret is configured.
4. Let CI publish artifacts to PyPI.

For Conda/Homebrew/Nix distribution, submit the updated files under `packaging/`. CI attempts builds but does not publish automatically.

### Local Codecov uploads

- `make test` (coverage enabled) produces `coverage.xml` and `codecov.xml`, then attempts a Codecov upload.
- For private repos, set `CODECOV_TOKEN` (see `.env.example`) or export it in your shell.
- Public repos typically do not require a token.
- The harness performs an allow-empty commit named `test: auto commit before Codecov upload` immediately before uploading so the report is associated with a revision. Remove or amend that commit after the run if you do not wish to keep it.
