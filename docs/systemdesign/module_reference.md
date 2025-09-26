# Module Reference

This catalogue documents each first-class module in `lib_layered_config`, linking
responsibilities, dependencies, and verification assets to the Clean Architecture
contracts of the project. Use it together with `docs/systemdesign/test_matrix.md`
when introducing features, moving code, or expanding test coverage so that
documentation, behaviour, and tests stay aligned.

---

## Architecture Overview

The library follows a domain-driven, ports-and-adapters layout:

| Layer | Key Modules | Primary Responsibilities |
|-------|-------------|--------------------------|
| Domain | `domain.config`, `domain.errors` | Immutable configuration value object and error taxonomy. |
| Application | `application.merge`, `application.ports` | Merge policy and public contracts for adapters. |
| Adapters | `adapters.path_resolvers.default`, `adapters.file_loaders.structured`, `adapters.dotenv.default`, `adapters.env.default` | Filesystem discovery, structured file parsing, dotenv parsing, and environment ingestion. |
| Composition Root | `core` | Orchestrates adapters, merge policy, and provenance emission. |
| Presentation & Tooling | `cli`, `observability`, `examples.*`, `testing` | CLI transport, structured logging helpers, documentation tooling, and failure harness. |
| Support & Fixtures | `tests/support/layered.py` | Shared cross-platform sandboxes and helpers used by the test suites. |

Each module section below describes purpose, dependencies, public API, and the
test suites that enforce its contract.

---

## Domain Layer

### Module: `lib_layered_config/domain/config.py`
- **Purpose:** Provide an immutable configuration mapping with provenance lookup
  and dotted-path helpers. Forms the canonical value object returned to callers.
- **Responsibilities:**
  - Encapsulate merged data in `MappingProxyType` to guarantee immutability.
  - Track source metadata via the `SourceInfo` typed dictionary.
  - Expose helpers such as `get`, `origin`, `with_overrides`, `as_dict`, and
    `to_json`.
- **Dependencies:** Standard library only (`dataclasses`, `typing`, `types`).
- **Public API:** `Config`, `SourceInfo`, `Config.EMPTY_CONFIG`, module-level
  helper `_deepcopy_mapping` (internal).
- **Error Handling:** Relies on standard mapping semantics (`KeyError`); no
  custom exceptions inside the module.
- **Verification:** `tests/unit/test_config.py` covers mapping behaviour,
  provenance, JSON serialisation, and override semantics.
- **Notes:** `with_overrides` performs a shallow merge by design; deep overrides
  are delegated to `read_config_raw` plus custom merging when required.

### Module: `lib_layered_config/domain/errors.py`
- **Purpose:** Define a shared error taxonomy that spans domain, application,
  and adapters.
- **Responsibilities:** Provide `ConfigError` base class with subclasses for
  parsing (`InvalidFormat`), validation (`ValidationError`), and missing data
  (`NotFound`).
- **Dependencies:** Standard library only.
- **Public API:** `ConfigError`, `InvalidFormat`, `ValidationError`, `NotFound`.
- **Verification:** `tests/unit/test_errors.py` enforces inheritance hierarchy
  and shared behaviour.

---

## Application Layer

### Module: `lib_layered_config/application/ports.py`
- **Purpose:** Declare runtime-checkable contracts that adapters must satisfy so
  the composition root depends on abstractions, not concrete implementations.
- **Responsibilities:** Define `PathResolver`, `FileLoader`, `DotEnvLoader`,
  `EnvLoader`, and `Merger` protocols with documented method semantics.
- **Dependencies:** `typing.Protocol`, `typing.runtime_checkable`.
- **Public API:** The five protocols above; no concrete logic.
- **Verification:** `tests/adapters/test_port_contracts.py` asserts the default
  adapters implement each protocol at runtime.

### Module: `lib_layered_config/application/merge.py`
- **Purpose:** Merge ordered configuration layers into a single mapping while
  retaining provenance metadata.
- **Responsibilities:**
  - `merge_layers` orchestrates per-layer merging.
  - Internal helpers (`_merge_layer`, `_merge_mapping`, `_merge_branch`,
    `_set_scalar`, `_clear_branch`, `_dotted_key`) enforce precedence rules and
    dotted-key tracking.
- **Dependencies:** Standard library (`copy.deepcopy`).
- **Public API:** `merge_layers` (primary entry point).
- **Error Handling:** Expects adapters to provide clean mappings; deep copies
  avoid mutating caller data.
- **Verification:** `tests/application/test_merge.py` exercises precedence,
  associativity, idempotence, and “last layer wins” behaviour with Hypothesis
  property tests.

---

## Composition Root

### Module: `lib_layered_config/core.py`
- **Purpose:** Orchestrate adapter wiring, layer discovery, merge policy, and
  provenance emission to deliver the high-level `read_config` API.
- **Responsibilities:**
  - Instantiate path resolver, structured file loaders, dotenv loader, and
    environment loader.
  - Gather layers in documented order (`app → host → user → dotenv → env`).
  - Merge payloads via `application.merge.merge_layers` and wrap the result in a
    `Config` value object.
  - Emit structured log events via `observability.log_*` helpers.
