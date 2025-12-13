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

### Feature Documentation: Domain Config Value Object

## Status

Complete

## Links & References

**Feature Requirements:** docs/systemdesign/concept.md
**Task/Ticket:** Internal architecture mandate – immutable configuration aggregate
**Pull Requests:** N/A (historical foundation module)
**Related Files:**

- `src/lib_layered_config/domain/config.py`
- `tests/unit/test_config.py`
- `tests/unit/test_layers_helpers.py`

---

## Problem Statement

The configuration system must expose a single immutable view of merged layers
while retaining provenance for every dotted key. Without a canonical value
object, adapters and presentation layers would each reinvent traversal,
serialisation, and origin tracking, risking inconsistency with the precedence
rules defined in docs/systemdesign.

## Solution Overview

- Implement a frozen `Config` dataclass wrapping merged data and metadata.
- Represent provenance with a typed dictionary (`SourceInfo`).
- Provide helpers (`get`, `origin`, `with_overrides`, `as_dict`, `to_json`) so
  downstream modules can safely access values without mutating the aggregate.
- Supply a module-level `EMPTY_CONFIG` to avoid repeated allocations when no
  layers produce data.

---

## Architecture Integration

**App Layer Fit:** The application merge policy (`application.merge`) produces
`LayerSnapshot`s that the composition root converts into `Config` instances
before handing them to callers and CLI commands.

**Data Flow:**
- Merge pipeline → `Config` stores merged `_data` alongside `_meta` provenance.
- Presentation/CLI → read via mapping protocol or helper methods.
- Observability → provenance metadata supports human-readable logging.

**System Dependencies:** Pure standard library (`dataclasses`, `types`,
`collections.abc`, `typing`, `json`). No external packages.

---

## Core Components

### `Config`

- **Purpose:** Immutable mapping that behaves like `Mapping[str, Any]` while
  retaining provenance.
- **Input:** Merged configuration mapping plus metadata mapping of dotted keys
  to `SourceInfo` entries.
- **Output:** Mapping interface (getitem/len/iter) and helper methods returning
  either values (`get`, `origin`) or serialised representations (`as_dict`,
  `to_json`).
- **Location:** `src/lib_layered_config/domain/config.py`

### `SourceInfo`

- **Purpose:** Capture provenance (layer, path, dotted key).
- **Input:** Emitted by merge pipeline.
- **Output:** Dict-like structure consumed by CLI and observability modules.
- **Location:** `src/lib_layered_config/domain/config.py`

### Helper Functions (`_follow_path`, `_clone_map`, `_looks_like_mapping`, etc.)

- **Purpose:** Keep traversal and cloning logic pure and testable.
- **Input:** Nested mappings or values from `_data`.
- **Output:** Safe lookups, defensive clones, and type guards to protect
  callers from accidental mutation.
- **Location:** `src/lib_layered_config/domain/config.py`

---

## Implementation Details

**Dependencies:** Standard library only.

**Key Configuration:** None; behaviour is driven entirely by inputs from the
merge pipeline.

**Database Changes:** Not applicable.

**Error Handling Strategy:**
- `KeyError` bubbles for unknown top-level keys (standard mapping semantics).
- Helpers return caller-provided defaults rather than raising when dotted paths
  fail, aligning with system design guidance.

---

## Testing Approach

**Manual Testing Steps:** Inspect CLI output (`make dev && lib_layered_config read ...`) to confirm provenance data.

**Automated Tests:**
- `tests/unit/test_config.py` – mapping protocol compliance, provenance, JSON.
- `tests/unit/test_layers_helpers.py` – helper coverage for internal traversal
  utilities.
- Property-based tests in `tests/application/test_merge.py` indirectly validate
  `Config`’s handling of merged layers.

**Edge Cases:** Empty configuration (`EMPTY_CONFIG`), dotted paths over scalars,
and cloning of nested tuples/sets.

**Test Data:** Pytest fixtures in `tests/unit/test_config.py` plus sandbox
helpers under `tests/support`.

---

## Known Issues & Future Improvements

**Current Limitations:** `with_overrides` performs only **shallow (top-level) merges**.
When overriding a nested key, the entire top-level key is replaced:

```python
cfg = Config({"db": {"host": "localhost", "port": 5432}}, {...})
cfg = cfg.with_overrides({"db": {"host": "newhost"}})
cfg["db"]  # → {"host": "newhost"}  — port is lost!
```

This is intentional, not a missing feature:

1. **Provenance tracking** — Deep merge would require updating `_meta` for every
   affected nested key, introducing complexity and potential for stale metadata.
2. **Architecture** — The domain layer avoids importing application merge logic
   to maintain Clean Architecture boundaries.
3. **Use case fit** — `with_overrides` targets CLI flags and simple runtime
   tweaks; complex nested changes belong in explicit layer files.

**Workaround:** For deep overrides, create a layer file (TOML/JSON/YAML) and let
the normal `read_config` merge pipeline handle it with full provenance tracking.

**Future Enhancements:** Optionally expose typed accessors or schema binding
once validation requirements are defined in docs/systemdesign.

---

## Risks & Considerations

**Technical Risks:** Minimal – logic is pure and covered by unit tests; risk lies
in misuse (mutating clones without understanding provenance).

**User Impact:** None; API stability is guaranteed across minor releases.

---

### Feature Documentation: Domain Error Taxonomy

## Status

Complete

## Links & References

