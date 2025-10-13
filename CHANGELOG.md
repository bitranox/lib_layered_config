# Changelog

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