- **Dependencies:** Adapters, merge policy, observability, domain config.
- **Public API:** `read_config`, `read_config_raw`, `LayerLoadError` exception.
- **Error Handling:** Wraps adapter failures in `LayerLoadError`; skips files
  with unsupported suffixes by design.
- **Verification:** `tests/e2e/test_read_config.py` covers precedence and
  provenance; `tests/e2e/test_cli.py` exercises the same flows via the CLI.

---

## Adapter Layer

### Module: `lib_layered_config/adapters/path_resolvers/default.py`
- **Purpose:** Discover configuration files and directories across Linux,
  macOS, and Windows using environment overrides and documented defaults.
- **Responsibilities:**
  - Compute app, host, user, and dotenv candidates via `_linux_paths`,
    `_mac_paths`, `_windows_paths`, and `_project_dotenv_paths`.
  - Normalise file ordering (e.g., `config.d` directories) with `_collect_layer`.
- **Dependencies:** `pathlib.Path`, `os`, `sys`, `socket`, observability logger.
- **Public API:** `DefaultPathResolver` class.
- **Error Handling:** Non-existent paths are simply omitted; observable via
  `log_debug` events.
- **Verification:** `tests/adapters/test_path_resolver.py` covers platform
  permutations, dotenv discovery, and hostname-specific paths.

### Module: `lib_layered_config/adapters/file_loaders/structured.py`
- **Purpose:** Parse TOML, JSON, and YAML configuration files with consistent
  error handling and observability.
- **Responsibilities:**
  - `BaseFileLoader` handles file I/O, mapping validation, and log emission.
  - Format-specific loaders (`TOMLFileLoader`, `JSONFileLoader`, `YAMLFileLoader`)
    parse content and raise `InvalidFormat` on error.
- **Dependencies:** `tomllib`, `json`, optional `yaml`, domain errors,
  observability.
- **Public API:** `BaseFileLoader` (internal), concrete loader classes.
- **Error Handling:** Raises `NotFound` for missing files, `InvalidFormat` for
  parse errors, and logs structured events for telemetry.
- **Verification:** `tests/adapters/test_file_loaders.py` covers success and
  failure scenarios; also invoked indirectly via `tests/e2e/test_cli.py`.

### Module: `lib_layered_config/adapters/dotenv/default.py`
- **Purpose:** Locate and parse `.env` files while mirroring environment
  nesting semantics.
- **Responsibilities:**
  - Build search lists using resolver hints and upward directory walks.
  - Parse key/value pairs, ignoring shell-style comments.
  - Reuse `assign_nested` semantics shared with the environment loader.
- **Dependencies:** `pathlib.Path`, `os`, domain errors, observability.
- **Public API:** `DefaultDotEnvLoader` (`load`, `last_loaded_path`).
- **Error Handling:** Raises `InvalidFormat` with contextual information; emits
  structured logs for discovery success and failure.
- **Verification:** `tests/adapters/test_dotenv_loader.py` validates nested
  parsing, missing files, and metadata exposure.

### Module: `lib_layered_config/adapters/env/default.py`
- **Purpose:** Translate namespaced environment variables into nested mappings
  that align with file-based configuration layers, performing primitive coercion.
- **Responsibilities:**
  - `default_env_prefix` normalises slugs to uppercase prefixes.
  - `_iter_namespace_entries` filters the namespace and strips prefixes.
  - `assign_nested` plus helper functions manage case-insensitive keys and type
    coercion (bool, null, int, float).
- **Dependencies:** `os`, standard library collections, observability.
- **Public API:** `DefaultEnvLoader`, `default_env_prefix`, `assign_nested`.
- **Error Handling:** Raises `ValueError` when attempting to convert an existing
  scalar to a mapping (protecting data integrity).
- **Verification:** `tests/adapters/test_env_loader.py` covers coercion, nested
  assignment, and property-based randomised namespaces; contract adherence is
  asserted in `tests/adapters/test_port_contracts.py`.

---

## Presentation & Tooling

### Module: `lib_layered_config/cli.py`
- **Purpose:** Provide a Rich Click CLI that mirrors the library’s configuration
  workflows for operators and documentation.
- **Responsibilities:**
  - Define the top-level command group (`lib_layered_config`) with subcommands
    `read`, `deploy`, `generate-examples`, `env-prefix`, `info`, and `fail`.
  - Integrate with `lib_cli_exit_tools` for consistent exit handling and optional
    tracebacks.
  - Format JSON output (config and provenance) and return deployment/generation
    results as JSON arrays for scriptability.
- **Dependencies:** `rich_click`, `json`, `pathlib.Path`, `lib_cli_exit_tools`,
  core APIs, examples, observability.
- **Public API:** CLI command group (`cli`), entry point helper `main`.
- **Error Handling:** Uses `lib_cli_exit_tools` to render tracebacks when
  requested; propagates `ConfigError` subclasses for caller handling.