**Feature Requirements:** docs/systemdesign/concept.md (error handling section)
**Task/Ticket:** Architecture baseline for consistent exceptions
**Related Files:**

- `src/lib_layered_config/domain/errors.py`
- `tests/unit/test_errors.py`

---

## Problem Statement

Adapters, application logic, and presentation code must communicate failure
without leaking implementation details. Without a shared taxonomy, callers
would need to inspect string messages or adapter-specific exceptions.

## Solution Overview

- Introduce `ConfigError` as the common base.
- Provide `InvalidFormatError`, `ValidationError`, and `NotFoundError` subclasses mapped
  to the scenarios described in the system design.
- Keep the module dependency-free so every layer can raise these errors without
  risk of cyclic imports.

---

## Architecture Integration

**App Layer Fit:** Application services catch `ConfigError` derivatives to
translate domain failures into user-facing errors.

**Data Flow:** Adapters raise specific subclasses (`InvalidFormatError`, `NotFoundError`),
which bubble through the merge pipeline and surface in CLI responses.

**System Dependencies:** Standard library only.

---

## Core Components

### `ConfigError`
- **Purpose:** Base class for all library-specific failures.
- **Input:** Raised directly or through subclasses.
- **Output:** Captured by higher layers to format error messages.
- **Location:** `src/lib_layered_config/domain/errors.py`

### `InvalidFormatError`, `ValidationError`, `NotFoundError`
- **Purpose:** Specialised error signals for malformed input, semantic
  validation, or missing sources.
- **Location:** `src/lib_layered_config/domain/errors.py`

---

## Implementation Details

**Dependencies:** None (beyond `Exception`).

**Key Configuration / Database Changes:** Not applicable.

**Error Handling Strategy:** Subclasses communicate intent so callers can decide
whether to fail fast (`InvalidFormatError`) or continue (`NotFoundError`).

---

## Testing Approach

**Automated Tests:** `tests/unit/test_errors.py` verifies inheritance hierarchy
and ensures the taxonomy remains stable.

**Edge Cases:** Future validation logic should reuse `ValidationError`; tests
should expand accordingly.

---

## Known Issues & Future Improvements

**Current Limitations:** `ValidationError` is currently unused; keep for forward
compatibility.

**Future Enhancements:** Once semantic validation is implemented, document the
expected error messages and calling conventions here.

---

## Risks & Considerations

**Technical Risks:** None – hierarchy is simple. Ensure subclasses remain
serialisable and do not capture large payloads in attributes.

**User Impact:** Operators experience clearer error messages and can catch
specific exceptions in automation scripts.

---

## Application Layer

### Feature Documentation: Adapter Protocols

## Status

Complete

## Links & References

**Feature Requirements:** docs/systemdesign/concept.md (Ports & Adapters)
**Related Files:**

- `src/lib_layered_config/application/ports.py`
- `tests/adapters/test_port_contracts.py`

---

## Problem Statement

Clean Architecture requires the core to depend on abstractions. Without
protocols describing adapter behaviour, accidental regressions (missing methods
or wrong return types) would surface only in production.

## Solution Overview

- Define runtime-checkable protocols for each adapter family.
- Standardise provenance payload shape via `SourceInfoPayload`.
- Use `runtime_checkable` and explicit tests to enforce compliance.

---

## Architecture Integration

**App Layer Fit:** Composition root consumes protocols; adapters implement them.

**System Dependencies:** Standard library typing only.

---

## Core Components

### `SourceInfoPayload`
- **Purpose:** Shared provenance record.
- **Location:** `application/ports.py`

### Protocols (`PathResolver`, `FileLoader`, `DotEnvLoader`, `EnvLoader`, `Merger`)
- **Purpose:** Contract definitions for adapters and merge policy wrappers.
- **Methods:** Documented inline; mirror precedence rules.
- **Location:** `application/ports.py`

---

## Testing Approach

- `tests/adapters/test_port_contracts.py` uses `isinstance` to ensure default
  adapters satisfy each protocol; extend tests when new adapters appear.

---

## Known Issues & Future Improvements

- Update protocols and tests when new adapter behaviours are required (e.g.,
  async loading, caching hints).

---

### Feature Documentation: Merge Policy

## Status

Complete

## Links & References

**Feature Requirements:** docs/systemdesign/concept.md (Layer precedence)
**Related Files:**

- `src/lib_layered_config/application/merge.py`
- `tests/application/test_merge.py`
- `tests/unit/test_layers_helpers.py`

---

## Problem Statement

Multiple configuration sources must merge deterministically, respecting the
documented precedence, without mutating inputs and while retaining provenance
for each dotted key.

## Solution Overview

- Represent each layer via `LayerSnapshot`.
- Implement `merge_layers` to fold snapshots into data/provenance pairs.
- Use helper functions to manage recursion, overwrite semantics, and dotted key
  generation.

---

## Architecture Integration

**App Layer Fit:** Composition root converts adapter output into snapshots and
delegates merging to this module.

**Data Flow:** Layer iterator → `_weave_layer` → `_descend` → `_store_branch`/
`_store_scalar` → provenance updated per scalar.

**System Dependencies:** Standard library (`collections.abc`, `dataclasses`,
`copy`).

---

## Core Components

### `LayerSnapshot`
- **Purpose:** Immutable descriptor (name, payload, origin).
- **Location:** `application/merge.py`

### `merge_layers`
- **Purpose:** Perform precedence-aware merge.
- **Input:** Iterable of snapshots ordered lowest→highest precedence.
- **Output:** Tuple `(data, provenance)` for domain `Config`.
- **Location:** `application/merge.py`

