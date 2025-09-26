# Module Reference

This catalogue links each module in `lib_layered_config` to the Clean Architecture
concepts described for the library. Every entry follows the documentation
blueprint in `systemprompts/self_documenting_template.md` so that engineers and
technical writers have a uniform, actionable summary of responsibilities,
contracts, and testing hooks.

---

## Module: lib_layered_config/__init__.py

### Status
Complete

### Links & References
**Feature Requirements:** Exposes curated public API for layered configuration.
**Task/Ticket:** N/A (core package contract)
**Pull Requests:** Historical consolidation in initial release.
**Related Files:**
- `src/lib_layered_config/core.py`
- `src/lib_layered_config/observability.py`

### Problem Statement
Provide a minimal, intentionally curated surface so consumers can import the
library without learning its internal layering. The package needs to expose the
value object, read helpers, error taxonomy, and observability bindings while
keeping other modules private.

### Solution Overview
- Re-export only the stable entry points (`read_config`, `Config`, errors,
  logging helpers).
- Align exported names with README examples and system design diagrams.
- Guard future expansion: new features must be deliberately added here after
  design review.

### Architecture Integration
**App Layer Fit:** Public facade bridging consumers to the composition root.
**Data Flow:** Imports from core/observability and re-exports to callers; no
runtime logic besides `__all__` curation.
**System Dependencies:** Purely depends on internal modules; no external APIs.

### Core Components
- **Public Symbols:** `Config`, `read_config`, `read_config_raw`, error classes,
  `default_env_prefix`, `bind_trace_id`, `get_logger`.

### Implementation Details
**Dependencies:** Internal modules only.
**Key Configuration:** None; module executes at import time only.
**Database Changes:** N/A.
**Error Handling Strategy:** Delegated to imported modules.

### Testing Approach
**Manual Testing Steps:** Import the package and ensure expected symbols exist.
**Automated Tests:** Covered implicitly by end-to-end tests under `tests/`.
**Edge Cases:** Backwards compatibility when new exports are added.

### Known Issues & Future Improvements
**Current Limitations:** Lacks explicit deprecation helpers; rely on changelog.
**Future Enhancements:** Consider exporting convenience tracing context manager.

### Risks & Considerations
**Technical Risks:** Expanding the surface accidentally without documentation.
**User Impact:** Any change here is public API churn.

### Documentation & Resources
**Internal References:** `README.md`, this module reference.
**External References:** Clean Architecture guidelines (internal only).

---

## Module: lib_layered_config/core.py

### Status
Complete

### Links & References
**Feature Requirements:** Composition root orchestrating adapters and precedence.
**Task/Ticket:** Initial design ADR (see `concept.md`).
**Pull Requests:** Core wiring PRs in early history.
**Related Files:**
- `src/lib_layered_config/adapters/*`
- `src/lib_layered_config/application/merge.py`
- `src/lib_layered_config/domain/config.py`

### Problem Statement
Consumers need a deterministic way to read layered configuration from multiple
sources while preserving precedence, provenance, and observability. The
composition root must coordinate adapters without leaking implementation
concerns to callers.

### Solution Overview
- Instantiate path resolver, dotenv loader, env loader, and file loaders.
- `_gather_layers` orchestrates layer discovery, invoking `_collect_path_layers`,
  `_dotenv_layer`, and `_env_layer` to keep precedence readable.
- Iterate layers in documented order (`app → host → user → dotenv → env`).
- Merge payloads via the application merge policy and emit observability events.
- Expose high-level (`read_config`) and low-level (`read_config_raw`) APIs.

### Architecture Integration
**App Layer Fit:** Composition root at the outer boundary of the application
layer.
**Data Flow:** Adapters supply mappings → merge policy → domain `Config`.
**System Dependencies:** Filesystem, environment variables (via adapters).

### Core Components
- **`LayerLoadError`:** Wraps adapter-specific exceptions with context.
- **`read_config`:** Facade returning immutable `Config` objects.
- **`read_config_raw`:** Returns raw merged dictionaries and provenance.
- **`_gather_layers`:** Collects path, dotenv, and environment layers.
- **`_load_files`:** Helper to load and filter per-layer config files.
- **`_order_paths`:** Stable ordering honouring user preferences.
- **`_FILE_LOADERS`:** Suffix → loader mapping (TOML/JSON/YAML).

