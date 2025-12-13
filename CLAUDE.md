# Claude Code Guidelines for lib_layered_config

## Session Initialization

When starting a new session, read and apply the following system prompt files from `/media/srv-main-softdev/projects/softwarestack/systemprompts`:

### Core Guidelines (Always Apply)
- `core_programming_solid.md`

### Bash-Specific Guidelines
When working with Bash scripts:
- `core_programming_solid.md`
- `bash_clean_architecture.md`
- `bash_clean_code.md`
- `bash_small_functions.md`

### Python-Specific Guidelines
When working with Python code:
- `core_programming_solid.md`
- `python_solid_architecture_enforcer.md`
- `python_clean_architecture.md`
- `python_clean_code.md`
- `python_small_functions_style.md`
- `python_libraries_to_use.md`
- `python_structure_template.md`

### Additional Guidelines
- `self_documenting.md`
- `self_documenting_template.md`
- `python_jupyter_notebooks.md`
- `python_testing.md`

## Project Structure

```
lib_layered_config/
├── .github/
│   └── workflows/              # GitHub Actions CI/CD workflows
├── docs/                       # Project documentation
│   └── systemdesign/           # System design documents
├── notebooks/                  # Jupyter notebooks for experiments
│   └── Quickstart.ipynb        # Getting started notebook
├── scripts/                    # Build and automation scripts
│   ├── build.py               # Build wheel/sdist
│   ├── bump.py                # Version bump (generic)
│   ├── bump_major.py          # Bump major version
│   ├── bump_minor.py          # Bump minor version
│   ├── bump_patch.py          # Bump patch version
│   ├── bump_version.py        # Version bump utilities
│   ├── clean.py               # Clean build artifacts
│   ├── cli.py                 # CLI for scripts
│   ├── dependencies.py        # Dependency management
│   ├── dev.py                 # Development install
│   ├── help.py                # Show help
│   ├── install.py             # Install package
│   ├── menu.py                # Interactive TUI menu
│   ├── push.py                # Git push
│   ├── release.py             # Create releases
│   ├── run_cli.py             # Run CLI
│   ├── target_metadata.py     # Metadata generation
│   ├── test.py                # Run tests with coverage
│   ├── toml_config.py         # TOML configuration utilities
│   ├── version_current.py     # Print current version
│   └── _utils.py              # Shared utilities
├── src/
│   └── lib_layered_config/    # Main Python package
│       ├── __init__.py        # Package initialization
│       ├── __init__conf__.py  # Configuration constants
│       ├── __main__.py        # CLI entry point
│       ├── core.py            # Core facade/API
│       ├── _layers.py         # Layer loading utilities
│       ├── _platform.py       # Platform detection
│       ├── observability.py   # Logging and observability
│       ├── testing.py         # Test utilities
│       ├── py.typed           # PEP 561 marker
│       ├── adapters/          # Adapter layer (infrastructure)
│       │   ├── dotenv/        # .env file loading
│       │   ├── env/           # Environment variable loading
│       │   ├── file_loaders/  # TOML/YAML file loaders + .d directory expansion
│       │   ├── path_resolvers/ # Platform-specific path resolution
│       │   └── _nested_keys.py # Nested key handling
│       ├── application/       # Application layer (use cases)
│       │   ├── merge.py       # Configuration merging logic
│       │   └── ports.py       # Interface definitions
│       ├── cli/               # CLI commands
│       │   ├── common.py      # Shared CLI utilities
│       │   ├── constants.py   # CLI constants
│       │   ├── deploy.py      # Deploy command
│       │   ├── fail.py        # Fail command (testing)
│       │   ├── generate.py    # Generate command
│       │   ├── info.py        # Info command
│       │   └── read.py        # Read command
│       ├── domain/            # Domain layer (core business logic)
│       │   ├── config.py      # Configuration domain model
│       │   ├── errors.py      # Domain exceptions
│       │   └── identifiers.py # Value objects for identifiers
│       └── examples/          # Example configurations
│           ├── deploy.py      # Deploy example
│           └── generate.py    # Generate example
├── tests/                     # Test suite
│   ├── adapters/              # Adapter tests
│   ├── application/           # Application layer tests
│   ├── benchmark/             # Performance benchmarks
│   ├── domain/                # Domain layer tests
│   ├── e2e/                   # End-to-end tests
│   ├── examples/              # Example tests
│   ├── support/               # Test support utilities
│   ├── unit/                  # Unit tests
│   └── conftest.py            # Pytest fixtures
├── CLAUDE.md                  # Claude Code guidelines (this file)
├── CHANGELOG.md               # Version history
├── CONTRIBUTING.md            # Contribution guidelines
├── DEVELOPMENT.md             # Development setup guide
├── LICENSE                    # MIT License
├── Makefile                   # Make targets for common tasks
├── pyproject.toml             # Project metadata & dependencies
├── codecov.yml                # Codecov configuration
└── README.md                  # Project overview
```

## Versioning & Releases