### Helper Functions
- **Purpose:** Keep recursion pure (`_weave_layer`, `_descend`, `_store_branch`,
  `_store_scalar`, `_ensure_branch`, `_clear_branch_if_empty`, `_join_segments`,
  `_looks_like_mapping`).

---

## Implementation Details

**Error Handling:**
- Clones payloads to avoid mutating adapter data.
- Removing empty branches from provenance prevents stale metadata after scalar
  overrides.

---

## Testing Approach

- `tests/application/test_merge.py` (property-based) and
  `tests/unit/test_layers_helpers.py` validate precedence, idempotence, and
  helper behaviour.

---

## Known Issues & Future Improvements

- Future schema validation may constrain payload types.
- Monitor performance when dealing with very large configuration trees.

---

## Composition Root

### Feature Documentation: Core Composition Module

## Status

Complete

## Links & References

**Feature Requirements:** docs/systemdesign/concept.md (Layer orchestration)
**Related Files:**

- `src/lib_layered_config/core.py`
- `src/lib_layered_config/_layers.py`
- `tests/e2e/test_read_config.py`
- `tests/e2e/test_cli.py`

---

## Problem Statement

Expose a stable API that discovers configuration layers, merges them with
provenance, and returns either Python objects or JSON without leaking adapter
details to callers.

## Solution Overview

- ``read_config``: returns the domain ``Config`` aggregate.
- ``read_config_json``: serialises config + provenance for tooling.
- ``read_config_raw``: provides raw dictionaries for advanced automation.
- Wrap adapter failures in ``LayerLoadError`` to keep error handling uniform.

---

## Architecture Integration

**Layer Fit:** Composition root consumes adapter protocols, calls
``_layers.collect_layers``, and hands results to ``application.merge``.

**System Dependencies:** Adapters, merge policy, observability, domain config.

---

## Core Components

### `read_config`
- **Purpose:** Return immutable configuration object.
- **Location:** `core.py`

### `read_config_json`
- **Purpose:** Return JSON payload for CLI/automation.
- **Location:** `core.py`

### `read_config_raw`
- **Purpose:** Expose raw dictionaries, used by CLI helpers and tests.
- **Location:** `core.py`

### `LayerLoadError`
- **Purpose:** Single exception type for adapter failures.

---

## Implementation Details

**Error Handling:** ``LayerLoadError`` wraps ``InvalidFormatError`` exceptions.
``_compose_config`` returns ``EMPTY_CONFIG`` when no data exists.

**Observability:** Resets trace IDs before collecting layers; actual logging is
handled inside `_layers` and adapters.

---

## Testing Approach

- `tests/e2e/test_read_config.py` and `tests/e2e/test_cli.py` cover precedence,
  provenance, CLI formatting, and error propagation.

---

## Known Issues & Future Improvements

- Consider adding structured metrics (timings, file counts) if future telemetry
  requirements demand them.

---

### Feature Documentation: Layer Assembly Helpers

## Status

Complete

## Links & References

**Feature Requirements:** docs/systemdesign/concept.md (Layer precedence)
**Related Files:**

- `src/lib_layered_config/_layers.py`
- `tests/unit/test_layers_helpers.py`
- `tests/application/test_merge.py`

---

## Problem Statement

Before merging, the system must gather defaults, filesystem entries, dotenv
values, and environment variables in the correct order without duplicating
logic inside the composition root.

## Solution Overview

- ``collect_layers`` orchestrates adapters and returns ``LayerSnapshot``
  instances in precedence order.
- ``merge_or_empty`` combines snapshots (via ``merge_layers``) whilst emitting
  observability events.
- Private helpers load defaults, filesystem files, dotenv data, and environment
  variables.

---

## Architecture Integration

**Layer Fit:** Called only from ``core.read_config_raw``.

**System Dependencies:** Path resolver, file loaders, dotenv loader, env loader,
merge policy, observability.

---

## Core Components

### `collect_layers`
- **Purpose:** Assemble a list of ``LayerSnapshot`` instances.

### `merge_or_empty`
- **Purpose:** Merge snapshots or return empty dictionaries when nothing is
  discovered.

### Helper Generators
- **Purpose:** Yield defaults, filesystem, dotenv, and env layers with logging.

---

## Implementation Details

**Error Handling:** Unsupported file extensions are skipped; loaders raising
``InvalidFormatError`` propagate so ``LayerLoadError`` can wrap them.

**Observability:** Emits ``layer_loaded`` / ``configuration_empty`` events via
`observability.log_*` helpers.

---

## Testing Approach

- `tests/unit/test_layers_helpers.py` covers sorted ordering, helper branches,
  and provenance events.
- `tests/adapters/test_*` suites indirectly exercise the generators.

---

## Known Issues & Future Improvements

- Monitor performance when there are many files per layer; consider streaming
  snapshots instead of materialising lists if necessary.

---

## Adapter Layer

### Feature Documentation: Path Resolver Adapter

## Status

Complete

## Links & References

**Feature Requirements:** docs/systemdesign/concept.md (Filesystem discovery)
**Related Files:**

- `src/lib_layered_config/adapters/path_resolvers/default.py`
- `tests/adapters/test_path_resolver.py`

---

## Problem Statement

Each operating system stores configuration files differently. The system needs
a single adapter that resolves app/host/user/dotenv paths according to the
documented precedence while honouring environment overrides for testability and
portable installations.

## Solution Overview