### Implementation Details
**Dependencies:** Uses adapters (`DefaultPathResolver`, `DefaultDotEnvLoader`,
`DefaultEnvLoader`, structured file loaders) and application merge function.
**Key Configuration:** Supports `prefer` ordering hint and optional `start_dir`.
**Database Changes:** None.
**Error Handling Strategy:** Adapters raise domain errors; `LayerLoadError`
converts parsing failures into consistent signals.

### Testing Approach
**Manual Testing Steps:** Run example CLI or tests to ensure precedence order.
**Automated Tests:** `tests/test_core.py` (merging, precedence, trace logging).
**Edge Cases:** Empty layers, missing files, invalid formats.

### Known Issues & Future Improvements
**Current Limitations:** `_FILE_LOADERS` is static; user extensibility requires
wrapping `read_config_raw`.
**Future Enhancements:** Consider plugin registry for custom file formats.

### Risks & Considerations
**Technical Risks:** Silent skipping of unsupported suffixes must remain
intentional and documented.
**User Impact:** Changes to precedence order would be breaking.

### Documentation & Resources
**Internal References:** `concept.md`, README precedence matrix.
**External References:** None.

---

## Module: lib_layered_config/domain/config.py

### Status
Complete

### Links & References
**Feature Requirements:** Immutable configuration value object with provenance.
**Task/Ticket:** Domain layer specification (`concept.md`).
**Pull Requests:** Domain modelling PR.
**Related Files:**
- `src/lib_layered_config/application/merge.py`
- `tests/domain/test_config.py`

### Problem Statement
Callers require a safe, immutable representation of layered configuration that
preserves provenance and supports dotted path lookups without mutating shared
state.

### Solution Overview
- Define `SourceInfo` typed dictionary for provenance metadata.
- Implement `Config` dataclass extending `Mapping` with dotted access helpers.
- Provide deep-copy helpers to serialise to dict/JSON without mutating state.
- Offer `EMPTY_CONFIG` singleton for empty results.

### Architecture Integration
**App Layer Fit:** Domain entity consumed by outer layers.
**Data Flow:** `merge_layers` produces `(data, meta)` which instantiate `Config`.
**System Dependencies:** Standard library only.

### Core Components
- **`SourceInfo`:** Metadata for each dotted key.
- **`Config`:** Immutable mapping with dotted `get`, `origin`, `with_overrides`.
- **`_deepcopy_mapping` / `_deepcopy_value`:** Internal cloning utilities.
- **`EMPTY_CONFIG`:** Shared empty instance.

### Implementation Details
**Dependencies:** `MappingProxyType`, standard library typing/dataclasses.
**Key Configuration:** JSON serialisation helper uses utf-8 and no ASCII escape.
**Database Changes:** None.
**Error Handling Strategy:** Raises standard mapping errors; no custom errors.

### Testing Approach
**Manual Testing Steps:** Instantiate `Config` with sample data; verify
immutability.
**Automated Tests:** `tests/domain/test_config.py` ensures dotted lookups,
provenance, overrides.
**Edge Cases:** Non-existent keys, nested collections, JSON serialisation.

### Known Issues & Future Improvements
**Current Limitations:** `with_overrides` only merges top-level dictionaries.
**Future Enhancements:** Consider change logs for provenance merges.

### Risks & Considerations
**Technical Risks:** Misuse of mapping proxies could expose mutability; tests
cover this.
**User Impact:** High—`Config` is a public contract.

### Documentation & Resources
**Internal References:** README usage examples.
**External References:** Python `Mapping` protocol documentation.

---

## Module: lib_layered_config/domain/errors.py

### Status
Complete

### Links & References
**Feature Requirements:** Shared error taxonomy for all layers.
**Task/Ticket:** Initial domain design.
**Related Files:**
- `src/lib_layered_config/core.py`
- Adapter modules raising these exceptions.

### Problem Statement
Ensure all layers communicate errors using a predictable hierarchy so callers can
handle failures without inspecting adapter internals.