- **Verification:** `tests/e2e/test_cli.py` exercises all subcommands,
  provenance output, deployment overwrites, metadata fallbacks, and intentional
  failure paths.

### Module: `lib_layered_config/__main__.py`
- **Purpose:** Support `python -m lib_layered_config` by delegating to the CLI
  entry point.
- **Responsibilities:** Import `lib_layered_config.cli.main` and exit with its
  return code.
- **Dependencies:** CLI module only.
- **Verification:** Implicit via CLI end-to-end tests.

### Module: `lib_layered_config/observability.py`
- **Purpose:** Offer structured logging primitives with trace propagation so
  adapters emit consistent diagnostics.
- **Responsibilities:**
  - Manage a shared logger with a `NullHandler`.
  - Maintain a `TRACE_ID` context variable and provide `bind_trace_id`.
  - Provide `log_debug`, `log_info`, `log_error`, and `make_event` helpers.
- **Dependencies:** Python `logging`, `contextvars`.
- **Public API:** Logger helpers and trace binding utilities.
- **Verification:** `tests/unit/test_observability.py` ensures handler presence,
  trace propagation, and event construction; CLI/adapters rely on these helpers
  indirectly.

### Module: `lib_layered_config/testing.py`
- **Purpose:** Provide a deterministic failure helper used by the CLI (`fail`
  command) and test suites.
- **Responsibilities:** Define `FAILURE_MESSAGE` and `i_should_fail()` that
  raises `RuntimeError(FAILURE_MESSAGE)`.
- **Verification:** `tests/unit/test_testing.py` confirms exception semantics and
  public re-export.

---

## Examples & Documentation Helpers

### Module: `lib_layered_config/examples/generate.py`
- **Purpose:** Emit example configuration trees for documentation, tutorials,
  and onboarding across supported platforms.
- **Responsibilities:**
  - Build `ExampleSpec` objects per platform using `_build_specs`.
  - Write files to disk via `_write_examples`, `_write_spec`, `_should_write`,
    and `_ensure_parent` while respecting the `force` flag.
- **Dependencies:** `pathlib`, `os`, logging via observability.
- **Public API:** `generate_examples`, `ExampleSpec`, `DEFAULT_HOST_PLACEHOLDER`.
- **Verification:** `tests/unit/test_examples.py` exercises idempotence, force
  rewrites, and platform-specific layouts.

### Module: `lib_layered_config/examples/deploy.py`
- **Purpose:** Copy an existing configuration file into the canonical layer
  directories (app, host, user) discovered by the path resolver.
- **Responsibilities:**
  - Instantiate a path resolver via `_prepare_resolver`.
  - Compute destination paths with `_destinations_for` and conditionally copy
    via `_should_copy` and `_copy_payload`.
  - Honour the `force` flag to control overwrites and skip existing files.
- **Dependencies:** `pathlib`, environment variables for overrides, adapters.
- **Public API:** `deploy_config`.
- **Verification:** `tests/examples/test_deploy.py` covers deployments across
  targets, skip/force semantics, invalid inputs, and Windows-specific paths.

### Module: `lib_layered_config/examples/__init__.py`
- **Purpose:** Present a single namespace for example helpers consumed by
  documentation and notebooks.
- **Public API:** Re-exports `deploy_config`, `generate_examples`,
  `ExampleSpec`, `DEFAULT_HOST_PLACEHOLDER`.
- **Verification:** Covered indirectly by the example tests above.

---

## Support & Fixtures

### Module: `tests/support/layered.py`
- **Purpose:** Provide shared test fixtures (`LayeredSandbox`) for cross-platform
  filesystem scaffolding so tests can focus on behavioural assertions.
- **Responsibilities:**
  - `LayeredSandbox` dataclass stores vendor/app/slug context, computed roots,
    environment overrides, and a starting directory.
  - Methods `write` and `apply_env` create files and register environment
    variables consistently across tests.
  - `create_layered_sandbox` factory builds a sandbox for the current or
    specified platform.
- **Verification:** Doctests within the module plus usage across
  `tests/e2e/test_cli.py`, `tests/e2e/test_read_config.py`, and
  `tests/examples/test_deploy.py`.

---

## Composition Summary

- **High-Level API:** `lib_layered_config.read_config`, `read_config_raw`, and
  `Config` deliver immutable configuration with provenance.
- **Adapters:** Cross-platform filesystem discovery, structured parsing, dotenv
  loading, and environment ingestion are implemented in dedicated modules and
  validated by port contract tests.
- **Presentation:** The Rich Click CLI, examples tooling, and logging helpers
  enable operators and documentation to exercise the same code paths as library
  consumers.
- **Testing:** `tests/support` utilities, property-based tests, e2e suites, and
  doctests keep contracts verifiable. Refer to `docs/systemdesign/test_matrix.md`
  for a cross-reference of suites to modules.

Keeping this reference current ensures engineers can quickly assess the impact of
changes, identify missing tests, and confirm adherence to the architecture.
