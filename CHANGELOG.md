# Changelog

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