### Solution Overview
- Define `ConfigError` base class and typed subclasses for major failure modes.
- Keep errors in domain layer to maintain Clean Architecture dependency rule.

### Architecture Integration
**App Layer Fit:** Domain primitives used throughout adapters and core.
**Data Flow:** Exceptions are raised by adapters/core and bubble to callers.
**System Dependencies:** None.

### Core Components
- `ConfigError`, `InvalidFormat`, `ValidationError`, `NotFound`.

### Implementation Details
**Dependencies:** Standard `Exception` hierarchy.
**Key Configuration:** None.
**Error Handling Strategy:** Uniform types for parsing, validation, missing data.

### Testing Approach
**Automated Tests:** Indirect via adapter/core tests.
**Edge Cases:** Future validation rules can subclass `ValidationError`.

### Known Issues & Future Improvements
Potential expansion when semantic validation is implemented.

### Risks & Considerations
Misclassification of errors would break caller expectations.

### Documentation & Resources
Referenced in README error handling section.

---

## Module: lib_layered_config/application/ports.py

### Status
Complete

### Links & References
**Feature Requirements:** Ports describing adapter responsibilities.
**Related Files:**
- `src/lib_layered_config/adapters/*`
- `src/lib_layered_config/application/merge.py`

### Problem Statement
Adapters must implement stable contracts so the application layer can orchestrate
them without knowing platform details.

### Solution Overview
- Introduce narrow `Protocol`s for path resolution, file loading, dotenv loading,
  env loading, and merging.
- Document semantics for each method to promote consistent behaviour.

### Architecture Integration
**App Layer Fit:** Defines boundary between application and adapters.
**Data Flow:** Core invokes ports; adapters implement them.
**System Dependencies:** Typing module only.

### Core Components
Protocols: `PathResolver`, `FileLoader`, `DotEnvLoader`, `EnvLoader`, `Merger`.

### Implementation Details
**Dependencies:** `typing.Protocol` for structural typing.
**Error Handling Strategy:** Implementations raise domain errors.

### Testing Approach
**Automated Tests:** Contract coverage via adapter tests.

### Known Issues & Future Improvements
May expand with future transports; prefer new protocols over extending existing.

### Risks & Considerations
Keeping interfaces minimal ensures DIP compliance.

### Documentation & Resources
Module docstring, adapter docs.

---

## Module: lib_layered_config/application/merge.py

### Status
Complete

### Links & References
**Feature Requirements:** Deterministic merging with provenance tracking.
**Related Files:**
- `src/lib_layered_config/domain/config.py`
- `tests/application/test_merge.py`

### Problem Statement
Need a reusable merge policy that applies precedence ordering and records
metadata for provenance-aware tooling.

### Solution Overview
- `merge_layers` iterates ordered layer payloads and merges into dict/meta pairs.
- `_merge_layer` and `_merge_mapping` handle nested containers and provenance.
- Uses `deepcopy` to avoid mutating adapter-provided data structures.

### Architecture Integration
**App Layer Fit:** Application service invoked by composition root.
**Data Flow:** Layer tuples → merged mapping + provenance.
**System Dependencies:** Standard library only.

### Core Components
`merge_layers`, `_merge_layer`, `_merge_mapping`.

### Implementation Details
**Dependencies:** `deepcopy` from stdlib.
**Error Handling Strategy:** No exceptions; relies on adapter data cleanliness.

### Testing Approach
`tests/application/test_merge.py` (nested merges, precedence, provenance).

### Known Issues & Future Improvements
Large configurations may benefit from streaming merge; currently in-memory.

### Risks & Considerations
Mutable inputs could still leak without deepcopy; tests guard common cases.

### Documentation & Resources
Refer to README precedence narrative.

---

## Module: lib_layered_config/adapters/path_resolvers/default.py

### Status
Complete

### Links & References
**Feature Requirements:** OS-aware path discovery.
**Related Files:**
- `tests/adapters/test_path_resolver.py`
- `src/lib_layered_config/core.py`

### Problem Statement
`read_config` requires deterministic file discovery across Linux, macOS, and
Windows with override hooks for tests.

### Solution Overview
- Constructor captures vendor/app/slug plus optional overrides.
- `_platform_paths` dispatches to tiny per-OS helpers (`_linux_paths`,
  `_mac_paths`, `_windows_paths`).
