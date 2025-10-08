# lib_layered_config

<!-- Badges -->
[![CI](https://github.com/bitranox/lib_layered_config/actions/workflows/ci.yml/badge.svg)](https://github.com/bitranox/lib_layered_config/actions/workflows/ci.yml)
[![CodeQL](https://github.com/bitranox/lib_layered_config/actions/workflows/codeql.yml/badge.svg)](https://github.com/bitranox/lib_layered_config/actions/workflows/codeql.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Open in Codespaces](https://img.shields.io/badge/Codespaces-Open-blue?logo=github&logoColor=white&style=flat-square)](https://codespaces.new/bitranox/lib_layered_config?quickstart=1)
[![PyPI](https://img.shields.io/pypi/v/lib-layered-config.svg)](https://pypi.org/project/lib-layered-config/)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/lib-layered-config.svg)](https://pypi.org/project/lib-layered-config/)
[![Code Style: Ruff](https://img.shields.io/badge/Code%20Style-Ruff-46A3FF?logo=ruff&labelColor=000)](https://docs.astral.sh/ruff/)
[![codecov](https://codecov.io/gh/bitranox/lib_layered_config/graph/badge.svg)](https://codecov.io/gh/bitranox/lib_layered_config)
[![Maintainability](https://qlty.sh/gh/bitranox/projects/lib_layered_config/maintainability.svg)](https://qlty.sh/gh/bitranox/projects/lib_layered_config)
[![Known Vulnerabilities](https://snyk.io/test/github/bitranox/lib_layered_config/badge.svg)](https://snyk.io/test/github/bitranox/lib_layered_config)

A cross-platform configuration loader that deep-merges application defaults, host overrides, user profiles, `.env` files, and environment variables into a single immutable object. The core follows Clean Architecture boundaries so adapters (filesystem, dotenv, environment) stay isolated from the domain model while the CLI mirrors the same orchestration.

## Table of Contents

1. [Key Features](#key-features)
2. [Architecture Overview](#architecture-overview)
3. [Installation](#installation)
4. [Quick Start](#quick-start)
5. [Configuration Sources & Precedence](#configuration-sources--precedence)
6. [CLI Usage](#cli-usage)
7. [Python API](#python-api)
8. [Example Generation & Deployment](#example-generation--deployment)
9. [Provenance & Observability](#provenance--observability)
10. [Development](#development)
11. [License](#license)

## Key Features

- **Deterministic layering** — precedence is always `defaults → app → host → user → dotenv → env`.
- **Immutable value object** — returned `Config` prevents accidental mutation and exposes dotted-path helpers.
- **Provenance tracking** — every key reports the layer and path that produced it.
- **Cross-platform path discovery** — Linux (XDG), macOS, and Windows layouts with environment overrides for tests.
- **Extensible formats** — TOML and JSON are built-in; YAML is available via the optional `yaml` extra.
- **Automation-friendly CLI** — inspect, deploy, or scaffold configurations without writing Python.
- **Structured logging** — adapters emit trace-aware events without polluting the domain layer.

## Architecture Overview

The project follows a Clean Architecture layout so responsibilities remain easy to reason about and test:

- **Domain** — immutable `Config` value object plus error taxonomy.
- **Application** — merge policy (`LayerSnapshot`, `merge_layers`) and adapter protocols.
- **Adapters** — filesystem discovery, structured file loaders, dotenv, and environment ingress.
- **Composition** — `core` and `_layers` wire adapters together and expose the public API.
- **Presentation & Tooling** — CLI commands, deployment/example helpers, observability utilities, and testing hooks.

Consult [`docs/systemdesign/module_reference.md`](docs/systemdesign/module_reference.md) for a per-module catalogue and traceability back to the system design notes.

## Installation

```bash
pip install lib_layered_config
# or with optional YAML support
pip install "lib_layered_config[yaml]"
```

> **Requires Python 3.13+** — the standard-library `tomllib` handles TOML parsing.
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

## Configuration Sources & Precedence

Later layers override earlier ones **per key** while leaving unrelated keys untouched.

| Precedence | Layer       | Description |
| ---------- | ----------- | ----------- |
| 0          | `defaults`  | Optional baseline file provided via the API/CLI `--default-file` flag |
| 1          | `app`       | System-wide defaults (e.g. `/etc/<slug>/…`) |
| 2          | `host`      | Machine-specific overrides (`hosts/<hostname>.toml`) |
| 3          | `user`      | Per-user settings (XDG, Application Support, AppData) |
| 4          | `dotenv`    | First `.env` found via upward search plus platform extras |
| 5          | `env`       | Process environment with namespacing and `__` nesting |

Use the optional defaults layer when you want one explicitly-provided file to seed configuration before host/user overrides apply.

Important directories (overridable via environment variables):

### Linux
- `/etc/<slug>/config.toml`
- `/etc/<slug>/config.d/*.{toml,json,yaml,yml}`
- `/etc/<slug>/hosts/<hostname>.toml`
- `$XDG_CONFIG_HOME/<slug>/config.toml` (the resolver reads `$XDG_CONFIG_HOME`; if it is missing it falls back to `~/.config/<slug>/config.toml`)
- `.env` search: current directory upwards + `$XDG_CONFIG_HOME/<slug>/.env`

### macOS
- `/Library/Application Support/<Vendor>/<App>/config.toml`
- `/Library/Application Support/<Vendor>/<App>/config.d/`
- `/Library/Application Support/<Vendor>/<App>/hosts/<hostname>.toml`
- `~/Library/Application Support/<Vendor>/<App>/config.toml`
- `.env` search: current directory upwards + `~/Library/Application Support/<Vendor>/<App>/.env`

### Windows
- `%ProgramData%\<Vendor>\<App>\config.toml`
- `%ProgramData%\<Vendor>\<App>\config.d\*`
- `%ProgramData%\<Vendor>\<App>\hosts\%COMPUTERNAME%.toml`
- `%APPDATA%\<Vendor>\<App>\config.toml` (resolver order: `LIB_LAYERED_CONFIG_APPDATA` → `%APPDATA%`; if neither yields an existing directory it tries `LIB_LAYERED_CONFIG_LOCALAPPDATA` → `%LOCALAPPDATA%`)
- `.env` search: current directory upwards + `%APPDATA%\<Vendor>\<App>\.env`

Environment overrides: `LIB_LAYERED_CONFIG_ETC`, `LIB_LAYERED_CONFIG_PROGRAMDATA`, `LIB_LAYERED_CONFIG_APPDATA`, `LIB_LAYERED_CONFIG_LOCALAPPDATA`, `LIB_LAYERED_CONFIG_MAC_APP_ROOT`, `LIB_LAYERED_CONFIG_MAC_HOME_ROOT`. Both the runtime readers and the `deploy` helper honour these variables so generated files land in the same directories that `read_config` inspects.

**Fallback note:** Whenever a path is marked as a fallback, the resolver first consults the documented environment overrides (`LIB_LAYERED_CONFIG_*`, `$XDG_CONFIG_HOME`, `%APPDATA%`, etc.). If those variables are unset or the computed directory does not exist, it switches to the stated fallback location (`~/.config`, `%LOCALAPPDATA%`, ...). This keeps local installs working without additional environment configuration while still allowing operators to steer resolution explicitly.

## CLI Usage

### Command Summary

| Command                                | Description                                           |
|----------------------------------------|-------------------------------------------------------|
| `lib_layered_config read`              | Load configuration (human readable by default)        |
| `lib_layered_config read-json`         | Emit config + provenance JSON envelope                |
| `lib_layered_config deploy`            | Copy a source file into one or more layer directories |
| `lib_layered_config generate-examples` | Scaffold example trees (POSIX/Windows layouts)        |
| `lib_layered_config env-prefix`        | Compute the canonical environment prefix              |
| `lib_layered_config fail`              | Intentionally raise a `RuntimeError` (for testing)    |

### `read`

```bash
lib_layered_config read --vendor Acme --app ConfigKit --slug config-kit   --prefer toml --prefer json   --start-dir /path/to/project   --default-file ./config.defaults.toml   --format human            # or json
  # --provenance / --no-provenance (defaults to provenance)
```

- `--format human` prints an annotated prose list (default).
- `--format json` returns either the Config JSON or, with `--provenance`, a combined `{config, provenance}` document. Pretty-printing is enabled by default; add `--no-indent` for compact output.
- `--default-file` seeds the merge with a lowest-precedence baseline file.

Human output example:

```
service.timeout: 20
  provenance: layer=env, path=None
service.endpoint: https://api.example.com
  provenance: layer=user, path=/home/alice/.config/config-kit/config.toml
```

JSON output example:

```bash
lib_layered_config read --vendor Acme --app ConfigKit --slug config-kit --format json --indent
```

### `deploy`

```bash
lib_layered_config deploy --source ./config/app.toml   --vendor Acme --app ConfigKit --slug config-kit   --target app --target user [--platform posix|windows] [--force]
```

Returns a JSON array of files created or overwritten.

### `generate-examples`

```bash
lib_layered_config generate-examples --destination ./examples   --vendor Acme --app ConfigKit --slug config-kit [--platform posix|windows] [--force]
```

### `env-prefix`

```bash
lib_layered_config env-prefix config-kit
# -> CONFIG_KIT
```

### `read-json`

```bash
lib_layered_config read-json --vendor Acme --app ConfigKit --slug config-kit --no-indent
```

### `fail`

```bash
lib_layered_config fail
# raises RuntimeError: i should fail
```

## Python API

```python
from lib_layered_config import (
    Config,
    read_config,
    read_config_json,
    read_config_raw,
    default_env_prefix,
    deploy_config,
    generate_examples,
    i_should_fail,
)
```

### `Config`

- `Config.get("service.timeout", default=None)` — dotted-path lookups with optional default.
- `Config.origin("service.timeout")` — provenance metadata (`{'layer': 'env', 'path': None, 'key': 'service.timeout'}`).
- `Config.as_dict()` / `Config.to_json(indent=2)` — mutable deep copies for serialization.
- `Config.with_overrides({"service": {"timeout": 90}})` — shallow overrides without mutating the original.

### `read_config`

Immutable `Config` wrapper with provenance metadata. See [Quick Start](#quick-start).

```python
from pathlib import Path
from lib_layered_config import read_config

defaults = Path("config.defaults.toml")
config = read_config(vendor="Acme", app="Demo", slug="demo", default_file=defaults)
print(config.get("service.timeout", default=30))
```

### `read_config_json`

```python
from lib_layered_config import read_config_json
import json

payload = read_config_json(vendor="Acme", app="Demo", slug="demo", indent=2)
data = json.loads(payload)
print(data["config"]["service"]["timeout"])
print(data["provenance"]["service.timeout"])
```

### `read_config_raw`

Returns primitive `dict` structures `(data, provenance)` for automation or templating.

### Example helpers

- `deploy_config(source, vendor=..., app=..., targets=("app", "user"), slug=None, platform=None, force=False)`
- `generate_examples(destination, slug=..., vendor=..., app=..., platform=None, force=False)`

## Example Generation & Deployment

Use the Python helpers or CLI equivalents:

```python
from pathlib import Path
from lib_layered_config.examples import deploy_config, generate_examples

# copy one file into the system/user layers
paths = deploy_config("./myapp/config.toml", vendor="Acme", app="ConfigKit", targets=("app", "user"))

# scaffold an example tree for documentation
examples = generate_examples(Path("./examples"), slug="config-kit", vendor="Acme", app="ConfigKit")
```

## Provenance & Observability

- Every merged key stores metadata (`layer`, `path`, `key`).
- Structured logging lives in `lib_layered_config.observability` (trace-aware `log_debug`, `log_info`, `log_error`).
- Use `bind_trace_id("abc123")` to correlate CLI/log events with your own tracing.

## Further documentation

- [CHANGELOG](CHANGELOG.md) — user-facing release notes.
- [CONTRIBUTING](CONTRIBUTING.md) — guidelines for issues, pull requests, and coding style.
- [DEVELOPMENT](DEVELOPMENT.md) — local tooling, recommended workflow, and release checklist.
- [Module Reference](docs/systemdesign/module_reference.md) — architecture-aligned responsibilities per module.
- [LICENSE](LICENSE) — MIT license text.


## Development

```bash
pip install "lib_layered_config[dev]"
make test          # lint + type-check + pytest + coverage (fail-under=90%)
make build         # build wheel / sdist artifacts
make run -- --help # run the CLI via the repo entrypoint
```

*Formatting gate:* Ruff formatting runs in check mode during `make test`. Run `ruff format .` (or `pre-commit run --all-files`) before pushing and consider `pre-commit install` to keep local edits aligned.

*Coverage gate:* the maintained test suite must stay ≥90% (see `pyproject.toml`). Add targeted unit tests if you extend functionality.

**Platform notes**

- Windows runners install `pipx` and `uv` automatically in CI; locally ensure `pipx` is on your `PATH` before running `make test` so the wheel verification step succeeds.
- The journald prerequisite step runs only on Linux; macOS/Windows skips it, so there is no extra setup required on those platforms.

### Continuous integration

The GitHub Actions workflow executes three jobs:

- **Test matrix** (Linux/macOS/Windows, Python 3.13 + latest 3.x) running the same pipeline as `make test`.
- **pipx / uv verification** to prove the built wheel installs cleanly with the common Python app launchers.
- **Notebook smoke test** that executes `notebooks/Quickstart.ipynb` to keep the tutorial in sync.

Packaging-specific jobs (conda, Nix, Homebrew sync) were retired; the Python packaging metadata in `pyproject.toml` remains the single source of truth.

## License

MIT © Robert Nowotny