- Implement `DefaultPathResolver` covering Linux, macOS, and Windows layouts.
- Provide helpers for `.env` discovery and `config.d` directory expansion.
- Emit structured logging so missing files are observable.

---

## Architecture Integration

**App Layer Fit:** Implements `application.ports.PathResolver`; invoked by the
composition root before merging layers.

**System Dependencies:** `pathlib`, `os`, `sys`, `socket`, observability.

---

## Core Components

### `DefaultPathResolver`
- **Purpose:** Expose `app`, `host`, `user`, and `dotenv` iterables.
- **Input:** Vendor/app/slug identifiers, optional overrides (cwd/env/platform).
- **Output:** Ordered lists of candidate file paths.

### Helpers (`_linux_paths`, `_mac_paths`, `_windows_paths`, `_project_dotenv_paths`, `_collect_layer`)
- **Purpose:** Encapsulate platform-specific logic and ensure deterministic ordering.

---

## Implementation Details

**Error Handling:** Missing files are skipped silently; observability captures
counts via `log_debug` events.

---

## Testing Approach

- `tests/adapters/test_path_resolver.py` exercises each platform branch,
  hostname overrides, dotenv discovery, and fallback logic.

---

## Known Issues & Future Improvements

- Monitor platform-specific environment variables; update helper overrides if
  future OS versions change default directories.

---

### Feature Documentation: Dot-D Directory Expansion

## Status

Complete

## Links & References

**Feature Requirements:** docs/systemdesign/concept.md (.d directory pattern)
**Related Files:**

- `src/lib_layered_config/adapters/file_loaders/_dot_d.py`
- `src/lib_layered_config/_layers.py`
- `tests/adapters/test_dot_d.py`
- `tests/e2e/test_dot_d_integration.py`

---

## Problem Statement

Configuration files often need to be extended by additional snippets without
modifying the original file. The `.d` directory pattern (inspired by `/etc/apt/sources.list.d/`)
allows operators and package managers to drop configuration fragments into a
companion directory that are automatically merged with the base file.

## Solution Overview

- Implement `expand_dot_d()` to expand any config file path into an ordered list
  of paths including the base file and companion `.d` directory entries.
- Naming convention: `config.toml` → `config.d/` (not `config.toml.d/`), allowing
  mixed formats (TOML, YAML, JSON) in the same `.d` directory.
- Both the base file and `.d` directory are optional (either can exist independently).
- Files in the `.d` directory are sorted lexicographically (e.g., `10-db.toml`,
  `20-cache.toml`) for deterministic ordering.
- Integration with `_layers.py` ensures provenance tracks individual `.d` files.

---

## Architecture Integration

**App Layer Fit:** The expansion is performed at the `_layers._load_entry_with_dot_d()`
level, ensuring all configuration file paths (defaults, app, host, user) benefit
from `.d` expansion without modifying path resolvers.

**Data Flow:**
- Path resolver yields `config.toml` paths
- `_load_entry_with_dot_d()` calls `expand_dot_d()` to get ordered file list
- Each file is loaded via `_load_entry()` and yields separate `LayerSnapshot`s
- Merge pipeline combines them in order, tracking provenance per file

**System Dependencies:** Standard library only (`pathlib`).

---

## Core Components

### `expand_dot_d`
- **Purpose:** Expand a config file path to include `.d` directory entries.
- **Input:** Absolute path to a configuration file.
- **Output:** Iterator yielding paths in merge order (base file first, then `.d` files).
- **Location:** `adapters/file_loaders/_dot_d.py`

### `_collect_dot_d_files`
- **Purpose:** Helper to yield files from a `.d` directory in lexicographical order.
- **Input:** Path to the `.d` directory.
- **Output:** Iterator yielding absolute paths to supported config files.
- **Location:** `adapters/file_loaders/_dot_d.py`

### `_load_entry_with_dot_d`
- **Purpose:** Load a config file and any companion `.d` files as snapshots.
- **Input:** Layer name and base file path.
- **Output:** Iterator of `LayerSnapshot` instances.
- **Location:** `_layers.py`

---

## Implementation Details

**Naming Convention:** The `.d` directory name is derived by replacing the file
extension with `.d`:
- `config.toml` → `config.d/`
- `config.yaml` → `config.d/`
- `config.json` → `config.d/`

This allows all formats to share the same companion directory and enables mixed
format files within a single `.d` directory.

**File Filtering:** Only files with extensions `.toml`, `.yaml`, `.yml`, or `.json`
are included. Non-config files (e.g., `README.md`) are silently ignored.

**Subdirectory Handling:** Subdirectories inside `.d` are not traversed (flat
structure only).

**Error Handling:** Missing files and directories are handled gracefully; the
function yields nothing if neither base file nor `.d` directory exists.

**Observability:** The `_note_dot_d_expanded()` helper logs when `.d` expansion
occurs with the count of additional files.

---

## Testing Approach

**Unit Tests (`tests/adapters/test_dot_d.py`):**
- `test_expand_dot_d_returns_base_only_when_no_dot_d_dir`
- `test_expand_dot_d_returns_empty_when_neither_exists`
- `test_expand_dot_d_returns_dot_d_only_when_base_missing`
- `test_expand_dot_d_merges_base_and_dot_d_in_order`
- `test_expand_dot_d_sorts_lexicographically`
- `test_expand_dot_d_filters_unsupported_extensions`
- `test_expand_dot_d_handles_mixed_formats_in_dot_d`
- `test_expand_dot_d_ignores_subdirectories`