- `_project_dotenv_paths` and `_platform_dotenv_path` narrate dotenv discovery.
- `_collect_layer` iterates canonical files and `config.d` directories.

### Architecture Integration
**App Layer Fit:** Adapter implementing `PathResolver` port.
**Data Flow:** Emits iterables of absolute paths consumed by core.
**System Dependencies:** Filesystem (`Path`), OS environment, hostname.

### Core Components
- `DefaultPathResolver`
- `_collect_layer`
- `_ALLOWED_EXTENSIONS`

### Implementation Details
**Dependencies:** `os`, `sys`, `socket`, `Path`, observability helpers.
**Key Configuration:** Env overrides (`LIB_LAYERED_CONFIG_*`).
**Error Handling Strategy:** Non-existent paths simply omitted.

### Testing Approach
`tests/adapters/test_path_resolver.py` (platform-specific expectations).

### Known Issues & Future Improvements
Monitor platform overrides as new operating systems appear; current helpers keep
branching minimal.

### Risks & Considerations
Platform detection must remain in sync with new OS variants.

### Documentation & Resources
Refer to README filesystem layout diagrams.

---

## Module: lib_layered_config/adapters/file_loaders/structured.py

### Status
Complete

### Links & References
**Feature Requirements:** Load structured files into mappings with observability.
**Related Files:**
- `tests/adapters/test_file_loaders.py`
- `src/lib_layered_config/core.py`

### Problem Statement
Need consistent file parsing for TOML, JSON, and YAML with robust error
reporting and optional dependencies.

### Solution Overview
- `BaseFileLoader` centralises file reading and mapping validation.
- `TOMLFileLoader`, `JSONFileLoader`, and `YAMLFileLoader` parse specific
  formats and emit structured logs.
- YAML support gated by PyYAML availability.

### Architecture Integration
**App Layer Fit:** Implement `FileLoader` port consumed by core `_load_files`.
**Data Flow:** File path → mapping → merge layer.
**System Dependencies:** `tomllib`/`json`/`yaml`, filesystem.

### Core Components
- `BaseFileLoader._read`
- `BaseFileLoader._ensure_mapping`
- Concrete loader classes per format.

### Implementation Details
**Error Handling Strategy:** Raise `NotFound` when missing; `InvalidFormat` on
parse failures; log structured events.

### Testing Approach
`tests/adapters/test_file_loaders.py` verifying format handling and errors.

### Known Issues & Future Improvements
Potential to add schema validation or plugin registration.

### Risks & Considerations
Ensure optional `yaml` import stays guarded to avoid import errors.

### Documentation & Resources
README format support table.

---

## Module: lib_layered_config/adapters/dotenv/default.py

### Status
Complete

### Links & References
**Feature Requirements:** `.env` discovery and parsing.
**Related Files:**
- `tests/adapters/test_dotenv.py`
- `src/lib_layered_config/core.py`

### Problem Statement
Need deterministic `.env` loading that respects precedence and matches env
nesting semantics.

### Solution Overview
- `DefaultDotEnvLoader` tracks extras provided by path resolver and caches last
  loaded path.
- `_iter_candidates` performs upward search from start dir.
- `_parse_dotenv` splits key/value pairs, validating syntax.
- Helper functions handle key resolution and nested assignment.

### Architecture Integration
**App Layer Fit:** Adapter implementing `DotEnvLoader` port.
**Data Flow:** Filesystem → mapping.
**System Dependencies:** File I/O.

### Core Components
- `DefaultDotEnvLoader`
- `_iter_candidates`
- `_parse_dotenv`
- `_assign_nested` family helpers.

### Implementation Details
**Error Handling Strategy:** Raise `InvalidFormat` with line numbers; log events.

### Testing Approach
`tests/adapters/test_dotenv.py` covering parsing, overrides, invalid lines.

### Known Issues & Future Improvements
No built-in variable substitution; deliberate omission.

### Risks & Considerations
Strict parsing rejects some 3rd-party dotenv extensions; document this.

### Documentation & Resources
README `.env` section.

---

## Module: lib_layered_config/adapters/env/default.py

