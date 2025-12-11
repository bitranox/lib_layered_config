# Changelog

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
  - Default behavior: creates new files, skips existing files (protects user customizations)
  - Force flag behavior: overwrites existing files without warning
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