**E2E Tests (`tests/e2e/test_dot_d_integration.py`):**
- `test_read_config_merges_dot_d_directory`
- `test_read_config_dot_d_override_precedence`
- `test_read_config_dot_d_provenance_tracks_individual_files`
- `test_read_config_dot_d_works_for_default_file`
- `test_read_config_dot_d_user_layer_overrides_app_layer`
- `test_read_config_dot_d_mixed_formats`

---

## Deployment Integration

The `.d` directory pattern is also supported during deployment via `deploy_config()`.

**Key Difference from Reading:**
- **Reading**: Only config files (`.toml`, `.yaml`, `.yml`, `.json`) are parsed
- **Deployment**: ALL files are copied (including README.md, notes.txt, etc.)

This preserves documentation and supporting files alongside config fragments.

**Implementation:**
- `examples/deploy.py`: `_collect_dot_d_sources()` collects all files (no extension filter)
- `cli/deploy.py`: `_format_results()` includes `.d` results in JSON output

**JSON Output Fields:**
- `dot_d_created`: Paths of `.d` files created
- `dot_d_overwritten`: Paths of `.d` files overwritten
- `dot_d_skipped`: Paths of `.d` files skipped (identical content)
- `dot_d_backups`: Backup paths for overwritten `.d` files

**Tests:**
- `tests/e2e/test_deploy_behavior.py`:
  - `test_deploy_with_dot_d_directory_copies_both_base_and_dot_d_files`
  - `test_deploy_dot_d_force_mode_creates_backups`
  - `test_deploy_dot_d_smart_skip_identical_content`
  - `test_deploy_dot_d_includes_non_config_files`
  - `test_deploy_dot_d_mixed_formats`

---

## Known Issues & Future Improvements

**Current Limitations:** None identified.

**Future Enhancements:** Consider adding support for include directives within
config files if more complex composition patterns are required.

---

### Feature Documentation: Structured File Loaders

## Status

Complete

## Links & References

**Feature Requirements:** docs/systemdesign/concept.md (Structured file parsing)
**Related Files:**

- `src/lib_layered_config/adapters/file_loaders/structured.py`
- `tests/adapters/test_file_loaders.py`

---

## Problem Statement

Configuration files may be provided in TOML, JSON, or YAML. The system must
parse them consistently, emit observability events, and raise precise errors
without coupling core logic to parser implementations.

## Solution Overview

- `BaseFileLoader` handles file I/O, immutable validation, and logging.
- Concrete loaders (`TOMLFileLoader`, `JSONFileLoader`, `YAMLFileLoader`) use
  parser-specific libraries and delegate validation to the base class.

---

## Architecture Integration

**App Layer Fit:** Instances of these loaders implement the `FileLoader`
protocol and feed layer snapshots before merging.

**System Dependencies:** `tomllib` (stdlib 3.11+) or `tomli` (fallback for 3.10), `json`, optional `yaml`, domain errors,
observability helpers.

---

## Core Components

### `BaseFileLoader`
- **Purpose:** Shared read/validate/log behaviour.
- **Methods:** `_read`, `_ensure_mapping`, plus log helpers.

### Format Loaders
- **Purpose:** Parse TOML/JSON/YAML into mappings.
- **Location:** `structured.py`
- **Supporting Helpers:** `_ensure_yaml_available`, `_require_yaml_module`,
  `_parse_yaml_bytes` lazily import PyYAML, explain missing dependencies, and
  wrap parser errors with domain-specific context.

---

## Implementation Details

**Error Handling:**
- Raises `NotFoundError` for missing files.
- Raises `InvalidFormatError` for parse failures with format-specific context.
- Emits `config_file_read` / `config_file_loaded` events.
- YAML parsing uses `_parse_yaml_bytes` to normalise `None` payloads to empty
  mappings and translate `YAMLError` into actionable `InvalidFormatError`.

---

## Testing Approach

- `tests/adapters/test_file_loaders.py` covers success and error branches; CLI
  integration tests exercise loaders end-to-end.

---

## Known Issues & Future Improvements

- YAML support depends on optional dependency; monitor installation guidance in
`README` if defaults change.

---

### Feature Documentation: Dotenv Loader

## Status

Complete

## Links & References

**Feature Requirements:** docs/systemdesign/concept.md (`.env` precedence)
**Related Files:**

- `src/lib_layered_config/adapters/dotenv/default.py`
- `tests/adapters/test_dotenv_loader.py`

---

## Problem Statement

Developers use `.env` files for local overrides and secrets. The adapter must
discover candidate files (project upwards plus platform extras), parse key/value
pairs strictly, and integrate with the merge provenance system.

## Solution Overview

- `DefaultDotEnvLoader` searches for files, parses the first hit, and records
  the loaded path.
- Shared helpers ensure nested structure and case handling match the environment
  adapter.
- Structured logging communicates success, absence, or parse errors.

---

## Architecture Integration

**App Layer Fit:** Implements the `DotEnvLoader` protocol; invoked after
filesystem layers but before environment variables.

**System Dependencies:** `pathlib`, `os`, domain errors, observability.

---

## Core Components

### `DefaultDotEnvLoader`
- **Purpose:** Main adapter exposing `.load` and `last_loaded_path`.
- **Location:** `adapters/dotenv/default.py`

### Helpers (`_build_search_list`, `_iter_candidates`, `_parse_dotenv`, `_assign_nested`, `_resolve_key` …)
- **Purpose:** Keep parsing strict, maintain nested structure, and share logic
  with the environment loader.