### Status
Complete

### Links & References
**Feature Requirements:** Environment variable ingestion.
**Related Files:**
- `tests/adapters/test_env.py`
- `src/lib_layered_config/core.py`

### Problem Statement
Transform process environment variables into nested dictionaries consistent with
file-based layers while supporting type coercion.

### Solution Overview
- `default_env_prefix` standardises prefixes from slug.
- `DefaultEnvLoader.load` filters variables and builds nested structures.
- Helpers manage case-insensitive keys, mapping creation, and primitive coercion.

### Architecture Integration
**App Layer Fit:** Adapter implementing `EnvLoader` port.
**Data Flow:** `os.environ` → mapping.
**System Dependencies:** Environment dictionary.

### Core Components
- `default_env_prefix`
- `DefaultEnvLoader`
- `assign_nested`, `_resolve_key`, `_ensure_child_mapping`, `_coerce`

### Implementation Details
**Error Handling Strategy:** Value errors raised when nesting collides with
scalar values.

### Testing Approach
`tests/adapters/test_env.py` ensures coercion and nesting semantics.

### Known Issues & Future Improvements
No casting for complex types; evaluate future typed adapters.

### Risks & Considerations
Must avoid accidental capture of unrelated variables; prefix logic critical.

### Documentation & Resources
README environment variable guide.

---

## Module: lib_layered_config/examples/generate.py

### Status
Complete

### Links & References
**Feature Requirements:** Generate documentation-ready example configs.
**Related Files:**
- `README.md`
- `tests/examples/test_generate.py`

### Problem Statement
Documentation and onboarding need reproducible example files matching the
filesystem layout so users can bootstrap quickly.

### Solution Overview
- `ExampleSpec` dataclass describes files to generate.
- `generate_examples` writes examples to destination, allowing overwrite.
- `_build_specs` produces canonical layer files (app, host, user, dotenv).

### Architecture Integration
**App Layer Fit:** Support tooling outside main runtime; no layer coupling.
**Data Flow:** Specification → filesystem outputs.
**System Dependencies:** `Pathlib` I/O.

### Core Components
- `DEFAULT_HOST_PLACEHOLDER`
- `ExampleSpec`
- `generate_examples`
- `_build_specs`

### Implementation Details
**Error Handling Strategy:** Relies on filesystem exceptions; no silent failures.

### Testing Approach
`tests/examples/test_generate.py` ensures files are written with placeholders.

### Known Issues & Future Improvements
Currently generates TOML only; extendable to JSON/YAML variants if needed.

### Risks & Considerations
Running with `force=False` skips existing files; ensure docs mention this.

### Documentation & Resources
README quickstart instructions.

---

## Module: lib_layered_config/observability.py

### Status
Complete

### Links & References
**Feature Requirements:** Provide structured logging helpers with trace IDs.
**Related Files:**
- All adapters
- `tests/test_observability.py`

### Problem Statement
Need uniform logging primitives so adapters emit structured events with shared
trace context.

### Solution Overview
- `TRACE_ID` context variable tracks current trace identifier.
- Logging helpers wrap standard library logger, injecting context payload.
- `make_event` constructs consistent diagnostics for configuration events.

### Architecture Integration
**App Layer Fit:** Cross-cutting helper used by adapters and core.
**Data Flow:** Accepts log metadata, forwards to logging handlers.
**System Dependencies:** Python `logging`, `contextvars`.

### Core Components
- `TRACE_ID`
- `get_logger`
- `bind_trace_id`
- `log_debug` / `log_info` / `log_error`
- `make_event`

### Implementation Details
**Error Handling Strategy:** Logging operations assumed to succeed; rely on
logger handlers for failures.

### Testing Approach
`tests/test_observability.py` covers trace binding and structured payloads.

### Known Issues & Future Improvements
Potential to add structured warning logging if needed.

### Risks & Considerations
Misuse of `bind_trace_id` (forgetting to clear) can leak context; document in
README.

### Documentation & Resources
Internal README observability chapter; logging best practices.


## Module: lib_layered_config/testing.py

### Status
Complete

### Problem Statement
Expose a single deterministic failure helper so transports (CLI) and integration
tests can verify error-handling flows without bespoke fixtures.

