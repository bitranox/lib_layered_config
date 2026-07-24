# lib_layered_config

<!-- Badges -->
[![CI](https://github.com/bitranox/lib_layered_config/actions/workflows/default_cicd_public.yml/badge.svg)](https://github.com/bitranox/lib_layered_config/actions/workflows/default_cicd_public.yml)
[![CodeQL](https://github.com/bitranox/lib_layered_config/actions/workflows/codeql.yml/badge.svg)](https://github.com/bitranox/lib_layered_config/actions/workflows/codeql.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Open in Codespaces](https://img.shields.io/badge/Codespaces-Open-blue?logo=github&logoColor=white&style=flat-square)](https://codespaces.new/bitranox/lib_layered_config?quickstart=1)
[![PyPI](https://img.shields.io/pypi/v/lib-layered-config.svg)](https://pypi.org/project/lib-layered-config/)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/lib-layered-config.svg)](https://pypi.org/project/lib-layered-config/)
[![Code Style: Ruff](https://img.shields.io/badge/Code%20Style-Ruff-46A3FF?logo=ruff&labelColor=000)](https://docs.astral.sh/ruff/)
[![codecov](https://codecov.io/gh/bitranox/lib_layered_config/graph/badge.svg)](https://codecov.io/gh/bitranox/lib_layered_config)
[![Maintainability](https://qlty.sh/gh/bitranox/projects/lib_layered_config/maintainability.svg)](https://qlty.sh/gh/bitranox/projects/lib_layered_config)
[![security: bandit](https://img.shields.io/badge/security-bandit-yellow.svg)](https://github.com/PyCQA/bandit)

## Config is annoying

Here is the odd thing about configuration bugs: hardly any of them are about the value. They are about authorship. By the time a setting reaches your program it has passed through as many as six hands - the defaults you shipped, a file in `/etc`, a per-host tweak, something in the user's home directory, a `.env`, and an environment variable a colleague exported months ago and forgot - and any hand along the way may have changed it. The number you finally read is the last whisper in a long game of telephone, and the library you read it with took no notes. So when the value is wrong, you are not debugging code. You are interviewing witnesses.

The sensible-looking shortcuts are exactly the ones that turn on you:

- Read `os.environ.get("TIMEOUT", 30)` in one module and a `config.toml` in another, and the real timeout is settled by whichever line ran first. Nobody wins the argument; nobody is even told there was one.
- Hard-code `/etc/myapp/` because that is plainly where config lives - on Linux. On the macOS and Windows machines that make up most of your users, it lives somewhere else entirely.
- Trust `"false"` from a file as a boolean; a non-empty string is truthy, so you have just shipped with the safety switched off.
- Let a password rest in the config file, let the config file drift into git, and you have handed a secret a permanent home address.
- Assign to the shared settings dict from three call-frames deep, and "the configuration" now means different things depending on what ran when.

None of these are hard to fix once. They are hard to fix *forever*, because the single fact you need the moment it breaks - who set this value, and from where - was thrown away at the door.

## Configuration, with a paper trail

`lib_layered_config` begins with the part every other approach discards: the paperwork. It deep-merges the six layers - `defaults -> app -> host -> user -> dotenv -> env` - into one **immutable** object, in a precedence that never shifts, and it keeps the receipt. Ask for a value and it answers; ask *where the value came from* and it names the exact layer and file. The witness interview collapses into a lookup.

What that buys you:

- **One frozen object.** `read_config(...)` returns a `Config` nothing downstream can mutate, so your program cannot quietly begin to disagree with itself.
- **Every value carries its origin.** `config.origin("service.timeout")` reports the layer and the path it came from. Debugging stops being a seance.
- **The paths are already sorted.** Linux (XDG), macOS, and Windows locations are resolved for you, so you never bake someone else's `/etc` into your code.
- **One name switches the whole environment.** Profiles keep test, staging, and production in separate trees; ask for `profile="production"` and you get production's config, not a hand-merged guess at it.
- **Secrets sit above the file, not inside it.** Environment variables and `.env` outrank the committed config, which therefore holds shape rather than passwords - and the CLI can redact on the way out.

Same engine from either side: `from lib_layered_config import read_config` as a library, or a `lib_layered_config` command that reads, deploys, and scaffolds configuration without a line of Python.

In one sentence: a cross-platform configuration loader that deep-merges application defaults, host overrides, user profiles, `.env` files, and environment variables into a single immutable object. The core follows Clean Architecture boundaries so adapters (filesystem, dotenv, environment) stay isolated from the domain model while the CLI mirrors the same orchestration.

[License](LICENSE) | [AI stance](ai-stance.md) | [AI transparency](ai-transparency.md)

## Table of Contents

### Getting Started
- [Key Features](#key-features)
- [Installation](#installation)
- [Quick Start](#quick-start)

### Core Concepts
- [Understanding Key Identifiers](docs/identifiers.md) - Vendor, App, Slug, Profile
- [Configuration Profiles](docs/identifiers.md#configuration-profiles)
- [Configuration File Structure](docs/config-file-structure.md)
- [Configuration Sources & Precedence](#configuration-sources--precedence)

### Command Line Interface
Full reference: **[docs/cli-reference.md](docs/cli-reference.md)**
- [CLI Command Summary](docs/cli-reference.md#command-summary)
- [`read` / `read-json`](docs/cli-reference.md#read) - Load and inspect configuration
- [`deploy`](docs/cli-reference.md#deploy) - Deploy configuration files
- [`generate-examples`](docs/cli-reference.md#generate-examples) - Scaffold example trees
- [`env-prefix`](docs/cli-reference.md#env-prefix) - Compute environment prefix
- [`info` / `fail`](docs/cli-reference.md#info) - Diagnostics

### Python API
Full reference: **[docs/python-api.md](docs/python-api.md)**
- [Layer Enum](docs/python-api.md#layer-enum)
- [Config Class](docs/python-api.md#config-class)
- [`read_config`](docs/python-api.md#read_config) / [`read_config_json`](docs/python-api.md#read_config_json) / [`read_config_raw`](docs/python-api.md#read_config_raw)
- [`deploy_config`](docs/python-api.md#deploy_config)
- [`generate_examples` (Python)](docs/python-api.md#generate_examples)
- [`default_env_prefix`](docs/python-api.md#default_env_prefix)
- [Profile Validation](docs/python-api.md#profile-validation)
- [Permission Constants](docs/python-api.md#permission-constants)

### Deployment & Security
- [File Permissions](docs/cli-reference.md#-file-permissions)
- [Security Best Practices](docs/cli-reference.md#-security-best-practices)
- [Recommendations for Sensitive Data](docs/cli-reference.md#-recommendations-for-sensitive-data)
- [Example Generation & Deployment](#example-generation--deployment)
- [Deploying with `.d` Directories](#deploying-with-d-directories)
- [User Files Preservation](#user-files-are-preserved-during-deployment)

### Reference
- [Provenance & Observability](#provenance--observability)
- [Architecture Overview](#architecture-overview)
- [Further Documentation](#further-documentation)
- [Development](#development)
- [License](#license)
- [AI stance](ai-stance.md) and [AI transparency](ai-transparency.md) - how this project was built, and who answers for it

## Key Features

- **Deterministic layering** - precedence is always `defaults → app → host → user → dotenv → env`.
- **Immutable value object** - returned `Config` prevents accidental mutation and exposes dotted-path helpers.
- **Provenance tracking** - every key reports the layer and path that produced it.
- **Cross-platform path discovery** - Linux (XDG), macOS, and Windows layouts with environment overrides for tests.
- **Configuration profiles** - test, staging, and production live in separate trees; select one by name (`profile="production"`) instead of hand-merging environments.
- **`.d` directory support** - split configuration into multiple files using the Linux `.d` pattern (e.g., `config.d/10-database.toml`). Supports mixed formats (TOML, YAML, JSON) in the same directory.
- **Easy deployment** - deploy configs to app, host, and user layers with smart conflict handling that protects user customizations through automatic backups (`.bak`) and UCF files (`.ucf`) for safe CI/CD updates.
- **Fast parsing** - uses `rtoml` (Rust-based) for ~5x faster TOML parsing than stdlib `tomllib`.
- **Extensible formats** - TOML and JSON are built-in; YAML is available via the optional `yaml` extra.
- **Automation-friendly CLI** - inspect, deploy, or scaffold configurations without writing Python.
- **Structured logging** - adapters emit trace-aware events without polluting the domain layer.
- **Built for AI agents too** - the library is designed to be driven by an LLM agent as well as a human, and ships a Claude Code skill (`skills/python-layered-config/`) that teaches an agent how to install it, design config files, compute the env-var override names, manage profiles, and trace where each setting came from, across Linux, macOS, and Windows. Install it with `/plugin marketplace add bitranox/lib_layered_config` then `/plugin install lib_layered_config`.

## Installation

```bash
pip install lib_layered_config
# or with optional YAML support
pip install "lib_layered_config[yaml]"
```

> **Requires Python 3.10+** - uses `rtoml` (Rust-based TOML parser) for ~5x faster parsing than stdlib `tomllib`.
>
> Install the optional `yaml` extra only when you actually ship `.yml` files to keep the dependency footprint small.

For local development add tooling extras:

```bash
pip install "lib_layered_config[dev]"
```

## Quick Start

```python
from lib_layered_config import read_config

config = read_config(vendor="Acme", app="ConfigKit", slug="config-kit")
print(config.get("service.timeout", default=30))
print(config.origin("service.timeout"))
```

CLI equivalent (human readable by default):

```bash
lib_layered_config read --vendor Acme --app ConfigKit --slug config-kit
```

JSON output including provenance:

```bash
lib_layered_config read --vendor Acme --app ConfigKit --slug config-kit --format json
# or
lib_layered_config read-json --vendor Acme --app ConfigKit --slug config-kit
```

## Understanding Key Identifiers: Vendor, App, Slug, and Profile

Four identifiers decide *where* your configuration lives: **vendor** and **app** (used in
the macOS and Windows paths), **slug** (the Linux directory and the environment-variable
prefix), and an optional **profile** (test / staging / production, each in its own tree).
All four are validated for cross-platform filesystem safety.

Full detail - platform path tables, naming rules, profiles, and validation - is in
**[docs/identifiers.md](docs/identifiers.md)**.

```python
from lib_layered_config import read_config

# vendor/app -> macOS + Windows paths; slug -> Linux paths + the MYAPP___ env prefix
config = read_config(vendor="Acme", app="ConfigKit", slug="config-kit", profile="production")
```

## Configuration File Structure

Configuration files are TOML by default (JSON and YAML are also supported). Top-level keys,
`[section]` tables, nested subtables, and arrays all map onto dotted-path access
(`config.get("database.pool.size")`) and onto environment-variable overrides
(`MYAPP___DATABASE__POOL__SIZE`).

The full annotated example - every structural feature and how each maps to Python access and
to env vars - is in **[docs/config-file-structure.md](docs/config-file-structure.md)**.

```toml
debug = true

[database]
host = "localhost"

[database.pool]
size = 20
```

## Configuration Sources & Precedence

Later layers override earlier ones **per key** while leaving unrelated keys untouched.

| Precedence | Layer      | Description                                                           |
|------------|------------|-----------------------------------------------------------------------|
| 0          | `defaults` | Optional baseline file provided via the API/CLI `--default-file` flag |
| 1          | `app`      | System-wide defaults (e.g. `/etc/<slug>/...`)                         |
| 2          | `host`     | Machine-specific overrides (`hosts/<hostname>.toml`)                  |
| 3          | `user`     | Per-user settings (XDG, Application Support, AppData)                 |
| 4          | `dotenv`   | First `.env` found via upward search plus platform extras             |
| 5          | `env`      | Process environment with namespacing and `__` nesting                 |

Use the optional defaults layer when you want one explicitly-provided file to seed configuration before host/user overrides apply.

Important directories (overridable via environment variables):

### Linux
- `/etc/xdg/<slug>/config.toml` (XDG system-wide, checked first)
- `/etc/xdg/<slug>/config.d/*.{toml,json,yaml,yml}`
- `/etc/<slug>/config.toml` (legacy fallback)
- `/etc/<slug>/config.d/*.{toml,json,yaml,yml}`
- `/etc/xdg/<slug>/hosts/<hostname>.toml` or `/etc/<slug>/hosts/<hostname>.toml`
- `/etc/xdg/<slug>/hosts/<hostname>.d/*.{toml,json,yaml,yml}` (host-specific split config)
- `$XDG_CONFIG_HOME/<slug>/config.toml` (user; falls back to `~/.config/<slug>/config.toml`)
- `$XDG_CONFIG_HOME/<slug>/config.d/*.{toml,json,yaml,yml}`
- `.env` search: current directory upwards + `$XDG_CONFIG_HOME/<slug>/.env`

### macOS
- `/Library/Application Support/<Vendor>/<App>/config.toml` (system-wide app layer)
- `/Library/Application Support/<Vendor>/<App>/config.d/*.{toml,json,yaml,yml}`
- `/Library/Application Support/<Vendor>/<App>/hosts/<hostname>.toml`
- `/Library/Application Support/<Vendor>/<App>/hosts/<hostname>.d/*.{toml,json,yaml,yml}`
- `~/Library/Application Support/<Vendor>/<App>/config.toml` (user layer)
- `~/Library/Application Support/<Vendor>/<App>/config.d/*.{toml,json,yaml,yml}`
- `.env` search: current directory upwards + `~/Library/Application Support/<Vendor>/<App>/.env`

### Windows
- `%ProgramData%\<Vendor>\<App>\config.toml` (system-wide app layer)
- `%ProgramData%\<Vendor>\<App>\config.d\*.{toml,json,yaml,yml}`
- `%ProgramData%\<Vendor>\<App>\hosts\%COMPUTERNAME%.toml`
- `%ProgramData%\<Vendor>\<App>\hosts\%COMPUTERNAME%.d\*.{toml,json,yaml,yml}`
- `%APPDATA%\<Vendor>\<App>\config.toml` (user layer; resolver order: `LIB_LAYERED_CONFIG_APPDATA` → `%APPDATA%`; falls back to `%LOCALAPPDATA%`)
- `%APPDATA%\<Vendor>\<App>\config.d\*.{toml,json,yaml,yml}`
- `.env` search: current directory upwards + `%APPDATA%\<Vendor>\<App>\.env`

Environment overrides: `LIB_LAYERED_CONFIG_ETC`, `LIB_LAYERED_CONFIG_PROGRAMDATA`, `LIB_LAYERED_CONFIG_APPDATA`, `LIB_LAYERED_CONFIG_LOCALAPPDATA`, `LIB_LAYERED_CONFIG_MAC_APP_ROOT`, `LIB_LAYERED_CONFIG_MAC_HOME_ROOT`. Both the runtime readers and the `deploy` helper honour these variables so generated files land in the same directories that `read_config` inspects.

**Fallback note:** Whenever a path is marked as a fallback, the resolver first consults the documented environment overrides (`LIB_LAYERED_CONFIG_*`, `$XDG_CONFIG_HOME`, `%APPDATA%`, etc.). If those variables are unset or the computed directory does not exist, it switches to the stated fallback location (`~/.config`, `%LOCALAPPDATA%`, ...). This keeps local installs working without additional environment configuration while still allowing operators to steer resolution explicitly.

### The `.d` Directory Pattern

Any configuration file can have a companion `.d` directory for split configuration. This follows the common Linux pattern (similar to `/etc/apt/sources.list.d/` or `/etc/sudoers.d/`).

**Naming convention:** The `.d` directory name is the filename without extension plus `.d`:
- `config.toml` → `config.d/`
- `defaults.toml` → `defaults.d/`
- `myapp.yaml` → `myapp.d/`
- `settings.json` → `settings.d/`

This means **all formats share the same `.d` directory** - `config.toml`, `config.yaml`, and `config.json` all use `config.d/`.

**How it works:**
1. The loader first loads the base file (e.g., `config.toml`) if present
2. Then loads all files from the `.d` directory (e.g., `config.d/`) in **lexicographic order**
3. Only files with supported extensions are loaded: `.toml`, `.json`, `.yaml`, `.yml`
4. Files are merged in order, so later files override earlier ones
5. **Both the base file and `.d` directory are optional** - either can exist independently

**Supported at all layers:** The `.d` directory pattern works for **app**, **host**, and **user** layers:

| Layer    | Base File                             | Companion `.d` Directory            |
|----------|---------------------------------------|-------------------------------------|
| **app**  | `/etc/xdg/myapp/config.toml`          | `/etc/xdg/myapp/config.d/`          |
| **host** | `/etc/xdg/myapp/hosts/server-01.toml` | `/etc/xdg/myapp/hosts/server-01.d/` |
| **user** | `~/.config/myapp/config.toml`         | `~/.config/myapp/config.d/`         |

**Host-specific `.d` directories:** Each hostname file can have its own `.d` directory for per-host split configuration:
```
/etc/xdg/myapp/hosts/
├── server-01.toml                    # Host-specific base config
├── server-01.d/                      # Host-specific split config
│   ├── 10-network.toml
│   └── 20-storage.toml
├── server-02.toml
└── server-02.d/
    └── 10-network.toml
```

**File ordering:** Use numeric prefixes to control load order:
```
config.d/
├── 10-base.toml        # Loaded first (lowest precedence)
├── 20-database.yaml    # Loaded second (mixed formats allowed!)
├── 30-logging.json     # Loaded third
└── 99-overrides.toml   # Loaded last (highest precedence within config.d)
```

**Precedence order:**
```
config.toml             # Loaded first (lowest precedence)
config.d/10-base.toml   # Loaded second
config.d/20-db.yaml     # Loaded third
config.d/99-local.toml  # Loaded last (highest precedence)
```

**Use cases:**
- **Package managers** can drop configuration snippets without modifying the main file
- **Automation tools** can add/remove specific settings independently
- **Team workflows** can split configuration by concern (database, logging, features)
- **CI/CD pipelines** can deploy environment-specific overrides as separate files
- **Default files** (`--default-file`) also support `.d` expansion

**Example:**
```bash
# Main config defines defaults
/etc/myapp/config.toml:
  [database]
  host = "localhost"
  port = 5432

# Ops team adds production overrides (can use any supported format)
/etc/myapp/config.d/50-production.toml:
  [database]
  host = "db.prod.example.com"
  pool_size = 20

# Monitoring team adds their settings as YAML
/etc/myapp/config.d/60-monitoring.yaml:
  monitoring:
    enabled: true
    endpoint: "https://metrics.example.com"

# Result: database.host = "db.prod.example.com", database.port = 5432,
#         database.pool_size = 20, monitoring.enabled = true
```

**With default files:**
```python
# defaults.toml and defaults.d/ are both loaded
config = read_config(
    vendor="Acme",
    app="MyApp",
    slug="myapp",
    default_file="./defaults.toml",  # Also checks ./defaults.d/*.{toml,yaml,json}
)
```

**Without base file (`.d` directory only):**
```bash
# No config.toml exists, only config.d/ directory
/etc/myapp/config.d/
├── 10-database.toml
├── 20-cache.toml
└── 30-logging.yaml

# This works! All files from config.d/ are loaded and merged.
```

## CLI Usage

The command-line interface mirrors the Python API: read and inspect configuration, deploy
files across the app/host/user layers, scaffold example trees, and compute environment
prefixes. It also documents the file-overwrite and backup behavior and the per-layer
permission and secret-handling guidance.

The full command reference lives in **[docs/cli-reference.md](docs/cli-reference.md)**.

```bash
lib_layered_config read --vendor Acme --app ConfigKit --slug config-kit
lib_layered_config read --vendor Acme --app ConfigKit --slug config-kit --format json
lib_layered_config deploy --source config.toml --vendor Acme --app ConfigKit --slug config-kit --target user
```

## Python API

`read_config(...)` is the main entry point; it returns an immutable `Config` with
dotted-path access and per-key provenance. The `Config` class, the `Layer` enum, the other
read functions, `deploy_config`, example generation, profile validation, and the permission
constants are all covered in the full reference.

The full API reference lives in **[docs/python-api.md](docs/python-api.md)**.

```python
from lib_layered_config import read_config

config = read_config(vendor="Acme", app="ConfigKit", slug="config-kit")
timeout = config.get("service.timeout", default=30)
print(config.origin("service.timeout"))  # which layer and file set it
```

## Example Generation & Deployment

Use the Python helpers or CLI equivalents:

```python
from pathlib import Path
from lib_layered_config.examples import deploy_config, generate_examples

# copy one file into the system/user layers
# If ./myapp/config.d/ exists, those files are also deployed to each destination's config.d/
paths = deploy_config("./myapp/config.toml", vendor="Acme", app="ConfigKit", targets=("app", "user"))

# scaffold an example tree for documentation
examples = generate_examples(Path("./examples"), slug="config-kit", vendor="Acme", app="ConfigKit")
```

### Deploying with `.d` Directories

When deploying a configuration file, any companion `.d` directory is automatically included:

```bash
# Source structure:
# ./myapp/
# ├── config.toml          # Base configuration
# └── config.d/            # Companion .d directory
#     ├── 10-database.toml
#     └── 20-cache.toml

lib_layered_config deploy --source ./myapp/config.toml --vendor Acme --app MyApp --slug myapp --target app

# Result at /etc/xdg/myapp/:
# ├── config.toml          # Base configuration deployed
# └── config.d/            # .d directory also deployed
#     ├── 10-database.toml
#     └── 20-cache.toml
```

The JSON output includes separate fields for `.d` file results:
- `dot_d_created`: Paths of `.d` files created
- `dot_d_overwritten`: Paths of `.d` files overwritten (with `dot_d_backups`)
- `dot_d_skipped`: Paths of `.d` files skipped (identical content)

**Note:** Deployment copies ALL files from the `.d` directory (including README.md, notes.txt, etc.) to preserve documentation and supporting files. Only config file parsing filters by extension.

### User Files Are Preserved During Deployment

Deployment is **additive** - it only creates or updates files that exist in the source `.d` directory. User-added files in the destination are **never deleted or modified**.

```bash
# Source .d directory:
config.d/
├── 10-database.toml
└── 20-cache.toml

# Destination before deploy (user added custom files):
/etc/xdg/myapp/config.d/
├── 10-database.toml    # ← Will be updated/skipped
├── 20-cache.toml       # ← Will be updated/skipped
├── 50-custom.toml      # ← USER FILE: untouched
└── 99-local.toml       # ← USER FILE: untouched

# After deploy: user files 50-custom.toml and 99-local.toml remain intact
```

### Best Practice: Override in Additional Files

Instead of modifying distributed configuration files directly, **add your customizations in a separate file** with a high numeric prefix:

```bash
# DON'T: Edit the distributed file (changes lost on next deploy)
/etc/xdg/myapp/config.d/10-database.toml  # ← Don't modify this

# DO: Create your own override file (preserved across deploys)
/etc/xdg/myapp/config.d/90-local-overrides.toml  # ← Add your changes here
```

**Why this approach?**
- Your customizations survive application updates and re-deployments
- Clear separation between distributed defaults and local overrides
- Easy to identify what was customized vs. what came from the package
- Rollback is simple: just delete your override file

**Example workflow:**
```toml
# Distributed: /etc/xdg/myapp/config.d/10-database.toml
[database]
host = "localhost"
port = 5432
pool_size = 10

# Your overrides: /etc/xdg/myapp/config.d/90-local-overrides.toml
[database]
host = "db.prod.example.com"
pool_size = 50
# port is inherited from 10-database.toml (5432)
```

## Provenance & Observability

- Every merged key stores metadata (`layer`, `path`, `key`).
- Structured logging lives in `lib_layered_config.observability` (trace-aware `log_debug`, `log_info`, `log_warn`, `log_error`).
- Use `bind_trace_id("abc123")` to correlate CLI/log events with your own tracing.

### Type Conflict Warnings

When a later layer overwrites a scalar value with a mapping (or vice versa), a warning is emitted:

```python
import logging

logging.basicConfig(level=logging.WARNING)

# If user.toml has: service = "disabled"
# And app.toml has:  [service]
#                    timeout = 30
# A WARNING log is emitted: "type_conflict" with details about the key, layers, and types involved
```

This helps identify configuration mismatches where a key changes from a simple value to a nested structure (or the reverse) across layers.

## Architecture Overview

The project follows a Clean Architecture layout so responsibilities remain easy to reason about and test:

| Layer            | Responsibility                                                                       |
|------------------|--------------------------------------------------------------------------------------|
| **Domain**       | Immutable `Config` value object plus error taxonomy                                  |
| **Application**  | Merge policy (`LayerSnapshot`, `merge_layers`) and adapter protocols                 |
| **Adapters**     | Filesystem discovery, structured file loaders, dotenv, and environment ingress       |
| **Composition**  | `core` and `_layers` wire adapters together and expose the public API                |
| **Presentation** | CLI commands, deployment/example helpers, observability utilities, and testing hooks |

Consult [`docs/systemdesign/module_reference.md`](docs/systemdesign/module_reference.md) for a per-module catalogue and traceability back to the system design notes.

## Further Documentation

- [Identifiers and Profiles](docs/identifiers.md) - vendor/app/slug/profile, platform paths, naming rules, validation.
- [Configuration File Structure](docs/config-file-structure.md) - the full annotated config file and its env-var / dotted-path mapping.
- [CLI Reference](docs/cli-reference.md) - every command, flag, the file-overwrite/backup behavior, and permission/secret guidance.
- [Python API Reference](docs/python-api.md) - the `Config` class, `Layer` enum, all read/deploy functions, validation, and constants.
- [CHANGELOG](CHANGELOG.md) - user-facing release notes.
- [CONTRIBUTING](CONTRIBUTING.md) - guidelines for issues, pull requests, and coding style.
- [DEVELOPMENT](DEVELOPMENT.md) - local tooling, recommended workflow, and release checklist.
- [Module Reference](docs/systemdesign/module_reference.md) - architecture-aligned responsibilities per module.
- [LICENSE](LICENSE) - MIT license text.


## Development

```bash
pip install "lib_layered_config[dev]"
make test          # lint + type-check + pytest + coverage (fail-under=90%)
make build         # build wheel / sdist artifacts
make run -- --help # run the CLI via the repo entrypoint
```

The development extra now targets the latest stable releases of the toolchain
(pytest 8.4.2, ruff 0.14.0, codecov-cli 11.2.3, etc.), so upgrading your local
environment before running `make` is recommended.

*Formatting gate:* Ruff formatting runs in check mode during `make test`. Run `ruff format .` (or `pre-commit run --all-files`) before pushing and consider `pre-commit install` to keep local edits aligned.

*Coverage gate:* the maintained test suite must stay ≥90% (see `pyproject.toml`). Add targeted unit tests if you extend functionality.

**Platform notes**

- Windows runners install `pipx` and `uv` automatically in CI; locally ensure `pipx` is on your `PATH` before running `make test` so the wheel verification step succeeds.
- The journald prerequisite step runs only on Linux; macOS/Windows skips it, so there is no extra setup required on those platforms.

### Continuous integration

The GitHub Actions workflow executes three jobs:

- **Test matrix** (Linux/macOS/Windows, Python 3.10-3.13 + latest 3.x) running the same pipeline as `make test`.
- **pipx / uv verification** to prove the built wheel installs cleanly with the common Python app launchers.
- **Notebook smoke test** that executes `notebooks/Quickstart.ipynb` to keep the tutorial in sync using the native nbformat workflow (no compatibility shims required).
- CLI jobs run through `lib_cli_exit_tools.cli_session`, ensuring the `--traceback` flag behaves the same locally and in automation.

Packaging-specific jobs (conda, Nix, Homebrew sync) were retired; the Python packaging metadata in `pyproject.toml` remains the single source of truth.

## License

MIT © Robert Nowotny

---

[License](LICENSE) | [AI stance](ai-stance.md) | [AI transparency](ai-transparency.md)
