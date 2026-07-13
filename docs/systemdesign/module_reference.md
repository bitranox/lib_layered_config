# Module Reference

An architecture map of `lib_layered_config`: the layers, the import rules the build enforces,
and a one-line responsibility for every module. The exhaustive per-function detail (arguments,
return types, edge cases, runnable examples) lives in the source docstrings - Google style,
type-checked by pyright and executed as doctests under `make test` - so this file stays the
orientation layer on top of them rather than a second copy that rots. For the design intent see
[concept.md](concept.md); for user-facing usage see the [README](../../README.md) and the guides
under [docs/](../).

## Architecture

The library follows Clean Architecture: dependencies point inward only. Two import-linter
contracts in `pyproject.toml` (run by `lint-imports`, and in CI) fail the build if either is
violated:

- **Layered:** `cli` -> `examples` -> `adapters` -> `application` -> `domain`. A layer may import
  only from the layers below it.
- **Domain is pure:** `domain` may not import `adapters`, `application`, or `core`.

The root modules (`core.py`, `_layers.py`, `_platform.py`, `observability.py`, `testing.py`,
`__init__.py`, `__init__conf__.py`, `__main__.py`) sit outside the layer hierarchy and act as the
composition root and shared plumbing.

### The read pipeline

`read_config(...)` resolves per-platform paths, loads each layer, and deep-merges them in a fixed
precedence, producing an immutable `Config` plus provenance:

```
defaults -> app -> host -> user -> dotenv -> env      (lowest to highest precedence)
```

Every merged value records which layer and file produced it; `Config.origin(key)` returns that.

## Module map

### Composition root and shared plumbing

| Module              | Responsibility                                                                                                                            |
|---------------------|-------------------------------------------------------------------------------------------------------------------------------------------|
| `__init__.py`       | Public API surface: re-exports the read functions, `Config`, `Layer`, deploy/generate, and the validation and permission constants.       |
| `__init__conf__.py` | Generated package-metadata constants, synced from `pyproject.toml`.                                                                       |
| `__main__.py`       | `python -m lib_layered_config` entry point; delegates to the CLI.                                                                         |
| `core.py`           | Composition root: `read_config` / `read_config_json` / `read_config_raw` wire the adapters and the merge; defines `LayerLoadError`.       |
| `_layers.py`        | Layer assembly: `collect_layers` builds the ordered `LayerSnapshot` list (defaults, app, host, user, dotenv, env), incl. `.d` and dotenv. |
| `_platform.py`      | Normalizes user-supplied platform aliases (`normalise_resolver_platform`, `normalise_examples_platform`); raises `ValidationError`.       |
| `observability.py`  | Structured logging helpers (`log_debug`/`log_info`/`log_warn`/`log_error`, trace-id binding) so adapters log without coupling the domain. |
| `testing.py`        | Small diagnostics helper (`i_should_fail`) for consumers' failure-path tests and the CLI `fail` command.                                  |

### domain/ - pure business logic (no I/O)

| Module           | Responsibility                                                                                                                                        |
|------------------|-------------------------------------------------------------------------------------------------------------------------------------------------------|
| `config.py`      | Immutable `Config` value object: dotted-path `get`/`__getitem__`, `origin` provenance lookup, `as_dict`/`to_json` (optional redaction); `SourceInfo`. |
| `errors.py`      | Exception taxonomy: `ConfigError` base, `InvalidFormatError`, `ValidationError` (subclasses `ConfigError` and `ValueError`), `NotFoundError`.         |
| `identifiers.py` | `Layer` enum and identifier/profile validation (path traversal, reserved names, control chars, non-ASCII, length); raises `ValidationError`.          |
| `redaction.py`   | Secret masking: `is_sensitive` (password/token/apikey/`_key`/cookie/jwt/... patterns), `redact_mapping` (depth-guarded), `REDACTED_PLACEHOLDER`.      |
| `permissions.py` | Per-layer Unix permission policy: `LAYER_PERMISSIONS` (keyed by `Layer` values), `set_permissions` / `set_custom_permissions`, mode constants.        |

### application/ - use cases and ports