### Solution Overview
`i_should_fail` raises `RuntimeError('i should fail')` every time it is called.

### Architecture Integration
Used by the CLI `fail` command and by tests as a predictable failure path.

### Testing Approach
`tests/unit/test_testing.py` asserts the helper raises the expected exception.

---

## Module: lib_layered_config/examples/deploy.py

### Status
Complete

### Problem Statement
Provide a utility that copies an existing configuration file into the canonical layer directories (app/host/user) without overwriting operator-managed files.

### Solution Overview
- Reuses :class:`DefaultPathResolver` context (vendor, app, slug, platform) to compute target paths.
- Supports `app`, `host`, and `user` targets; skips destinations that already exist or resolve to the source file.
- Returns the list of files created so automation can report which layers were provisioned.

### Architecture Integration
**App Layer Fit:** Outermost adapter writing configuration artifacts to the filesystem.
**Data Flow:** Source file → destination directories derived from resolver environment.
**System Dependencies:** Standard library `pathlib`, OS environment variables consumed by the path resolver.

### Core Components
- `deploy_config`: orchestrates copy operations and validates inputs.
- `_resolve_destination` helpers: mirror resolver logic for Linux, macOS, and Windows.

### Implementation Details
**Error Handling Strategy:** Raises `FileNotFoundError` when the source file is missing and `ValueError` for unsupported targets; existing files are preserved.

### Testing Approach
`tests/examples/test_deploy.py` validates deployments across app/user/host targets, skip-on-existing behaviour, and error conditions.

### Known Issues & Future Improvements
Future enhancements could include dry-run output, explicit config.d destinations, or templated filename generation.

### Risks & Considerations
Relies on environment variables matching the path resolver conventions; changes to resolver logic should be reflected here.

---

## Module: lib_layered_config/examples/__init__.py

### Status
Complete

### Links & References
**Feature Requirements:** Centralised example utilities for tutorials and docs.
**Task/Ticket:** Original example suite scaffolding.
**Pull Requests:** Initial release; subsequent refactors keep namespace flat.
**Related Files:**
- `src/lib_layered_config/examples/deploy.py`
- `src/lib_layered_config/examples/generate.py`

### Problem Statement
Expose helper functions and data structures for example projects without asking
consumers to learn the internal module layout.

### Solution Overview
- Re-export deployment and generation helpers under a single namespace.
- Document the exports so tutorials reference stable, intentional names.
- Keep glue minimal: no additional logic resides in this package surface.

### Architecture Integration
**App Layer Fit:** Presentation helper layer aimed at documentation and demos.
**Data Flow:** Pure re-exports; no data processing occurs in this module.
**System Dependencies:** Relies on sibling modules only.

### Core Components
- **`deploy_config`:** copy template files into configuration directories.
- **`ExampleSpec`:** structure describing generated example assets.
- **`DEFAULT_HOST_PLACEHOLDER`:** placeholder hostname string for templates.
- **`generate_examples`:** orchestrates example file generation.

### Implementation Details
**Dependencies:** Imports from `deploy` and `generate` modules.
**Key Configuration:** None.
**Database Changes:** N/A.
**Error Handling Strategy:** Delegated to underlying modules.

### Testing Approach
**Manual Testing Steps:** Import `lib_layered_config.examples` in REPL/notebook
and call the re-exported helpers.
**Automated Tests:** Covered via `tests/examples/test_deploy.py` and
`tests/unit/test_examples.py` which exercise the underlying modules.
**Edge Cases:** Ensure re-exports stay aligned when new helpers are added.

### Known Issues & Future Improvements
**Current Limitations:** Namespace mirrors only core helpers; additional
examples require manual re-export.
**Future Enhancements:** Consider exporting convenience builders for notebook
stories.

### Risks & Considerations
**Technical Risks:** Low—module contains no behaviour but must stay in sync with
underlying helpers.
**User Impact:** Changes to exported names affect documentation code snippets.

### Documentation & Resources
**Internal References:** README examples section; notebooks under docs.
**External References:** None.

---

## Module: lib_layered_config/cli.py

### Status
Complete