- **Single Source of Truth**: Package version is in `pyproject.toml` (`[project].version`)
- **Version Bumps**: update `pyproject.toml`, `CHANGELOG.md` and update the constants in `src/lib_layered_config/__init__conf__.py` according to `pyproject.toml`
    - Automation rewrites `src/lib_layered_config/__init__conf__.py` from `pyproject.toml`, so runtime code imports generated constants instead of querying `importlib.metadata`.
    - After updating project metadata (version, summary, URLs, authors) run `make test` (or `python -m scripts.test`) to regenerate the metadata module before committing.
- **Release Tags**: Format is `vX.Y.Z` (push tags for CI to build and publish)

## Common Make Targets

| Target            | Description                                                                     |
|-------------------|---------------------------------------------------------------------------------|
| `build`           | Build wheel/sdist artifacts                                                     |
| `bump`            | Bump version (VERSION=X.Y.Z or PART=major\|minor\|patch) and update changelog  |
| `bump-major`      | Increment major version ((X+1).0.0)                                            |
| `bump-minor`      | Increment minor version (X.Y.Z → X.(Y+1).0)                                    |
| `bump-patch`      | Increment patch version (X.Y.Z → X.Y.(Z+1))                                    |
| `clean`           | Remove caches, coverage, and build artifacts (includes `dist/` and `build/`)   |
| `dev`             | Install package with dev extras                                                |
| `help`            | Show make targets                                                              |
| `install`         | Editable install                                                               |
| `menu`            | Interactive TUI menu                                                           |
| `push`            | Commit changes and push to GitHub (no CI monitoring)                           |
| `release`         | Tag vX.Y.Z, push, sync packaging, run gh release if available                  |
| `run`             | Run module entry (`python -m ... --help`)                                      |
| `test`            | Lint, format, type-check, run tests with coverage, upload to Codecov           |
| `version-current` | Print current version from `pyproject.toml`                                    |

## Coding Style & Naming Conventions

Follow the guidelines in `python_clean_code.md` for all Python code.

## Architecture Overview

This library follows Clean Architecture with four layers:
- **domain/**: Domain layer with configuration models, errors, and identifiers (no external dependencies)
- **application/**: Application services with merging logic and port interfaces
- **adapters/**: Infrastructure layer with file loaders, path resolvers, and environment adapters
- **cli/**: Command-line interface commands

Import rules (enforced by import-linter):
- `domain` cannot import from `application`, `adapters`, `cli`, or `core`
- `application` cannot import from `cli`
- Layer order: `domain` → `application` → `adapters` → root package

Apply principles from `python_clean_architecture.md` when designing and implementing features.

## Configuration Loading Features

### `.d` Directory Pattern
Any configuration file can have a companion `.d` directory for split configuration:
- `config.toml` → `config.d/` (not `config.toml.d/`)
- `defaults.toml` → `defaults.d/`

**Reading behavior:**
- Base file loaded first (lowest precedence within layer)
- `.d` directory files loaded in lexicographic order (e.g., `10-db.toml`, `20-cache.yaml`)
- Mixed formats allowed in `.d` directory (TOML, YAML, JSON)
- Both base file and `.d` directory are optional (either can exist independently)
- Works with `default_file` parameter and all layer types (app, host, user)
- Non-config files (README.md, etc.) are **ignored** during parsing

**Deployment behavior:**
- When deploying `config.toml`, the companion `config.d/` is automatically deployed
- ALL files in `.d` directory are deployed (including README.md, notes.txt, etc.)
- This preserves documentation and supporting files
- JSON output includes: `dot_d_created`, `dot_d_overwritten`, `dot_d_skipped`, `dot_d_backups`

**Implementation files:**
- `adapters/file_loaders/_dot_d.py` - `expand_dot_d()` for reading (filters by extension)
- `_layers.py` - `_load_entry_with_dot_d()` integration
- `adapters/path_resolvers/_base.py` - `collect_layer()` yields `config.toml` when `config.d/` exists
- `examples/deploy.py` - `_collect_dot_d_sources()` for deployment (all files)
- `cli/deploy.py` - `_format_results()` includes `.d` file results

## Security & Configuration

- `.env` files are for local tooling only (CodeCov tokens, etc.)
- **NEVER** commit secrets to version control
- Rich logging should sanitize payloads before rendering

## Documentation & Translations

### Web Documentation
- Update only English docs under `/website/docs`
- Other languages are translated automatically
- When in doubt, ask before modifying non-English documentation

### App UI Strings (i18n)
- Update only `sources/_locales/en` for string changes
- Other languages are translated automatically
- When in doubt, ask before modifying non-English locales

## Commit & Push Policy

### Pre-Push Requirements
- **Always run `make test` before pushing** to avoid lint/test breakage
- Ensure all tests pass and code is properly formatted

### Post-Push Monitoring
- Monitor GitHub Actions for errors after pushing
- Attempt to correct any CI/CD errors that appear

## Claude Code Workflow

When working on this project:
1. Read relevant system prompts at session start
2. Apply appropriate coding guidelines based on file type
3. Run `make test` before commits
4. Follow versioning guidelines for releases
5. Monitor CI after pushing changes
