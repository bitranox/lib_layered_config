Here is the concept for **lib_layered_config** – translated to English, aligned with the current architecture, and ready to evolve with the codebase.

---

# IDEA

Build a configurable layering library for applications.

* Merge configuration payloads from multiple layers (explicit defaults, app/system defaults, host, user, dotenv, environment variables).
* Merge key-by-key; later layers override earlier ones without deleting unrelated keys.
* Built-in support for TOML and JSON, optional support for YAML.
* `.env` files and process environment variables behave as first-class layers.
* Every setting exposes provenance (originating layer and file path).
* Keep the core pure-stdlib Python so it runs on Linux, macOS, and Windows.
* Offer generators for example configuration trees so developers can bootstrap projects quickly.
* Provide a typed, immutable public API backed by a well-defined error taxonomy.
* Ship a Rich Click CLI mirroring the library orchestration.

Use this checklist as a living reference; extend it as the solution grows.

---

## A) Goals & Scope

1. **Primary Goals** *(current status)*

* [x] Deterministic precedence order `defaults → app → host → user → dotenv → env` implemented in `_layers.collect_layers` and enforced by tests.
* [x] Structured file loaders (TOML/JSON core via `tomllib` stdlib 3.11+ or `tomli` fallback for 3.10, YAML behind optional extra).
* [x] Immutable `Config` value object exposing `get`, `origin`, `as_dict`, `to_json`, `with_overrides`.
* [x] Clean Architecture boundaries (Domain, Application, Adapters, Composition Root) reflected in module layout and import-linter contracts.
* [x] Trace-aware structured logging provided by `observability` helpers, consumed by adapters/composition.
* [x] Rich Click CLI (`lib_layered_config`) with commands for read/read-json, deploy, generate-examples, env-prefix, info, fail.
* [x] Example tree generator and deployment helpers for docs/onboarding (`examples/generate`, `examples/deploy`).
* [x] Interactive conflict handling for `deploy` command with backup (`.bak`) and UCF (`.ucf`) file support.
* [x] Smart skipping for `deploy` when destination content is identical (avoids unnecessary backups).
* [x] `.d` directory expansion for configuration files (e.g., `config.toml` → `config.d/`) with lexicographic ordering and provenance tracking per file.

2. **Non-Goals** *(still out of scope)*

* Schema validation beyond structural guards (future adapter extension).
* Framework-specific integrations (library stays framework-agnostic).

## B) Architecture & Organisation

1. **Domain Layer**
   - `Config` value object (immutable mapping; `get`, `as_dict`, `to_json`, `origin`, `with_overrides`).
   - Error hierarchy `ConfigError`, `InvalidFormatError`, `ValidationError`, `NotFoundError`.

2. **Application Layer**
   - Ports (Protocols) for `PathResolver`, `FileLoader`, `DotEnvLoader`, `EnvLoader`, `Merger`.
   - Merge use case (`merge_layers`) with provenance tracking and helper functions for scalar/branch merging.

3. **Adapters**
   - Path resolvers per OS (Linux/XDG, macOS Application Support, Windows ProgramData/AppData) honour environment overrides; reused by deployment helpers.
   - Structured file loaders (TOML/JSON core, YAML optional) emit deterministic logging and raise `InvalidFormatError`/`NotFoundError`.
   - Dotenv loader (upward search + platform extras, `__` nesting, quoting rules) and environment loader (namespace filtering, coercion for bool/null/int/float, provenance logging).
   - `.d` directory expansion (`adapters/file_loaders/_dot_d.py`) automatically discovers and merges companion `.d` directories for any config file.
   - `observability` module exposes trace-aware logging helpers shared across adapters and composition.

4. **Composition Root**
   - `read_config`, `read_config_json`, and `read_config_raw` wire adapters, gather layers, merge payloads, and return `Config`/raw/JSON views.
   - Supports optional `default_file` seeding, suffix preference ordering, configurable `.env` start directory, and wraps adapter errors in `LayerLoadError`.

5. **Presentation & Tooling**
   - Rich Click CLI with commands: `info`, `env-prefix`, `read`, `read-json`, `deploy`, `generate-examples`, `fail`.
   - Deploy command with conflict handling: `--force` (backup and overwrite), `--batch` (keep and write `.ucf` for CI), or interactive prompt (keep/overwrite).
   - Example and deployment helpers mirrored by CLI commands and used in documentation.
   - Testing helper (`i_should_fail`) and notebooks for deterministic failure-path demonstrations.

## C) Tests & Quality

* Unit tests for domain, adapters, merge logic, observability, and example/deployment helpers.
* Property-based tests (Hypothesis) verifying merge associativity and "last layer wins".
* Adapter contract tests ensuring runtime adherence to ports.
* E2E CLI tests exercising commands, provenance output, deployment flows, and failure handling.
* Behavior tests for deploy conflict handling (backup creation, UCF files, numbered suffixes).
* Notebook execution test for `notebooks/Quickstart.ipynb` (CI smoke test).
* Import-Linter contracts enforcing layer boundaries.
* Coverage gate configured at ≥90% in `pyproject.toml` and enforced via `make test`.

## D) Toolchain & Automation

* `pyproject.toml` targeting Python ≥3.10 with dev extras (pytest, hypothesis, coverage, ruff, pyright, bandit, pip-audit, import-linter, textual, twine, etc.). Uses `tomli` as a conditional dependency for Python < 3.11.
* `Makefile` targets: `test`, `build`, `run`, `push`, `bump`, `clean`, `menu`, `dev` (auto-bootstrap enabled).
* CI (`.github/workflows/ci.yml`) matrix covering Python 3.10-3.13 and latest 3.x, Ruff linting, import-linter, Pyright, pytest with coverage, and notebook execution.
* Release workflow (`release.yml`) builds wheels/sdists and publishes via Twine once tagged (`vX.Y.Z`).

## E) Examples & Documentation

* README highlights precedence, OS-specific search paths, CLI usage, doctest-powered API snippets, and provenance examples.
* System design docs (`docs/systemdesign/*.md`) track module responsibilities, test matrix, and this concept.
* Notebook `notebooks/Quickstart.ipynb` demonstrates prefix calculation, example generation, and `read_config` end-to-end.
* Example generator outputs layered trees (`etc/<slug>`, host overrides, user config, `.env.example`).

## F) Follow-up / Backlog

* Optional validation adapters (Pydantic, JSON Schema) for stricter configuration contracts.
* Change-detection/watch mode for developer tooling (future enhancement).
* Integration snippets for common frameworks (FastAPI, Django) once the core stabilises.
* Additional telemetry hooks (metrics/timings) if future requirements demand them.