### Links & References
**Feature Requirements:** Provide a transport so operators can run `read_config` from the shell.
**Related Files:**
- `src/lib_layered_config/core.py`
- `src/lib_layered_config/observability.py`
- `tests/e2e/test_cli.py`

### Problem Statement
Without a CLI, debugging precedence issues requires writing ad-hoc Python
snippets. The tool should mirror the template repository methodology and reuse
`lib_cli_exit_tools` for shared exit handling.

### Solution Overview
- Rich Click-powered command group (`lib_layered_config` / `lib-layered-config`).
- Global `--traceback` flag integrated with `lib_cli_exit_tools` configuration.
- Subcommands: `info`, `env-prefix`, `deploy`, `generate-examples`, `read`, and `fail`.
- Helpers (`_deploy_layers`, `_generate_example_tree`, `_render_read_command`) keep command bodies tiny and declarative.
- `main()` wrapper delegates to `lib_cli_exit_tools.run_cli` to standardise exit codes.

### Architecture Integration
**App Layer Fit:** Outermost adapter invoking the composition root.
**Data Flow:** CLI arguments → `read_config` / `read_config_raw` → JSON printed to stdout.
**System Dependencies:** `rich-click`, `lib_cli_exit_tools`, standard library `json`.

### Core Components
- `cli`: root click group.
- `cli_info`: prints package metadata via `_describe_distribution()`.
- `cli_env_prefix`: exposes `default_env_prefix`.
- `cli_deploy_config` / `cli_generate_examples`: orchestration facades that rely on `_deploy_layers` and `_generate_example_tree`.
- `cli_read_config`: wraps `read_config` / `read_config_raw` with optional provenance output via `_render_read_command`.
- `main`: console entry point registering with `console_scripts`.

### Implementation Details
**Error Handling Strategy:** `lib_cli_exit_tools.print_exception_message` formats errors; traceback verbosity controlled via CLI flag.

### Testing Approach
`tests/e2e/test_cli.py` covers success path, provenance output, env-prefix helper, metadata fallback, and traceback restoration.

### Known Issues & Future Improvements
Future work may add streaming output formats or filters for large configs.

### Risks & Considerations
Ensure CLI stays thin—no direct dependencies on adapter internals beyond the composition root.

### Documentation & Resources
README CLI instructions (future enhancement) and this module reference.

---

## Module: lib_layered_config/__main__.py

### Status
Complete

### Problem Statement
Support `python -m lib_layered_config` usage by delegating to the CLI entry point.

### Solution Overview
Tiny shim that imports `lib_layered_config.cli.main` and exits with its return code.

### Architecture Integration
keeps module execution aligned with the registered console script.

### Testing Approach
Covered implicitly via CLI tests (`tests/e2e/test_cli.py`) which call `cli.main` directly.

### Risks & Considerations
None—module contains no additional logic.

---

## Module: lib_layered_config/testing.py

### Status
Complete

### Links & References
**Feature Requirements:** Deterministic diagnostics for observing failure handling.
**Task/Ticket:** Testing support utilities (historical baseline).
**Pull Requests:** Initial testing harness introduction.
**Related Files:**
- `src/lib_layered_config/cli.py`
- `tests/unit/test_testing.py`

### Problem Statement
Integration and CLI examples require a predictable way to surface runtime
failures so that tooling can assert on tracebacks, exit codes, and messaging
without wiring bespoke fixtures for every test.

### Solution Overview
- Provide a single helper that always raises a `RuntimeError` with a stable
  message.
- Export the helper via the public package facade so notebooks and CLIs can
  import identical behaviour.
- Document the failure message as a constant to prevent drift between tests and
  examples.

### Architecture Integration
**App Layer Fit:** Testing/diagnostics support module consumed by presentation
layer tooling.
**Data Flow:** No data flow; the helper simply raises an exception when invoked.
**System Dependencies:** Standard library only.

### Core Components
- **`FAILURE_MESSAGE`:** Constant containing the canonical failure text.
- **`i_should_fail`:** Function that raises `RuntimeError(FAILURE_MESSAGE)`.

### Implementation Details
**Dependencies:** Relies solely on Python's exception mechanism.
**Key Configuration:** None.
**Database Changes:** N/A.
**Error Handling Strategy:** Always raises; callers assert on the message and
traceback.

