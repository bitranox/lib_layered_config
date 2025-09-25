# Packaging (Conda • Homebrew • Nix)

This directory contains packaging files and an automated sync flow so they stay aligned with `pyproject.toml`.

## TL;DR

- To bump the project and auto-sync all packaging files:
  - Exact version: `make bump VERSION=X.Y.Z`
  - Or semantic part: `make bump PART=patch|minor|major`
- To only synchronize packaging to the current `pyproject.toml` without changing versions:
  ```bash
  python3 scripts/bump_version.py --sync-packaging
  ```
- `make test` runs the same sync step up-front to keep packaging up to date.

## What auto-sync updates

The script `scripts/bump_version.py` updates the following when network access is available:

1) Conda recipe (`packaging/conda/recipe/meta.yaml`)
   - Sets Jinja version to the current `pyproject.toml` version.
   - Aligns `run:` requirements with `[project].dependencies` from `pyproject.toml`.
   - Syncs the Python constraint (`python >=X.Y`) from `requires-python`.
   - Computes and fills `sha256` for the GitHub release tarball `vX.Y.Z` when reachable.

2) Homebrew formula (`packaging/brew/Formula/lib-layered-config.rb`)
   - Updates the source tarball URL tag to `vX.Y.Z` and its primary `sha256` when reachable.
   - Sets the `depends_on "python@X.Y"` line from `requires-python`.
   - For each runtime dependency in `pyproject.toml`, attempts to resolve a PyPI sdist URL and `sha256`, updating/creating `resource` stanzas.

3) Nix flake (`packaging/nix/flake.nix`)
   - Sets the library package `version` and `rev = "vX.Y.Z"` placeholders.
   - Aligns the Python package set (e.g., `python312Packages`) and devShell interpreter with `requires-python`.
   - Rewrites `propagatedBuildInputs` from `[project].dependencies`.

Notes:
- If the network is unavailable, the sync will skip hashes and keep existing values.
- Review generated dependency/resource names; some projects may use a different package name in specific ecosystems.

## Conda (packaging/conda/recipe)

- Build locally:
  ```bash
  conda build packaging/conda/recipe
  ```
- Consider submitting to conda-forge via a feedstock.

## Homebrew (packaging/brew/Formula)

- Build locally on macOS:
  ```bash
  make build       # attempts Homebrew build; auto-installs if missing
  lib_layered_config --version
  ```
- Helpful checks:
  ```bash
  brew uninstall lib-layered-config || true
  brew audit --strict --formula packaging/brew/Formula/lib-layered-config.rb || true
  ```

## Nix (packaging/nix)

- Local build/run:
  ```bash
  make build
  make nix-run
  ```
- For reproducible releases, prefer a `fetchFromGitHub` source with `rev` and `sha256`.