---

## Implementation Details

**Error Handling:**
- Raises `InvalidFormatError` with line numbers on malformed entries.
- Logs missing files via `dotenv_not_found` events.

---

## Testing Approach

- `tests/adapters/test_dotenv_loader.py` covers discovery, parsing, error
  handling, and randomised namespacing.

---

## Known Issues & Future Improvements

- Currently loads only the first discovered file; future enhancements could
  support layered dotenv merges if requirements emerge.

---

### Feature Documentation: Environment Loader

## Status

Complete

## Links & References

**Feature Requirements:** docs/systemdesign/concept.md (Environment precedence)
**Related Files:**

- `src/lib_layered_config/adapters/env/default.py`
- `tests/adapters/test_env_loader.py`

---

## Problem Statement

The final precedence layer must ingest prefixed environment variables, coerce
primitive types, and maintain nested structure consistent with `.env` files.

## Solution Overview

- `default_env_prefix` standardises prefixes.
- `DefaultEnvLoader` filters, coerces, nests, and logs keys for diagnostics.
- Shared helpers resolve casing conflicts and guard against scalar collisions.

---

## Architecture Integration

**App Layer Fit:** Implements the `EnvLoader` protocol; invoked last during
layer assembly.

**System Dependencies:** `os`, observability.

---

## Core Components

### `DefaultEnvLoader`
- **Purpose:** Load prefixed variables into nested dictionaries.
- **Location:** `adapters/env/default.py`

### Helpers (`assign_nested`, `_normalize_prefix`, `_iter_namespace_entries`, `_coerce`, `_resolve_key` …)
- **Purpose:** Shared tooling ensuring consistent behaviour with dotenv parsing.

---

## Implementation Details

**Error Handling:**
- `assign_nested` raises `ValueError` when a scalar blocks further nesting.
- Logs loaded keys via `env_variables_loaded` events.

---

## Testing Approach

- `tests/adapters/test_env_loader.py` and property tests validate coercion,
  nesting, and error handling; protocol adherence checked in
  `tests/adapters/test_port_contracts.py`.

---

## Known Issues & Future Improvements

- Coercion currently supports bool/int/float/null; broaden if new types appear
  in docs/systemdesign requirements.

---

## Presentation & Tooling

### Feature Documentation: CLI Transport

## Status

Complete

## Links & References

**Feature Requirements:** docs/systemdesign/concept.md (CLI tooling)
**Related Files:**

- `src/lib_layered_config/cli.py`
- `tests/e2e/test_cli.py`

---

## Problem Statement

Provide a user-facing interface for reading configuration, deploying files,
generating examples, and surfacing metadata without exposing internal APIs.

## Solution Overview

- Rich Click command group with subcommands `read`, `read-json`, `deploy`,
  `generate-examples`, `env-prefix`, `info`, and `fail`.
- Metadata surfaces (`info`, `--version`) read directly from
  `lib_layered_config.__init__conf__` so automation keeps CLI output in sync
  with `pyproject.toml` without hitting `importlib.metadata` at runtime.
- Traceback handling delegates to `lib_cli_exit_tools.cli_session`, which
  applies the `--traceback` preference via configuration overrides and restores
  prior settings after each invocation.
- Helpers to normalise options, render human output, and manage traceback
  preferences.
- Integrates with ``lib_cli_exit_tools`` for consistent error messaging.

---

## Architecture Integration

**Layer Fit:** Presentation boundary depending on composition root and examples
modules.

**System Dependencies:** `rich_click`, `lib_cli_exit_tools`, core APIs, example
helpers.

---

## Core Components

### `cli`
- **Purpose:** Root Click group that toggles traceback behaviour.

### `cli_read_config` / `cli_read_config_json`
- **Purpose:** Invoke composition APIs and render human/JSON output.

### `cli_deploy_config` / `cli_generate_examples`
- **Purpose:** Delegate to example/deploy helpers and emit JSON file lists.

### Helper Functions (`_render_json`, `_render_human`, `_normalise_*`)
- **Purpose:** Keep command handlers declarative and reusable.

### Metadata Helpers (`version_string`, `describe_distribution`)
- **Purpose:** Produce CLI-friendly metadata strings sourced from
  `lib_layered_config.__init__conf__`.
- **Input:** Constants exposed via `__init__conf__.info_lines()` and related
  helpers maintained by release automation.
- **Output:** Click `--version` banner and `info` command lines.
- **Location:** `src/lib_layered_config/cli/common.py`
- **Supporting Docs:** The metadata module also exports
  `metadata_fields()`/`info_lines()` for structured and human rendering.

### Traceback Support Helpers (`_session_overrides`)
- **Purpose:** Derive `lib_cli_exit_tools.cli_session` overrides from parsed CLI
  arguments so the global `--traceback` flag works across entry points.
- **Input:** Raw argument sequences passed to the root CLI.
- **Output:** Mapping containing `{"traceback": True}` when verbose tracebacks
  were requested; empty mapping otherwise.
- **Location:** `src/lib_layered_config/cli/__init__.py`

---

## Testing Approach

- `tests/e2e/test_cli.py` covers each subcommand, JSON/human output, deployment
  flows, tracebacks, and failure handling.

---

## Known Issues & Future Improvements

- Consider adding streaming support for very large configurations; current
  implementation loads everything in memory.

---

### Feature Documentation: Platform Alias Helpers

## Status