### Testing Approach
**Manual Testing Steps:** Run `lib-layered-config fail` CLI command or import the
function in a shell to observe the exception.
**Automated Tests:** `tests/unit/test_testing.py` verifies raising semantics and
public re-export.
**Edge Cases:** None; deterministic by design.

### Known Issues & Future Improvements
**Current Limitations:** Only provides one failure type; additional exception
variants may be added if future tests demand differentiation.
**Future Enhancements:** Consider helper for async failure scenarios if needed.

### Risks & Considerations
**Technical Risks:** Minimal; change to message text would break consumers
asserting on exact output.
**User Impact:** Public API contract; message text must remain stable.

### Documentation & Resources
**Internal References:** README CLI command reference, this module catalogue.
**External References:** None.

---

---

## Module: lib_layered_config/examples/generate.py

### Status
Complete

### Links & References
**Feature Requirements:** Produce filesystem scaffolding for documentation demos.
**Related Files:**
- `src/lib_layered_config/examples/__init__.py`
- `tests/unit/test_examples.py`

### Problem Statement
Documentation and onboarding flows need reproducible example configurations that
mirror the recommended directory layout across platforms.

### Solution Overview
- `generate_examples` orchestrates spec generation and writing through helper
  verbs (`_write_examples`, `_write_spec`, `_should_write`).
- `_build_specs` emits platform-specific file specifications so templates stay
  centralised.
- `_normalise_platform` maps interpreter/override values to canonical keys.

### Architecture Integration
**App Layer Fit:** Examples/Docs helper; not used at runtime by the core
library.
**Data Flow:** Creates files on disk; no in-process consumption.
**System Dependencies:** `pathlib`, `os`, standard library only.

### Core Components
- `ExampleSpec`
- `generate_examples`
- `_build_specs`

### Implementation Details
**Dependencies:** No third-party libraries.
**Key Configuration:** Platform override parameter; `force` flag for re-runs.
**Error Handling Strategy:** Best-effort; existing files skipped unless `force`
  permits overwrites.

### Testing Approach
`tests/unit/test_examples.py` validates generation across platforms and `force`
semantics.

### Known Issues & Future Improvements
Templates are static; future iterations may load examples from user-provided
manifests.

### Risks & Considerations
Overwriting files is controlled via the `force` flag; callers must opt in to
avoid accidental clobbering.

### Documentation & Resources
README example generation section; notebooks referencing `generate_examples`.


## Module: lib_layered_config/examples/deploy.py

### Status
Complete

### Links & References
**Feature Requirements:** Copy canonical config files into layered directories.
**Related Files:**
- `src/lib_layered_config/examples/generate.py`
- `tests/examples/test_deploy.py`

### Problem Statement
Operators and tutorials need a convenience function that deploys a known-good
configuration file into the same locations that the runtime resolver searches,
without clobbering existing edits.

### Solution Overview
- `deploy_config` orchestrates resolution and copy decisions using helper verbs
  (`_prepare_resolver`, `_destinations_for`, `_should_copy`, `_copy_payload`).
- Platform-specific destination lookup routes through the same logic as the
  runtime path resolver for correctness.
- `force` flag enables overwriting while skipping unchanged files.

### Architecture Integration
**App Layer Fit:** Example tooling, not part of runtime composition.
**Data Flow:** Reads a source file and copies bytes to destination locations.

### Core Components
- `deploy_config`
- `_resolve_destination` family mirroring adapter logic
- `_copy_payload`

### Implementation Details
**Dependencies:** `pathlib`, environment variables, `DefaultPathResolver`.
**Key Configuration:** `platform` override; honours resolver environment
variables.
**Error Handling Strategy:** Raises `FileNotFoundError` for missing source; skips
unknown targets.

### Testing Approach
`tests/examples/test_deploy.py` validates target resolution, force behaviour, and
platform-specific paths.

### Known Issues & Future Improvements
Current helper supports synchronous file copy only; future versions may stream
large files or add dry-run support.

### Risks & Considerations
Overwriting files is optional; callers must set `force=True` explicitly.

### Documentation & Resources
README deployment section; notebooks using `deploy_config`.

---
