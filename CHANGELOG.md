# Changelog

All notable changes to lib_layered_config

This project adheres to [Semantic Versioning](https://semver.org/).

## [5.4.0] - 2026-01-31

### Added

- **Unix file permissions for deployed configuration files** — The `deploy_config()` function now automatically sets appropriate Unix file permissions based on the target layer. This ensures configuration files have the right access controls without manual `chmod` commands.

  **Default permissions by layer:**
  | Layer | Directory Mode | File Mode | Rationale |
  |-------|---------------|-----------|-----------|
  | `app` | `0o755` (rwxr-xr-x) | `0o644` (rw-r--r--) | System-wide config readable by all |
  | `host` | `0o755` (rwxr-xr-x) | `0o644` (rw-r--r--) | Machine-specific config readable by all |
  | `user` | `0o700` (rwx------) | `0o600` (rw-------) | Private user config |

  **New parameters for `deploy_config()`:**
  - `set_permissions: bool = True` — Enable/disable permission setting (default: enabled)
  - `dir_mode: int | None = None` — Override directory mode for all targets
  - `file_mode: int | None = None` — Override file mode for all targets

  **CLI flag:**
  - `--permissions / --no-permissions` — Enable/disable permission setting (default: `--permissions`)

  **Platform behavior:**
  - Linux/macOS: Full permission support via `chmod()`
  - Windows: Permissions skipped (Windows uses ACLs, not Unix modes)

  **Example usage:**
  ```python
  from lib_layered_config import deploy_config

  # Default: layer-aware permissions
  deploy_config(source="config.toml", vendor="Acme", app="MyApp",
                targets=["user"], slug="myapp")
  # User layer files get 700/600 permissions

  # Custom permissions
  deploy_config(source="config.toml", vendor="Acme", app="MyApp",
                targets=["app"], slug="myapp",
                dir_mode=0o750, file_mode=0o640)

  # Disable permissions
  deploy_config(source="config.toml", vendor="Acme", app="MyApp",
                targets=["user"], slug="myapp",
                set_permissions=False)
  ```

- **Permission constants exported in public API** — Four permission mode constants are now available from the main package:
  - `DEFAULT_APP_DIR_MODE` — `0o755`
  - `DEFAULT_APP_FILE_MODE` — `0o644`
  - `DEFAULT_USER_DIR_MODE` — `0o700`
  - `DEFAULT_USER_FILE_MODE` — `0o600`

- **`domain/permissions.py` module** — New domain module containing:
  - `set_permissions()` — Apply layer-aware default permissions
  - `set_custom_permissions()` — Apply custom permission modes
  - `LAYER_PERMISSIONS` — Mapping of layer names to permission modes

- **Profile name length validation** — Profile names are now validated for length with configurable limits for security and filesystem safety.

  **Length limits:**
  - Default max length: 64 characters (`DEFAULT_MAX_PROFILE_LENGTH`)
  - Absolute max length: 256 characters (internal security hardening)
  - Even if `max_length` is set higher than 256, the 256 limit is enforced
  - Setting `max_length=0` or negative uses the absolute maximum (256 chars)

  **New public API exports:**
  - `DEFAULT_MAX_PROFILE_LENGTH` — Constant (64 characters)
  - `validate_profile_name(value, *, max_length=64)` — Raises `ValueError` on invalid
  - `is_valid_profile_name(value, *, max_length=64)` — Returns `bool`, no exception

  **New parameter for `deploy_config()`:**
  - `max_profile_length: int = 64` — Maximum allowed profile name length

  **Security checks include:**
  - Path traversal prevention (`../`, `..\\`, absolute paths)
  - Control character rejection (null bytes, newlines, tabs)
  - Windows reserved name blocking (CON, PRN, NUL, COM1-9, LPT1-9)
  - Non-ASCII character rejection (encoding attack prevention)
  - Must start with alphanumeric, no trailing dots/spaces

  **Example usage:**
  ```python
  from lib_layered_config import (
      validate_profile_name,
      is_valid_profile_name,
      DEFAULT_MAX_PROFILE_LENGTH,
  )

  # Validate with exception
  validate_profile_name("production")  # OK
  validate_profile_name("a" * 100)     # Raises ValueError

  # Check without exception
  if is_valid_profile_name(user_input):
      deploy_config(..., profile=user_input)

  # Custom max length
  validate_profile_name("long-profile-name", max_length=128)
  ```

### Changed

- **README restructured by theme** — The README now has a cleaner organization with sections grouped by theme:
  - Getting Started (Key Features, Installation, Quick Start)
  - Core Concepts (Identifiers, Profiles, File Structure, Precedence)
  - Command Line Interface (all CLI commands)
  - Python API (all API functions and classes)
  - Deployment & Security (permissions, security best practices, .d directories)
  - Reference (observability, architecture, development)

### Documentation

- **Comprehensive security best practices** — New README sections covering:
  - File permissions by layer with rationale
  - Recommended permissions for `.env` files (`0o600`)
  - macOS and Windows platform-specific considerations
  - Recommendations for sensitive data (env vars, secrets managers, redaction)

- **Updated CLAUDE.md** — Added File Permissions section with API parameters, CLI flags, platform behavior, and implementation file references

## [5.3.9] - 2026-01-29

### Changed

- **Refactored config display using rtoml serialization** — The `display_config()` function now uses `rtoml.dumps()` for TOML serialization instead of custom formatting logic, then applies Rich styling to the output. This produces more accurate TOML output that matches standard TOML conventions and simplifies the codebase.

### Internal

- Replaced manual value formatting with `rtoml.dumps()` followed by regex-based parsing and styling
- Removed `_is_flat_dict()`, `_format_raw_value()`, `_styled_entry()`, `_has_leaf_values()`, and `_print_section()` helper functions
- Added `_SECTION_PATTERN` and `_KEY_VALUE_PATTERN` regex constants for parsing TOML output
- New `_render_toml_with_styling()` function handles line-by-line styling of TOML output

## [5.3.8] - 2026-01-29

### Added

- **Explanatory header in human output** — `display_config()` now prints a bright red header comment at the start of human-readable output explaining that nested dictionaries are displayed as `[section.subsection]` headers and may not match the original TOML structure. This helps users understand TOML serialization behavior.

## [5.3.5] - 2026-01-29

### Added

- **Provenance tracking for empty dicts** — The merge logic now stores provenance metadata for empty dict values (e.g., `console_styles: {}`). This allows `display_config()` to show source comments for empty dicts, matching the behavior for scalar values. Previously, empty dicts had no provenance and displayed without source information.

### Changed

- **`Config.origin()` returns data for empty dicts** — The `origin()` method now returns `SourceInfo` for empty dict keys instead of `None`, providing consistent provenance lookup across all value types.

## [5.3.4] - 2026-01-29

### Changed

- **`OutputFormat` moved to application layer** — The `OutputFormat` enum is now defined in `application.ports` instead of `cli.common` to satisfy Clean Architecture layer constraints. Both `cli` and `adapters.display` can now import it without violating import rules. The enum remains exported from the package root.

- **Flat dicts rendered as inline tables** — `display_config()` now renders flat dicts (containing only primitive values, no nested dicts) as TOML inline tables (e.g., `scrub_patterns = { password = ".+", token = ".+" }`) instead of section headers. This matches the TOML source style and reduces visual noise.

### Fixed

- **Leaf values now appear under correct section header** — `display_config()` now prints all leaf values (scalars, lists, and flat dicts) for a section before recursing into nested subsections. Previously, values appearing after a nested dict in iteration order would visually appear under the subsection header (e.g., `rate_limit` appearing under `[lib_log_rich.scrub_patterns]` instead of `[lib_log_rich]`).

## [5.3.3] - 2026-01-29

### Changed

- **`display_config` styling refinement** — Adjusted color scheme for better readability: keys now use light brown (`orange3`), the `=` separator is white (previously dimmed), and all values use green (previously yellow for non-strings).

### Fixed

- **Empty sections no longer displayed** — `display_config()` now skips empty dict values (e.g., `console_styles = {}`) instead of creating meaningless section headers like `[section.empty_table]`. Sections with no leaf values at any nesting level are omitted from output.

## [5.3.2] - 2026-01-29

### Added

- **Rich-styled configuration display** — New `display_config()` function in `adapters.display` for enhanced configuration visualization with Rich console styling.

  **Features:**
  - Human-readable TOML-like output with color-coded display (light brown keys, white `=`, green values)
  - JSON output format with automatic redaction
  - Provenance comments showing layer, profile, and source file path for each value
  - Cyan section headers, yellow provenance comments
  - Automatic redaction of sensitive values (passwords, tokens, secrets, API keys) displayed in dim red

  **Usage:**
  ```python
  from lib_layered_config import read_config, display_config, OutputFormat

  config = read_config(vendor="Acme", app="MyApp", slug="myapp")
  display_config(config)  # Human-readable output
  display_config(config, output_format=OutputFormat.JSON)  # JSON output
  display_config(config, section="database")  # Display specific section only
  ```

- **`OutputFormat` enum exported** — The `OutputFormat` enum (`OutputFormat.HUMAN`, `OutputFormat.JSON`) is now available from the main package for use with `display_config()`.

## [5.3.1] - 2026-01-28

### Changed
- **Provenance layer serialization** — `_store_scalar()` in `application/merge.py` now extracts the string `.value` from `Layer` enum instances before storing in the provenance dict. Previously, a `Layer` enum object could end up in the `"layer"` field, causing issues during JSON serialization

## [5.3.0] - 2026-01-27

### Added
- **Redaction support** - `Config.to_json(redact=True)` and `Config.as_dict(redact=True)` mask sensitive configuration values (passwords, tokens, secrets, API keys, credentials, private keys) with `***REDACTED***`. Prevents accidental exposure of secrets in logs, CLI output, or JSON exports.
- **`redact_mapping()` function** - Public domain function for recursive redaction of sensitive values in configuration dictionaries.
- **`is_sensitive()` predicate** - Public function to test whether a configuration key name matches known sensitive patterns.
- **`REDACTED_PLACEHOLDER` constant** - The `***REDACTED***` string used as replacement, exported for consumer use.
- **`orjson` as a production dependency** - Added `orjson>=3.11.5` for faster JSON serialization/deserialization.
- **`httpx` as a dev dependency** - Added `httpx>=0.28.0`, replacing `urllib` in development scripts.

### Changed
- `Config.with_overrides()` now performs **deep recursive merge** instead of
  shallow top-level replacement. Nested dict keys are preserved when overriding
  a sub-key. Non-mapping values (scalars, lists) are still replaced entirely.
- **TOML-style human-readable output** — `render_human()` now produces
  `[section.subsection]` headers and `key = value` lines instead of flat
  dotted-path listings. Provenance is shown as `# source:` comments above
  each setting. Strings are double-quoted, lists use JSON array syntax.
- Replaced stdlib `json` with `orjson` for JSON serialization/deserialization across all production modules (`domain/config.py`, `core.py`, `cli/common.py`, `cli/deploy.py`, `adapters/file_loaders/structured.py`).

### Fixed
- **import-linter contracts** — Fixed `make test` to invoke `lint-imports` CLI
  instead of a no-op `python -m importlinter.cli lint` command. Updated layers
  contract to use `containers` parameter (required by grimp v3.14). Corrected
  forbidden contract field name from `modules` to `source_modules`.
- `Config.to_json()` now uses orjson; the `indent` parameter always produces 2-space indent when set (orjson limitation).
- `Config.to_json()` gains `redact: bool = False` parameter.
- `Config.as_dict()` gains `redact: bool = False` parameter.
- `read_config_json()` gains `redact: bool = False` parameter.
- Replaced `tomllib`/`tomli` with `rtoml` in test suite (`tests/test_metadata.py`) for consistency with production TOML parser.
- Replaced `urllib` with `httpx` in `scripts/dependencies.py` for PyPI API requests.

## [5.2.1] - 2026-01-19

### Changed

- Removed unused `ctx.obj["traceback"]` storage in CLI root command. The `--traceback` flag continues to work via `_session_overrides()` which passes the flag to `lib_cli_exit_tools.cli_session`.

### Security

- Cleaned up pip-audit ignore list: removed `CVE-2025-68146` (filelock) which is no longer present in dependencies

## [5.2.0] - 2025-12-29

### Added

- **UNC path documentation and tests** - Documented support for UNC network paths (e.g., `//server/share`) in Windows path resolution. UNC paths are handled natively by `pathlib.Path` and can be configured via environment variable overrides.

  **Environment variables supporting UNC paths:**
  - `LIB_LAYERED_CONFIG_PROGRAMDATA` - Override for app-layer paths
  - `LIB_LAYERED_CONFIG_APPDATA` - Override for user-layer paths (roaming)
  - `LIB_LAYERED_CONFIG_LOCALAPPDATA` - Override for user-layer paths (local fallback)

  **Example:**
  ```bash
  export LIB_LAYERED_CONFIG_PROGRAMDATA="//fileserver/configs"
  ```

- **Cross-platform path handling documentation** - Added documentation noting that all path handling uses `pathlib.Path` for cross-platform compatibility.

### Changed

- Updated `_windows.py` module and class docstrings with UNC path support details
- Updated `_base.py` module docstring with cross-platform path handling note
- Reduced cyclomatic complexity in `cli/deploy.py`, `domain/identifiers.py`, and `examples/deploy.py` by extracting helper functions

### Fixed

- Fixed broken reference to non-existent `AGENTS.md` in `CONTRIBUTING.md` (now correctly references `CLAUDE.md`)

### Security

- Added `CVE-2025-68146` (filelock race condition) to pip-audit ignore list as accepted risk for transitive dependency

## [5.1.0] - 2025-12-13

### Added

- **`.d` directory expansion for configuration files** - Any configuration file now automatically discovers and merges files from a companion `.d` directory. This follows the pattern used by `/etc/apt/sources.list.d/` and similar Unix conventions.

  **Naming Convention:** The `.d` directory name is derived by replacing the file extension with `.d`:
  - `config.toml` → `config.d/`
  - `config.yaml` → `config.d/`
  - `config.json` → `config.d/`

  This design allows all formats to share the same companion directory and enables mixed format files within a single `.d` directory.

  **Features:**
  - Files in the `.d` directory are sorted lexicographically (e.g., `10-database.toml`, `20-cache.toml`)
  - Both the base file and `.d` directory are optional (either can exist independently)
  - Provenance tracks which specific `.d` file provided each configuration value
  - Supports mixed formats in the same `.d` directory (TOML, YAML, JSON)
  - Non-config files (e.g., `README.md`) are automatically ignored
  - Works at all layers: defaults, app, host, user

  **Example directory structure:**
  ```
  /etc/xdg/myapp/
  ├── config.toml              # Base configuration
  └── config.d/                # Companion .d directory
      ├── 10-database.toml     # Merged second
      ├── 20-cache.yaml        # Merged third (mixed formats OK)
      └── 30-logging.json      # Merged fourth
  ```

  **Merge order:** `config.toml` → `10-database.toml` → `20-cache.yaml` → `30-logging.json`

  **Usage example:**
  ```python
  from lib_layered_config import read_config

  # Automatically reads config.toml + config.d/* files
  config = read_config(vendor="Acme", app="MyApp", slug="myapp")

  # Provenance shows which .d file provided each value
  print(config.origin("database.host"))
  # → {"layer": "app", "path": "/etc/xdg/myapp/config.d/10-database.toml", "key": "database.host"}
  ```

- **`expand_dot_d()` function** - New public function in `adapters.file_loaders` for expanding a config file path to include `.d` directory entries. Useful for advanced use cases where direct control over file expansion is needed.

- **`_note_dot_d_expanded()` logging helper** - New observability helper that logs when `.d` expansion occurs with the count of additional files discovered.

- **`.d` directory support in `deploy_config`** - The `deploy_config` function now automatically detects and deploys companion `.d` directories. When deploying `config.toml`, if `config.d/` exists, its contents are also deployed to the corresponding `.d` directory at each destination.

  **Key behaviors:**
  - Deployment is **additive**: user-added files in the destination `.d` directory are preserved
  - Smart skip and backup functionality applies to `.d` files (identical to base file handling)
  - ALL files from source `.d` are copied (including README.md, notes.txt) to preserve documentation
  - Only config file parsing filters by extension; deployment copies everything

  **Best practice:** Override settings in a separate file (e.g., `90-local-overrides.toml`) instead of modifying distributed config files. This ensures customizations survive re-deployments.

  **JSON output fields for .d results:**
  - `dot_d_created`: Paths of .d files created
  - `dot_d_overwritten`: Paths of .d files overwritten
  - `dot_d_skipped`: Paths of .d files skipped (identical content)
  - `dot_d_backups`: Paths of .d backup files created

### Internal

- Added `adapters/file_loaders/_dot_d.py` module for `.d` directory expansion logic
- Modified `_layers._load_entry_with_dot_d()` to integrate `.d` expansion into the layer loading pipeline
- Updated `adapters/path_resolvers/_base.collect_layer()` to yield `config.toml` when `config.d/` directory exists (even if base file is missing)
- Added comprehensive test suites: `tests/adapters/test_dot_d.py` (15 unit tests) and `tests/e2e/test_dot_d_integration.py` (9 E2E tests)

## [5.0.0] - 2025-12-11

### Added

- **5x faster TOML parsing with rtoml** - Switched from stdlib `tomllib` to `rtoml` (Rust-based TOML parser) as the default parser. Benchmarks show ~5x faster parsing across all config sizes:
  - 1KB config: 0.15ms → 0.03ms
  - 17KB config: 2.9ms → 0.55ms
  - 60KB config: 8.3ms → 1.6ms

- **LRU caching for identifier validation** - Added `@lru_cache` to validation functions (`validate_identifier`, `validate_vendor_app`, `validate_hostname`) to avoid redundant validation when reading config multiple times with the same identifiers.

- **Smart skipping for `deploy` command** - When deploying a configuration file, the command now compares the source content with the existing destination file byte-by-byte. If the content is identical, the deployment is skipped without creating backup files. This prevents unnecessary `.bak` file proliferation when repeatedly deploying unchanged configurations.

  **Behavior:**
  - Applies to all modes: `--force`, `--batch`, and interactive
  - Uses exact byte comparison (whitespace differences are detected)
  - File modification time is preserved when skipped
  - JSON output reports `"skipped"` for identical content

  **Example:**
  ```bash
  # First deploy creates the file
  $ lib_layered_config deploy --source config.toml --vendor Acme --app Demo --slug demo --target app
  {"created": ["/etc/xdg/demo/config.toml"]}

  # Second deploy with same content skips (no backup created)
  $ lib_layered_config deploy --source config.toml --vendor Acme --app Demo --slug demo --target app --force
  {"skipped": ["/etc/xdg/demo/config.toml"]}

  # Deploy with different content creates backup and overwrites
  $ lib_layered_config deploy --source config-v2.toml --vendor Acme --app Demo --slug demo --target app --force
  {"overwritten": ["/etc/xdg/demo/config.toml"], "backups": ["/etc/xdg/demo/config.toml.bak"]}
  ```

- **`_content_matches()` helper** - New internal function in `examples/deploy.py` for byte-exact content comparison between source payload and destination file.

### Changed

- **TOML parser dependency** - Replaced `tomllib`/`tomli` with `rtoml` as the default TOML parser. This is a Rust-based parser that provides significant performance improvements while maintaining full TOML 1.0 compatibility.

### Removed

- **Deprecated internal shim functions** - Removed unused compatibility shims from `examples/deploy.py`:
  - Platform-specific destination helpers (`_linux_destination_for`, `_mac_destination_for`, `_windows_destination_for`)
  - Platform-specific path helpers (`_linux_app_path`, `_mac_app_path`, `_windows_app_path`, etc.)
  - Legacy helper functions (`_should_copy`, `_ensure_path`)

  These internal functions were replaced by the `DeploymentStrategy` class hierarchy and `_deploy_single()` function.

## [4.2.0] - 2025-12-11

### Added

- **Interactive conflict handling for `deploy` command** - When a destination file exists, the deploy command now offers two options:
  - **Keep existing** (`k`) - Save new config as `.ucf` (Update Configuration File), preserving the original — **default**
  - **Overwrite** (`o`) - Backup original to `.bak`, then write new file

- **`--batch` flag for `deploy` command** - Non-interactive mode that keeps existing files and writes new config as `.ucf` for manual review. Suitable for CI/CD pipelines and scripts where user customizations must be preserved.

- **Automatic backup creation** - When using `--force` or choosing "Overwrite", the existing file is backed up to `.bak` before being replaced.

- **Numbered suffix handling** - If `.bak` or `.ucf` files already exist, uses numbered suffixes (`.bak.1`, `.bak.2`, etc.) to avoid overwriting previous backups.

- **`DeployAction` enum** - New enum in `examples.deploy` tracking deployment outcomes: `CREATED`, `OVERWRITTEN`, `KEPT`, `SKIPPED`.

- **`DeployResult` dataclass** - Rich return type from `deploy_config()` providing:
  - `destination`: Target path
  - `action`: What action was taken (`DeployAction`)
  - `backup_path`: Path to backup file (if action was `OVERWRITTEN`)
  - `ucf_path`: Path to UCF file (if action was `KEPT`)

- **`ConflictResolver` callback type** - New type alias for custom conflict resolution callbacks: `Callable[[Path], DeployAction]`.

### Changed

- **`deploy_config()` return type** - Now returns `list[DeployResult]` instead of `list[Path]`. The destination paths are accessible via `result.destination`.

  **Breaking Change:** Update code that uses the return value:
  ```python
  # Before
  paths = deploy_config(source, vendor="V", app="A", targets=["app"], slug="s")
  for path in paths:
      print(f"Created: {path}")

  # After
  results = deploy_config(source, vendor="V", app="A", targets=["app"], slug="s")
  for result in results:
      print(f"{result.action.value}: {result.destination}")
  ```

- **`deploy_config()` signature** - Added new parameters:
  - `batch: bool = False` - Keep existing and write new as `.ucf` for review
  - `conflict_resolver: ConflictResolver | None = None` - Custom callback for conflict resolution

## [4.1.1] - 2025-12-11

### Documentation

- **Fixed error class names in system design docs** - Updated `concept.md` and `module_reference.md` to use actual class names (`InvalidFormatError`, `NotFoundError`) instead of shorthand (`InvalidFormat`, `NotFound`).

- **Improved `with_overrides` limitation documentation** - Added code example and rationale explaining why shallow (top-level) merge is intentional, covering provenance tracking, Clean Architecture, and use case fit. Added workaround guidance for deep override needs.

- **Clarified tomllib/tomli fallback** - Updated documentation to explicitly note `tomllib` (stdlib 3.11+) with `tomli` fallback for Python 3.10.

## [4.1.0] - 2025-12-11

### Added

- **Python 3.10+ compatibility** - The library now supports Python 3.10, 3.11, 3.12, and 3.13. Previously required Python 3.13+.
  - Added `tomli` as a conditional dependency for Python < 3.11 (provides TOML parsing before `tomllib` was added to stdlib)
  - CI matrix now tests against Python 3.10, 3.11, 3.12, 3.13, and latest 3.x

- **`parse_output_format()` function** - New CLI helper in `cli/common.py` that converts string input to `OutputFormat` enum at the CLI boundary, following the data architecture principle of parsing at system edges.

### Changed

- **`wants_json()` signature** - Now accepts only `OutputFormat` enum instead of `str | OutputFormat`. String-to-enum conversion should happen at the CLI boundary using `parse_output_format()`.

## [4.0.1] - 2025-12-08

### Changed

- **Data architecture enforcement** - Replaced magic string literals with named constants and enums throughout the codebase:
  - Added `OutputFormat` enum in CLI for type-safe output format selection (`json` vs `human`)
  - Added `_BOOL_TRUE`, `_BOOL_FALSE`, `_BOOL_LITERALS`, `_NULL_LITERALS` constants in env adapter
  - Added `_QUOTE_CHARS`, `_COMMENT_CHAR`, `_INLINE_COMMENT_DELIMITER`, `_KEY_VALUE_DELIMITER` constants in dotenv adapter
  - Added `NESTED_KEY_DELIMITER` constant for the `__` separator in nested key parsing

### Internal

- **Test suite refactoring** - Enhanced test architecture following clean code principles:
  - Centralized shared fixtures in `tests/conftest.py` (sandbox variants, CLI runner, source file fixtures)
  - Added `tests/unit/test_coverage_edge_cases.py` with 11 new laser-focused edge case tests
  - Improved test coverage from 97.88% to 98.49%
  - All tests now use real behavior over mocks where possible
  - Consistent OS-specific marking throughout (`@os_agnostic`, `@windows_only`, etc.)

## [4.0.0] - 2025-12-01

### Changed

- **Exception names follow PEP 8 convention** - Exception classes now use the `Error` suffix as recommended by PEP 8:
  - `InvalidFormat` → `InvalidFormatError`
  - `NotFound` → `NotFoundError`

  **Breaking Change:** The old names (`InvalidFormat`, `NotFound`) have been removed. Update your imports:

  ```python
  # Before
  from lib_layered_config import InvalidFormat, NotFound

  # After
  from lib_layered_config import InvalidFormatError, NotFoundError
  ```

- **Docstring style changed to Google format** - All docstrings throughout the codebase have been converted from NumPy style to Google style for consistency and wider compatibility.

  **Before (NumPy style):**
  ```python
  def func(value):
      """Short summary.

      Parameters
      ----------
      value : str
          Description of value.

      Returns
      -------
      bool
          Description of return value.
      """
  ```

  **After (Google style):**
  ```python
  def func(value):
      """Short summary.

      Args:
          value: Description of value.

      Returns:
          Description of return value.
      """
  ```

- **Configured `pydocstyle` convention** - Added `[tool.ruff.lint.pydocstyle]` with `convention = "google"` to `pyproject.toml` to enforce consistent docstring formatting.

### Internal

- Reduced cyclomatic complexity in `domain/identifiers.py` by extracting validation helper functions (`_check_not_empty`, `_check_ascii_only`, `_check_no_invalid_chars`, etc.).
- Modernized type annotations: replaced `typing.List`, `typing.Tuple`, `typing.Optional` with built-in `list`, `tuple`, and `X | None` syntax.
- Moved `Iterable`, `Iterator`, `Mapping`, `Sequence` imports from `typing` to `collections.abc`.
- Added docstrings to all Protocol methods in `application/ports.py`.
- Added docstrings to deployment strategy classes and methods in `examples/deploy.py`.
- Simplified `_should_copy()` function in `examples/deploy.py` (SIM103).
- Removed unused imports across CLI modules.

## [3.1.0] - 2025-12-01

### Added

- **Configuration profiles** - New `profile` parameter for `read_config()`, `read_config_json()`, `read_config_raw()`, and `deploy_config()` functions. Profiles allow organizing environment-specific configurations (e.g., `test`, `staging`, `production`) into isolated subdirectories. When specified, all configuration paths include a `profile/<name>/` segment.

  **Example paths with `profile="production"`:**
  - Linux: `/etc/xdg/<slug>/profile/production/config.toml`
  - macOS: `/Library/Application Support/<vendor>/<app>/profile/production/config.toml`
  - Windows: `C:\ProgramData\<vendor>\<app>\profile\production\config.toml`

- **CLI `--profile` option** - Added `--profile` option to `read`, `read-json`, and `deploy` commands.

  ```bash
  lib_layered_config read --vendor Acme --app MyApp --slug myapp --profile production
  lib_layered_config deploy --source config.toml --vendor Acme --app MyApp --slug myapp --profile test --target app
  ```

- **`validate_profile()` function** - New validation function in `domain/identifiers.py` for sanitizing profile names.

- **`validate_path_segment()` function** - New centralized validation function for all filesystem path segments.

- **`validate_vendor_app()` function** - New validation function for vendor/app that allows spaces (for macOS/Windows paths like `/Library/Application Support/Acme Corp/My App/`).

### Changed

- **Enhanced identifier validation** - All identifiers are now validated with comprehensive cross-platform filesystem safety rules:

  **Validation by Type:**
  | Identifier | Spaces Allowed | Notes |
  |------------|----------------|-------|
  | `vendor` | ✅ Yes | For macOS/Windows paths |
  | `app` | ✅ Yes | For macOS/Windows paths |
  | `slug` | ❌ No | Linux paths, env var prefix |
  | `profile` | ❌ No | Profile subdirectory |
  | `hostname` | ❌ No | Host-specific files |

  **Common Rules (All Identifiers):**
  - ASCII-only characters (no UTF-8/Unicode)
  - Must start with alphanumeric character (a-z, A-Z, 0-9)
  - No path separators (`/`, `\`)
  - No Windows-invalid characters (`<`, `>`, `:`, `"`, `|`, `?`, `*`)
  - No Windows reserved names (CON, PRN, AUX, NUL, COM1-9, LPT1-9)
  - Cannot end with dot or space (Windows restriction)

  **Examples:**
  ```python
  # ✅ Valid
  vendor="Acme Corp"    # Spaces OK in vendor
  app="Btx Fix Mcp"     # Spaces OK in app
  slug="my-app"         # No spaces in slug
  profile="production"  # No spaces in profile

  # ❌ Invalid (raises ValueError)
  "../etc"      # Path traversal
  "café"        # Non-ASCII
  "CON"         # Windows reserved
  slug="my app" # Slug cannot have spaces
  ".hidden"     # Starts with dot
  "app<test>"   # Windows-invalid character
  ```

## [3.0.1] - 2025-11-30

### Added

- **`Layer` enum** - New type-safe enumeration for configuration layer names (`Layer.DEFAULTS`, `Layer.APP`, `Layer.HOST`, `Layer.USER`, `Layer.DOTENV`, `Layer.ENV`). The enum values are strings, so they work seamlessly with existing code and provenance dictionaries.

- **Type conflict warnings** - When a later configuration layer overwrites a scalar value with a mapping (or vice versa), a warning is now logged. This helps identify configuration mismatches where a key changes type across layers.

- **Input validation for identifiers** - The `vendor`, `app`, and `slug` parameters are now validated to prevent path traversal attacks. Values containing `/`, `\`, or starting with `.` will raise `ValueError`.

- **Hostname sanitization** - Hostnames used in path resolution are now validated to prevent path traversal via malicious hostname values.

### Changed

- **`MergeResult` dataclass** - The merge function now returns a `MergeResult` dataclass with `data` and `provenance` attributes instead of a tuple, improving code clarity.

- **Observability module** - Added `log_warn()` function for structured warning logs with trace context.

### Internal

- Consolidated duplicate nested-key iteration logic into `adapters/_nested_keys.py`.
- Reduced cyclomatic complexity in `DefaultPathResolver` using Strategy pattern.
- Trimmed verbose docstrings to improve maintainability index scores.

## [3.0.0] - 2025-11-25

### Breaking Changes

- **Environment variable prefix format changed** - The environment variable prefix now uses triple underscore (`___`) as the separator between the slug prefix and configuration keys, instead of a single underscore. This change clearly distinguishes the application prefix from section/key separators (which use double underscores `__`).

  **Before (v2.x):**
  ```bash
  # Slug: "myapp" → Prefix: "MYAPP_"
  MYAPP_DATABASE__HOST=localhost
  MYAPP_DATABASE__PORT=5432
  MYAPP_SERVICE__TIMEOUT=30
  ```

  **After (v3.0):**
  ```bash
  # Slug: "myapp" → Prefix: "MYAPP___"
  MYAPP___DATABASE__HOST=localhost
  MYAPP___DATABASE__PORT=5432
  MYAPP___SERVICE__TIMEOUT=30
  ```

### Why This Change?

The new format makes it unambiguous where the prefix ends and the configuration path begins:
- `PREFIX___SECTION__SUBSECTION__KEY=value`
- Triple underscore (`___`) = prefix separator
- Double underscore (`__`) = nesting separator

This eliminates potential confusion when slugs contain underscores (e.g., `my_app` would have been `MY_APP_DATABASE__HOST`, making it unclear if `APP` was part of the prefix or a section name).

### Migration Guide

1. **Update all environment variables** - Add an extra two underscores after your prefix:
   - `MYAPP_DATABASE__HOST` → `MYAPP___DATABASE__HOST`
   - `CONFIG_KIT_SERVICE__TIMEOUT` → `CONFIG_KIT___SERVICE__TIMEOUT`

2. **Update shell scripts** - If you use `env-prefix` CLI command, note that it now returns the prefix with the trailing `___`:
   ```bash
   # Before: returns "MYAPP"
   # After: returns "MYAPP___"
   prefix=$(lib_layered_config env-prefix myapp)
   export ${prefix}DATABASE__HOST=localhost  # No extra underscore needed
   ```

3. **Update Python code** - If you use `default_env_prefix()`:
   ```python
   from lib_layered_config import default_env_prefix

   prefix = default_env_prefix("myapp")  # Returns "MYAPP___"
   os.environ[f"{prefix}DATABASE__HOST"] = "localhost"  # No extra underscore
   ```

### Changed

- `default_env_prefix()` now returns the slug in uppercase followed by `___` (e.g., `"MYAPP___"`)
- `_normalize_prefix()` ensures prefixes end with `___` instead of `_`
- CLI `env-prefix` command output now includes the `___` suffix
- Example `.env` templates now use the new format

### Documentation

- Updated README.md with new prefix format throughout all examples
- Updated all environment variable examples to use `PREFIX___SECTION__KEY` format
- Added explanation of why triple underscore was chosen as the separator

## [2.0.0] - 2025-11-20

### Breaking Changes

- **XDG Base Directory Specification compliance on Linux** - System-wide application configuration now defaults to `/etc/xdg/{slug}/` instead of `/etc/{slug}/` to follow the XDG Base Directory Specification.

### Changed

- **Path resolution (Linux)**: The path resolver now checks both `/etc/xdg/{slug}/` (XDG-compliant, checked first) and `/etc/{slug}/` (legacy, fallback) when reading configuration. This provides backward compatibility with existing installations.
- **Deployment (Linux)**: The `deploy_config()` function and `deploy` CLI command now deploy application-level configuration to `/etc/xdg/{slug}/config.toml` by default on Linux systems.
- **Host configuration (Linux)**: Host-specific configuration now deploys to `/etc/xdg/{slug}/hosts/{hostname}.toml` instead of `/etc/{slug}/hosts/{hostname}.toml`.
- **Example generation (Linux/POSIX)**: The `generate_examples()` function now creates example files in `xdg/{slug}/` for system-wide configuration and `home/{slug}/` for user-level configuration.

### Migration Guide

**For existing installations:**
- Configurations in `/etc/{slug}/` will continue to work (backward compatibility)
- New deployments will use `/etc/xdg/{slug}/`
- To migrate: move existing files from `/etc/{slug}/` to `/etc/xdg/{slug}/`
- Both locations are checked during reading, with `/etc/xdg/{slug}/` taking precedence

**Platform-specific behavior:**
- Linux: Uses `/etc/xdg/{slug}/` (system-wide) and `~/.config/{slug}/` (user-level)
- macOS: No change, continues to use `/Library/Application Support/{vendor}/{app}/`
- Windows: No change, continues to use `%ProgramData%\{vendor}\{app}\`

### Documentation

- Updated README.md with XDG-compliant paths throughout all examples
- Added backward compatibility notes explaining dual-path checking
- Updated all CLI command examples to reflect new default paths

## [1.1.1] - 2025-11-11

### Documentation

- **Major README enhancement** - Expanded from 787 to 2,800+ lines with comprehensive documentation for all functions, CLI commands, and parameters.

#### New Sections Added

- **Understanding Key Identifiers: Vendor, App, and Slug** - Detailed explanation of the three identifiers, their purposes, platform-specific usage, and naming best practices. Includes cross-platform path examples for Linux, macOS, and Windows.

- **Configuration File Structure** - Complete 200+ line example TOML configuration file demonstrating:
  - Top-level keys, sections, and nested sections
  - Arrays and all supported data types (strings, integers, floats, booleans, dates)
  - Real-world configuration patterns (database, service, logging, API, cache, email, monitoring)
  - Access patterns showing Python code, CLI usage, and environment variable mapping
  - Equivalent JSON and YAML representations

- **File Overwrite Behavior** - Comprehensive explanation of the `deploy` command's safe-by-default behavior:
  - Default behavior: creates new files, handles conflicts interactively (protects user customizations)
  - Force flag behavior: backs up existing files and overwrites
  - Visual decision flow diagram
  - 4 practical scenarios with examples
  - Best practices (DO's and DON'Ts) for safe deployment
  - Python API equivalents

#### Enhanced API Documentation

- **Config Class Methods** (6 methods, 23 examples):
  - `get()`: 3 examples showing basic lookups, handling missing keys, and deep nested paths
  - `origin()`: 3 examples for provenance checking, debugging precedence, and security validation
  - `as_dict()`: 2 examples for serialization and testing
  - `to_json()`: 2 examples for pretty-printing and compact output
  - `with_overrides()`: 2 examples for environment-specific configs and feature flags
  - `[key]` access: 2 examples for direct access and iteration

- **Core Functions** (7 functions, 31 examples):
  - `read_config()`: 5 examples from basic usage to complete production setup
  - `read_config_json()`: 3 examples for APIs, audit tools, and logging
  - `read_config_raw()`: 3 examples for templates, validation, and runtime overrides
  - `default_env_prefix()`: 3 examples for documentation generation and validation
  - `deploy_config()`: 5 examples for system-wide, user-specific, and host-specific deployment
  - `generate_examples()`: 5 examples including CI/CD validation
  - `i_should_fail()`: Testing error handling example

#### Enhanced CLI Documentation

Each CLI command now includes:
- Detailed parameter tables with type, required status, default values, and valid choices
- 4-6 real-world examples per command with expected outputs
- Clear explanations of when and why to use each example

- **`read` command**: 6 examples covering human-readable output, JSON for automation, provenance auditing, format preferences, defaults files, and debugging with environment variables

- **`deploy` command**: 6 examples for installation, user configuration, multiple targets, cross-platform deployment, host-specific configs, and safe deployment patterns

- **`generate-examples` command**: 6 examples for documentation generation, cross-platform support, updates, CI/CD validation, and onboarding workflows

- **`env-prefix` command**: 4 examples for checking prefixes, generating documentation, validation scripts, and test environment setup

- **`read-json` command**: Enhanced with API endpoint and audit tool examples

#### Parameter Documentation Improvements

All functions and CLI commands now document:
- Complete parameter lists with types (string, path, bool, int, etc.)
- Required vs. optional status clearly marked
- Default values explicitly stated
- Valid values for all choice/enum parameters (e.g., "app", "host", "user" for targets; "posix", "windows" for platforms)
- Return types and error conditions
- Platform-specific behaviors

#### Additional Improvements

- Updated Table of Contents to include all new sections
- Added environment variable naming pattern documentation with examples
- Included visual structure diagrams showing nested configuration as JSON
- Cross-referenced Python API and CLI equivalents throughout
- Added security considerations (e.g., where to store secrets)
- Included integration examples with Flask, jq, pytest, and other tools

## [1.1.0] - 2025-10-13

- Refactor CLI metadata commands (`info`, `--version`) to read from the
  statically generated `__init__conf__` module, removing runtime
  `importlib.metadata` lookups.
- Update CLI entrypoint to use `lib_cli_exit_tools.cli_session` for traceback
  management, keeping the shared configuration in sync with the newer
  `lib_cli_exit_tools` API without manual state restoration.
- Retire the `lib_layered_config.cli._default_env_prefix` compatibility export;
  import `default_env_prefix` from `lib_layered_config.core` instead.
- Refresh dependency baselines to the latest stable releases (rich-click 1.9.3,
  codecov-cli 11.2.3, PyYAML 6.0.3, ruff 0.14.0, etc.) and mark dataclasses with
  `slots=True` where appropriate to embrace Python 3.13 idioms.
- Simplify the CI notebook smoke test to rely on upstream nbformat behaviour,
  dropping compatibility shims for older notebook metadata schemas.

## [1.0.0] - 2025-10-09

- Add optional `default_file` support to the composition root and CLI so baseline configuration files load ahead of layered overrides.
- Refactor layer orchestration into `lib_layered_config._layers` to keep `core.py` small and more maintainable.
- Align Windows deployment with runtime path resolution by honouring `LIB_LAYERED_CONFIG_APPDATA` even when the directory is missing and falling back to `%LOCALAPPDATA%` only when necessary.
- Expand the test suite to cover CLI metadata helpers, layer fallbacks, and default-file precedence; raise the global coverage bar to 90%.
- Document the `default_file` usage pattern in the README and clarify that deployment respects the same environment overrides as the reader APIs.
- Raise the minimum supported Python version to 3.13; retire the legacy Conda, Nix, and Homebrew automation in favour of the PyPI-first build (now verified via pipx/uv in CI).

## [0.1.0] - 2025-09-26
- Implement core layered configuration system (`read_config`, immutable `Config`, provenance tracking).
- Add adapters for OS path resolution, TOML/JSON/YAML loaders, `.env` parser, and environment variables.
- Provide example generators, logging/observability helpers, and architecture enforcement via import-linter.
- Reset packaging manifests (PyPI, Conda, Nix, Homebrew) to the initial release version with Python ≥3.12.
- Refine the CLI into micro-helpers (`deploy`, `generate-examples`, provenance-aware `read`) with
  shared traceback settings and JSON formatting utilities.
- Bundle `tomli>=2.0.1` across all packaging targets (PyPI, Conda, Brew, Nix) so Python 3.10 users
  receive a TOML parser without extra steps; newer interpreters continue to use the stdlib module.