Complete

## Links & References

**Feature Requirements:** docs/systemdesign/concept.md (Platform alias normalisation)
**Related Files:**

- `src/lib_layered_config/_platform.py`
- `src/lib_layered_config/cli.py`
- `src/lib_layered_config/examples/generate.py`
- `tests/unit/test_cli_helpers.py`

---

## Problem Statement

CLI and example tooling accept user-provided platform strings. Duplicated alias
logic risked drift between commands and documentation, and made it difficult to
expand supported names consistently.

## Solution Overview

- Centralise alias normalisation in `_platform.py` with explicit resolver and
  example mappings.
- Expose helpers that raise descriptive `ValueError`s so CLI code can translate
  them to `click.BadParameter`.
- Keep defaults (auto-detection) in outer layers while sharing validation
  semantics.

---

## Architecture Integration

**Layer Fit:** Presentation/helper boundary shared by CLI and example tooling.

**System Dependencies:** Standard library only.

---

## Core Components

### `normalise_resolver_platform`
- **Purpose:** Map CLI `--platform` inputs to resolver identifiers (`linux`,
  `darwin`, `win32`).
- **Tests:** `tests/unit/test_cli_helpers.py::test_normalise_platform_maps_aliases`.

### `_sanitize`
- **Purpose:** Normalise raw alias inputs (strip/normalize case) and reject empty
  values before delegation so error messages stay descriptive.
- **Usage:** Shared guard leveraged by both normalisation helpers.

---

## Testing Approach

- Unit tests cover alias permutations and error handling via Click wrappers.

---

## Known Issues & Future Improvements

- Revisit mappings if additional artefact generators introduce new platform
  families.

---

### Feature Documentation: Example Deployment Helper

## Status

Complete

## Links & References

**Feature Requirements:** docs/systemdesign/concept.md (Operator tooling)
**Related Files:**

- `src/lib_layered_config/examples/deploy.py`
- `tests/examples/test_deploy.py`
- `tests/e2e/test_deploy_behavior.py`

---

## Problem Statement

Operators need to copy configuration templates into the same layered structure
the runtime expects, with clear options for handling conflicts when files
already exist at the destination.

## Solution Overview

- `deploy_config` validates targets, computes destinations using
  `DefaultPathResolver`, and deploys files with conflict handling.
- Three conflict resolution strategies: interactive prompts, `--force` for
  automatic backup-and-overwrite, `--batch` for keep-and-write-UCF (CI/scripts).
- Results tracked via `DeployResult` dataclass with backup/UCF paths.

---

## Architecture Integration

**Layer Fit:** Optional tooling layer reused by the CLI `deploy` command.

**System Dependencies:** Path resolver adapter, `pathlib`, `os`, `shutil`.

---

## Core Components

### `deploy_config`
- **Purpose:** Public API for copying configuration artefacts with conflict handling.
- **Input:** Source path, vendor/app/slug identifiers, targets, and optional
  `force`, `batch`, and `conflict_resolver` parameters.
- **Output:** `list[DeployResult]` describing the action taken for each destination.

### `DeployAction` (Enum)
- **Purpose:** Track deployment outcomes: `CREATED`, `OVERWRITTEN`, `KEPT`, `SKIPPED`.
- **Location:** `examples/deploy.py`

### `DeployResult` (Dataclass)
- **Purpose:** Rich result object containing:
  - `destination`: Target file path
  - `action`: What action was taken (`DeployAction`)
  - `backup_path`: Path to `.bak` backup file (if overwritten)
  - `ucf_path`: Path to `.ucf` file (if kept existing)
- **Location:** `examples/deploy.py`

### `ConflictResolver` (Type Alias)
- **Purpose:** Callback type for custom conflict resolution: `Callable[[Path], DeployAction]`.
- **Usage:** Called when destination exists and neither `--force` nor `--batch` is set.

### Conflict Handling Helpers
- `_content_matches`: Compare destination content with payload for smart skipping.
- `_next_available_path`: Find non-conflicting path with numbered suffix (`.bak.1`, `.bak.2`).
- `_backup_file`: Create `.bak` backup of existing file.
- `_write_ucf`: Write new content as `.ucf` variant when keeping existing.
- `_deploy_single`: Handle conflict resolution for a single destination.
- `_execute_action`: Perform the chosen action (overwrite/keep/skip).

### Path Resolution Helpers
- `_prepare_resolver`, `_destinations_for`, `_copy_payload`:
  Internal helpers to compute destinations and enforce deployment policy.

---

## Conflict Handling Behavior

| Scenario | Behavior |
|----------|----------|
| New file (no conflict) | File created, action = `CREATED` |
| File exists + identical content | Skip silently (smart skip), action = `SKIPPED` |
| File exists + different content + `--force` | Backup to `.bak`, overwrite, action = `OVERWRITTEN` |
| File exists + different content + `--batch` | Keep existing, write new as `.ucf`, action = `KEPT` |
| File exists + different content + interactive | Prompt user: Keep (`.ucf`, default) / Overwrite (`.bak`) |
| Existing `.bak`/`.ucf` | Use numbered suffix (`.bak.1`, `.bak.2`, etc.) |

**Smart Skipping:** When the destination file already exists with identical content
to the source, deployment is skipped without creating backups. This avoids
unnecessary `.bak` file proliferation and is applied regardless of `--force`
or `--batch` flags.

---

## Testing Approach