| Module     | Responsibility                                                                                                                                                                                 |
|------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `merge.py` | Deterministic deep-merge with provenance: `merge_layers`, `LayerSnapshot`, `MergeResult`; scalar/mapping/list rules, numeric-index array-element override, `ValueKind`, recursion-depth guard. |
| `ports.py` | Port `Protocol`s the adapters implement (`PathResolver`, `FileLoader`, `DotEnvLoader`, `EnvLoader`, `Merger`), `OutputFormat`, and `SourceInfoPayload`.                                        |

### adapters/ - infrastructure

| Module                                               | Responsibility                                                                                                         |
|------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------|
| `_nested_keys.py`                                    | Shared `__`-delimited nested-key assignment (`assign_nested`) used by the dotenv and env loaders.                      |
| `path_resolvers/default.py`                          | `DefaultPathResolver`: selects a per-OS strategy and yields ordered candidate paths per layer.                         |
| `path_resolvers/_base.py`                            | `PlatformContext`, the `PlatformStrategy` base, and `collect_layer` (a config file plus its `.d`).                     |
| `path_resolvers/_linux.py` `_macos.py` `_windows.py` | Per-platform directory layouts (XDG, Application Support, ProgramData).                                                |
| `path_resolvers/_dotenv.py`                          | Ordered `.env` search-path discovery.                                                                                  |
| `file_loaders/structured.py`                         | TOML / JSON / YAML loaders (`BaseFileLoader`), with a maximum-file-size guard.                                         |
| `file_loaders/_dot_d.py`                             | `.d` directory expansion (`expand_dot_d`), filtered by config extension.                                               |
| `dotenv/default.py`                                  | `DefaultDotEnvLoader`: parse a `.env` file via upward search or an explicit path.                                      |
| `env/default.py`                                     | `DefaultEnvLoader`: prefix-filter environment variables and coerce values (bool/null/int/float + JSON arrays/objects). |
| `display/rich.py`                                    | Rich-styled human rendering of the merged TOML with per-key provenance comments.                                       |

### cli/ - command-line interface (package)

| Module           | Responsibility                                                                                                          |
|------------------|-------------------------------------------------------------------------------------------------------------------------|
| `__init__.py`    | The Click command group and `main()` entry; wires `lib_cli_exit_tools.cli_session` and derives `SessionOverrides`.      |
| `common.py`      | Shared CLI helpers: `ReadQuery`, `build_read_query`, `json_payload` / `human_payload` (with redaction), `render_human`. |
| `constants.py`   | CLI constants: `TARGET_CHOICES` (from the `Layer` enum) and the Click context settings.                                 |
| `read.py`        | The `read` and `read-json` commands (including `--redact`).                                                             |
| `deploy.py`      | The `deploy` command.                                                                                                   |
| `generate.py`    | The `generate-examples` command.                                                                                        |
| `info.py`        | The `info` and `env-prefix` commands.                                                                                   |
| `fail.py`        | The `fail` diagnostic command.                                                                                          |
| `typed_click.py` | Thin typed wrappers over rich-click decorators, isolating the one partially-untyped boundary.                           |

### examples/ - deployment and scaffolding (its own layer between cli and adapters)

| Module        | Responsibility                                                                                                                                                                         |
|---------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `deploy.py`   | `deploy_config` and the per-OS `DeploymentStrategy`; conflict handling (backup `.bak`, keep-as-`.ucf`), atomic writes, and layer permission hardening; `DeployAction`, `DeployResult`. |
| `generate.py` | Scaffold example config trees (`generate_examples`, `ExamplePlan`, `ExampleSpec`).                                                                                                     |

## Where the detail lives

- Per-function contracts, arguments, return types, and runnable examples: the module **docstrings** (Google style; type-checked by pyright and executed as doctests under `make test`).
- Design intent, goals, and quality bars: [concept.md](concept.md).
- Test layout: [test_matrix.md](test_matrix.md).
- User-facing usage: the [README](../../README.md) and the guides in [docs/](../) - identifiers and profiles, configuration file structure, the CLI reference, and the Python API reference.