- `tests/examples/test_deploy.py` covers unit-level behavior: backup creation,
  UCF generation, numbered suffixes, conflict resolver callbacks, and
  POSIX/Windows paths.
- `tests/e2e/test_deploy_behavior.py` covers end-to-end CLI scenarios:
  first-run creation, batch UCF creation, force overwriting, JSON output format,
  multiple sequential deploys with numbered backups, and smart skipping
  when content is identical.

---

## Known Issues & Future Improvements

- Interactive prompts require a TTY; use `--batch` for non-interactive environments.

---

### Feature Documentation: Example Generator

## Status

Complete

## Links & References

**Feature Requirements:** docs/systemdesign/concept.md (Onboarding examples)
**Related Files:**

- `src/lib_layered_config/examples/generate.py`
- `tests/examples/test_deploy.py` (shared helpers exercise specs)

---

## Problem Statement

Documentation and onboarding scripts need to generate realistic configuration
trees showcasing layered layout without manual setup.

## Solution Overview

- `generate_examples` builds platform-specific `ExampleSpec` sequences and
  writes them to disk.
- Helpers manage directory creation, overwrite semantics, and template content.

---

## Architecture Integration

**Layer Fit:** Optional tooling invoked by CLI and documentation scripts.

**System Dependencies:** `dataclasses`, `pathlib`, `os`.

---

## Core Components

### `ExamplePlan`
- **Purpose:** Frozen plan assembling destination, metadata, and overwrite flags
  prior to generation.

### `ExampleSpec`
- **Purpose:** Dataclass capturing relative path + content for a single file.

### `_build_specs`, `_write_examples`, `_should_write`, `_ensure_parent`
- **Purpose:** Generate platform-aware specs, honour force semantics, and create
  filesystem paths safely.

### `_normalise_platform`
- **Purpose:** Collapse user-provided platform aliases into `posix`/`windows`
  before dispatching to platform-specific spec builders.

---

## Testing Approach

- `tests/examples/test_deploy.py` verifies writer behaviour; CLI tests cover
  human-facing usage.

---

## Known Issues & Future Improvements

- Specs are static; consider templating tooling if documentation requires more
  dynamic content.

---

### Feature Documentation: Observability Helpers

## Status

Complete

## Links & References

**Feature Requirements:** docs/systemdesign/concept.md (Observability)
**Related Files:**

- `src/lib_layered_config/observability.py`
- `tests/unit/test_observability.py`

---

## Problem Statement

Provide structured logging with trace correlation without forcing applications
to adopt a specific logging framework.

## Solution Overview

- Context variable `TRACE_ID` to propagate trace identifiers.
- Helpers `log_debug`, `log_info`, `log_error`, `make_event` standardise
  structured payloads.
- ``get_logger`` exposes a shared logger with a `NullHandler` by default.

---

## Architecture Integration

**Layer Fit:** Used by adapters, `_layers`, and the composition root; domain
layer remains logging-free.

**System Dependencies:** `logging`, `contextvars`.

---

## Testing Approach

- `tests/unit/test_observability.py` validates trace binding, logging payloads,
  and event merging behaviour.

---

## Known Issues & Future Improvements

- Consider optional integration with structured logging frameworks (e.g.,
  `structlog`) if future requirements emerge.

---

### Feature Documentation: Testing Utilities

## Status

Complete

## Links & References

**Feature Requirements:** docs/systemdesign/concept.md (Testing aids)
**Related Files:**

- `src/lib_layered_config/testing.py`
- `tests/unit/test_testing.py`

---

## Problem Statement

Integration tests and tutorials need a deterministic way to trigger failures
that exercise error-handling paths without bespoke fixtures.

## Solution Overview

- `FAILURE_MESSAGE` holds the canonical error string.
- `i_should_fail` raises `RuntimeError` with the message for CLI/testing use.

---

## Architecture Integration

**Layer Fit:** Testing/tooling layer; referenced by CLI `fail` command and
notebooks.

---

## Testing Approach

- `tests/unit/test_testing.py` ensures the helper raises as expected; CLI tests
  assert error propagation.

---

## Known Issues & Future Improvements

- None at present; future scenarios may add additional failure helpers if more
  complex testing flows arise.

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
  directories (app, host, user) discovered by the path resolver, with
  interactive conflict handling, backup creation, and UCF file support.
- **Responsibilities:**
  - Instantiate a path resolver via `_prepare_resolver`.
  - Compute destination paths with `_destinations_for`.
  - Handle conflicts via `--force` (backup and overwrite), `--batch` (keep
    and write `.ucf`), or interactive prompt (keep as `.ucf` or overwrite with `.bak`).
  - Track results via `DeployResult` dataclass with action, backup, and UCF paths.
  - Use numbered suffixes (`.bak.1`, `.bak.2`) when backup/UCF files exist.
- **Dependencies:** `pathlib`, `shutil`, environment variables for overrides, adapters.
- **Public API:** `deploy_config`, `DeployAction`, `DeployResult`, `ConflictResolver`.
- **Verification:** `tests/examples/test_deploy.py` covers unit-level behavior;
  `tests/e2e/test_deploy_behavior.py` covers end-to-end CLI scenarios.

### Module: `lib_layered_config/examples/__init__.py`
- **Purpose:** Present a single namespace for example helpers consumed by
  documentation and notebooks.
- **Public API:** Re-exports `deploy_config`, `DeployAction`, `DeployResult`,
  `ConflictResolver`, `generate_examples`, `ExampleSpec`, `DEFAULT_HOST_PLACEHOLDER`.
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
