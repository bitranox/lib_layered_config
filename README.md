# lib_layered_config

<!-- Badges -->
[![CI](https://github.com/bitranox/lib_layered_config/actions/workflows/ci.yml/badge.svg)](https://github.com/bitranox/lib_layered_config/actions/workflows/ci.yml)
[![CodeQL](https://github.com/bitranox/lib_layered_config/actions/workflows/codeql.yml/badge.svg)](https://github.com/bitranox/lib_layered_config/actions/workflows/codeql.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Jupyter](https://img.shields.io/badge/Jupyter-Launch-orange?logo=jupyter)](https://mybinder.org/v2/gh/bitranox/lib_layered_config/HEAD?labpath=notebooks%2FQuickstart.ipynb)
[![PyPI](https://img.shields.io/pypi/v/lib-layered-config.svg)](https://pypi.org/project/lib-layered-config/)
[![PyPI - Downloads](https://img.shields.io/pypi/dm/lib-layered-config.svg)](https://pypi.org/project/lib-layered-config/)
[![Code Style: Ruff](https://img.shields.io/badge/Code%20Style-Ruff-46A3FF?logo=ruff&labelColor=000)](https://docs.astral.sh/ruff/)
[![codecov](https://codecov.io/gh/bitranox/lib_layered_config/graph/badge.svg)](https://codecov.io/gh/bitranox/lib_layered_config)
[![Maintainability](https://qlty.sh/gh/bitranox/projects/lib_layered_config/maintainability.svg)](https://qlty.sh/gh/bitranox/projects/lib_layered_config)
[![Known Vulnerabilities](https://snyk.io/test/github/bitranox/lib_layered_config/badge.svg)](https://snyk.io/test/github/bitranox/lib_layered_config)

A cross-platform configuration loader that deep-merges application defaults, host overrides, user profiles, `.env` files, and environment variables into a single immutable object. The library follows Clean Architecture boundaries so adapters (filesystem, dotenv, env) stay isolated from the domain model.

## Why

- **Deterministic precedence** — order is always `app → host → user → dotenv → env`.
- **Immutable API** — the returned `Config` value object prevents accidental runtime mutation.
- **Provenance tracking** — each key stores the layer and path that produced it.
- **OS-aware paths** — Linux (XDG), macOS, and Windows search strategies are built in.
- **Optional YAML support** — TOML and JSON are core; enable YAML via the `yaml` extra. Only users who rely on `.yml` files need to install the optional dependency, keeping the default install lightweight and pure-stdlib.

## Installation

```bash
pip install lib_layered_config
# or with YAML support
pip install "lib_layered_config[yaml]"
```

> **Note**
> `tomli>=2.0.1` ships with the base package to guarantee compatibility with Python 3.10. Modern
> interpreters (3.11+) use the stdlib `tomllib`, and the backport is effectively a no-op.

*Only install the `yaml` extra when your deployment actually ships `.yml` files—this keeps the default dependency set pure stdlib and avoids pulling in PyYAML unnecessarily.*

Development tooling (lint, type-check, tests, security) lives behind the `dev` extra:

```bash
pip install "lib_layered_config[dev]"
```

## Quick start

1. Create configuration files in the conventional locations (see the tables below).
2. Call `read_config` with your vendor, application, and slug identifiers.

```python
>>> from lib_layered_config import Config, read_config, default_env_prefix
>>> cfg = Config({"service": {"timeout": 30}}, {"service.timeout": {"layer": "app", "path": "config.toml", "key": "service.timeout"}})
>>> cfg.get("service.timeout")
30
>>> default_env_prefix("config-kit")
'CONFIG_KIT'
```

Calling the real loader wires all adapters together:

```python
from lib_layered_config import read_config

config = read_config(vendor="Acme", app="ConfigKit", slug="config-kit")
print(config.get("service.endpoint", default="https://api.acme.com"))
print(config.origin("service.endpoint"))  # {'layer': 'user', 'path': '/home/.../config.toml', 'key': 'service.endpoint'}
```

## Layer precedence

Later layers override earlier ones **per key** while preserving unrelated settings.

| Precedence | Layer   | Description                                   |
|------------|---------|-----------------------------------------------|
| 1          | `app`   | System-wide defaults (e.g., `/etc/<slug>/…`)   |
| 2          | `host`  | Machine-specific overrides                    |
| 3          | `user`  | Per-user settings (XDG, macOS, Windows paths) |
| 4          | `dotenv`| First `.env` encountered (upward search + OS) |
| 5          | `env`   | Process environment (prefix + `__` nesting)   |

Environment example: with slug `config-kit`, setting `CONFIG_KIT_SERVICE__TIMEOUT=45` produces `{"service": {"timeout": 45}}` in the merged configuration (thanks to the prefix and double underscore nesting semantics).

## Default paths

### Linux (XDG)
- `/etc/<slug>/config.toml`
- `/etc/<slug>/config.d/*.toml|*.json|*.yaml`
- `/etc/<slug>/hosts/<hostname>.toml`
- `$XDG_CONFIG_HOME/<slug>/config.toml` (fallback `~/.config/<slug>/config.toml`)
- `$XDG_CONFIG_HOME/<slug>/config.d/*.{toml,json,yaml,yml}`
- `.env` search: current directory upwards + `$XDG_CONFIG_HOME/<slug>/.env`

### macOS
- `/Library/Application Support/<Vendor>/<App>/config.toml`
- `/Library/Application Support/<Vendor>/<App>/config.d/*`
- `/Library/Application Support/<Vendor>/<App>/hosts/<hostname>.toml`
- `~/Library/Application Support/<Vendor>/<App>/config.toml`
- `.env` search: current directory upwards + `~/Library/Application Support/<Vendor>/<App>/.env`

### Windows
- `%ProgramData%\<Vendor>\<App>\config.toml`
- `%ProgramData%\<Vendor>\<App>\config.d\*`
- `%ProgramData%\<Vendor>\<App>\hosts\%COMPUTERNAME%.toml`
- `%APPDATA%\<Vendor>\<App>\config.toml` (fallback `%LOCALAPPDATA%`)
- `.env` search: current directory upwards + `%APPDATA%\<Vendor>\<App>\.env`

All directory roots accept test-friendly overrides via the environment variables:
`LIB_LAYERED_CONFIG_ETC`, `LIB_LAYERED_CONFIG_PROGRAMDATA`, `LIB_LAYERED_CONFIG_APPDATA`, `LIB_LAYERED_CONFIG_LOCALAPPDATA`, `LIB_LAYERED_CONFIG_MAC_APP_ROOT`, and `LIB_LAYERED_CONFIG_MAC_HOME_ROOT`.

## API surface

```python
from lib_layered_config import (
    Config,
    ConfigError,
    InvalidFormat,
    ValidationError,
    NotFound,
    LayerLoadError,
    read_config,
    read_config_raw,
    default_env_prefix,
    deploy_config,
    generate_examples,
    i_should_fail,
)
```

### `read_config(*, vendor, app, slug, prefer=None, start_dir=None) -> Config`
**Why**
    Load every configured layer (application defaults, host overrides, user profiles, `.env`, environment variables) and expose the merged view via an immutable `Config` value object.

**Parameters**
- `vendor` *(str)* – organisation or vendor namespace. Drives platform-specific directories such as `/etc/<vendor>/…` or `%APPDATA%\<vendor>\…`.
- `app` *(str)* – application name combined with the vendor to derive host and user layer directories.
- `slug` *(str)* – identifier for the configuration family (also feeds the environment variable prefix and the XDG/macOS folder names).
- `prefer` *(Sequence[str] | None)* – optional ordered list of suffixes (without dots) used to prioritise files inside `config.d` directories (`("toml", "json")` makes TOML win over JSON when both exist).
- `start_dir` *(str | None)* – directory from which the `.env` upward search begins. Defaults to the current working directory; handy for project-relative runners.

**Returns**
- `Config` – immutable mapping with provenance metadata attached to each dotted key.

**Example**
```python
>>> from tempfile import TemporaryDirectory
>>> from pathlib import Path
>>> import os
>>> tmp = TemporaryDirectory()
>>> etc_root = Path(tmp.name) / 'etc'
>>> (etc_root / 'demo').mkdir(parents=True, exist_ok=True)
>>> _ = (etc_root / 'demo' / 'config.toml').write_text('[service]
endpoint = "https://api.example.com"
', encoding='utf-8')
>>> previous = os.environ.get('LIB_LAYERED_CONFIG_ETC')
>>> try:
...     os.environ['LIB_LAYERED_CONFIG_ETC'] = str(etc_root)
...     cfg = read_config(vendor='Acme', app='Demo', slug='demo')
...     value = cfg.get('service.endpoint')
... finally:
...     if previous is None:
...         os.environ.pop('LIB_LAYERED_CONFIG_ETC', None)
...     else:
...         os.environ['LIB_LAYERED_CONFIG_ETC'] = previous
...     tmp.cleanup()
>>> value
'https://api.example.com'
```

### `read_config_raw(*, vendor, app, slug, prefer=None, start_dir=None) -> tuple[dict[str, object], dict[str, dict[str, object]]]`
**Why**
    Automation sometimes needs the primitive `dict` structures (for JSON APIs, templating, or UI rendering) instead of the `Config` wrapper.

**Parameters**
    Same as `read_config`.

**Returns**
- `tuple[dict[str, object], dict[str, dict[str, object]]]` – `(merged_data, provenance)` where `provenance` maps dotted keys to `{"layer", "path", "key"}` records.

**Example**
```python
>>> from tempfile import TemporaryDirectory
>>> from pathlib import Path
>>> import os
>>> tmp = TemporaryDirectory()
>>> etc_root = Path(tmp.name) / 'etc'
>>> (etc_root / 'demo').mkdir(parents=True, exist_ok=True)
>>> _ = (etc_root / 'demo' / 'config.toml').write_text('[feature]
enabled = true
', encoding='utf-8')
>>> previous = os.environ.get('LIB_LAYERED_CONFIG_ETC')
>>> try:
...     os.environ['LIB_LAYERED_CONFIG_ETC'] = str(etc_root)
...     data, meta = read_config_raw(vendor='Acme', app='Demo', slug='demo')
... finally:
...     if previous is None:
...         os.environ.pop('LIB_LAYERED_CONFIG_ETC', None)
...     else:
...         os.environ['LIB_LAYERED_CONFIG_ETC'] = previous
...     tmp.cleanup()
>>> data['feature']['enabled']
True
>>> meta['feature.enabled']['layer']
'app'
```

### `default_env_prefix(slug: str) -> str`
**Why**
    Compute the canonical environment-variable prefix for a configuration slug so scripts can discover `FOO__BAR` style variables.

**Parameters**
- `slug` *(str)* – configuration family identifier (kebab or snake case).

**Returns**
- `str` – uppercase namespace with dashes converted to underscores.

**Example**
```python
>>> default_env_prefix('config-kit')
'CONFIG_KIT'
```

### `deploy_config(source, *, vendor, app, targets, slug=None, platform=None, force=False) -> list[pathlib.Path]`
**Why**
    Copy an existing configuration artefact into the canonical layer directories so operators can bootstrap installations without touching platform-specific paths manually.

**Parameters**
- `source` *(str | Path)* – path to the configuration file that should be copied.
- `vendor` / `app` *(str)* – same identifiers you pass to `read_config`; they determine the deployment directories on each OS.
- `targets` *(Sequence[str])* – ordered list containing any combination of `"app"`, `"host"`, and `"user"`; the function attempts to deploy in the provided order.
- `slug` *(str | None)* – optional slug for directory naming; defaults to `app` when omitted.
- `platform` *(str | None)* – force a particular resolver platform (`"linux"`, `"darwin"`, `"win32"`); defaults to the running interpreter platform.
- `force` *(bool)* – overwrite existing files when `True`; otherwise existing files are preserved and omitted from the result.

**Returns**
- `list[pathlib.Path]` – destinations that were created or overwritten during this call (order mirrors `targets`).

**Example**
```python
>>> from tempfile import TemporaryDirectory
>>> from pathlib import Path
>>> import os
>>> tmp = TemporaryDirectory()
>>> source = Path(tmp.name) / 'base.toml'
>>> _ = source.write_text('[service]
endpoint = "https://api.example.com"
', encoding='utf-8')
>>> os.environ['LIB_LAYERED_CONFIG_ETC'] = str(Path(tmp.name) / 'etc')
>>> os.environ['XDG_CONFIG_HOME'] = str(Path(tmp.name) / 'xdg')
>>> paths = deploy_config(source, vendor='Acme', app='Demo', targets=['app', 'user'], slug='demo')
>>> sorted(p.name for p in paths)
['config.toml', 'config.toml']
>>> tmp.cleanup()
```

### `generate_examples(destination, *, slug, vendor, app, force=False, platform=None) -> list[pathlib.Path]`
**Why**
    Scaffold commented example files for every layer (system, host, user, dotenv) so documentation and demos stay in sync with the library’s conventions.

**Parameters**
- `destination` *(str | Path)* – directory root that will receive the example tree; created if missing.
- `slug` / `vendor` / `app` *(str)* – identifiers injected into file contents and directory names to make the examples read naturally.
- `force` *(bool)* – overwrite existing example files when `True`; by default the function skips files that already exist to avoid clobbering edits.
- `platform` *(str | None)* – override the platform layout. Accepts `"posix"` (covers Linux/macOS variants) or `"windows"`; `None` chooses based on the current interpreter.

**Returns**
- `list[pathlib.Path]` – absolute paths written (or overwritten when `force=True`).

**Example**
```python
>>> from tempfile import TemporaryDirectory
>>> from pathlib import Path
>>> tmp = TemporaryDirectory()
>>> generated = generate_examples(tmp.name, slug='demo', vendor='Acme', app='ConfigKit', platform='posix')
>>> sorted(p.relative_to(tmp.name).as_posix() for p in generated)[0]
'.env.example'
>>> tmp.cleanup()
```

### `i_should_fail() -> None`
**Why**
    Provide a deterministic failure hook for CLI demos and integration tests verifying error handling.

**Behaviour**
- Always raises `RuntimeError` with the message `"i should fail"`.

**Example**
```python
>>> from lib_layered_config.testing import i_should_fail
>>> try:
...     i_should_fail()
... except RuntimeError as exc:
...     error_message = str(exc)
>>> error_message
'i should fail'
```

### `Config` value object
**Why**
    Represent the merged configuration as an immutable, provenance-aware mapping.

**Key methods**
- `Config.get(key, default=None)` – dotted-path lookup (e.g. `cfg.get("service.timeout")`).
- `Config.origin(key)` – provenance metadata for a dotted key.
- `Config.to_json(indent=None)` – serialise to JSON for logging or debugging.
- `Config.with_overrides(mapping)` – return a new `Config` with top-level overrides applied (useful for tests).

**Example**
```python
>>> cfg = Config({'service': {'timeout': 30}}, {'service.timeout': {'layer': 'env', 'path': None, 'key': 'service.timeout'}})
>>> cfg.get('service.timeout')
30
>>> cfg.origin('service.timeout')
{'layer': 'env', 'path': None, 'key': 'service.timeout'}
>>> cfg.to_json()
'{"service":{"timeout":30}}'
```

## CLI usage

The package installs two entry points (``lib_layered_config`` and ``lib-layered-config``). All
commands accept the global flag ``--traceback/--no-traceback`` which controls whether full Python
tracebacks are rendered on errors (default: summary only). Unless noted, all subcommands emit JSON to
stdout and non-zero exit codes on failure.

### `info`
**Purpose**
    Print distribution metadata so operators can confirm the installed version and related project URLs.

**Options**
    None beyond the global ``--traceback`` toggle.

**Output**
    Human-readable metadata including name, version, required Python range, summary, and any
    ``Project-URL`` entries declared in the package metadata.

**Example**
```bash
$ lib_layered_config info
Info for lib_layered_config:
  Version         : 0.0.1
  Requires-Python : >=3.12
  Summary         : Cross-platform layered configuration loader for Python
```

### `env-prefix <slug>`
**Purpose**
    Compute the canonical environment variable prefix for a configuration slug so shell scripts and
    infrastructure tooling can discover namespaced variables (e.g. ``CONFIG_KIT_SERVICE__PORT``).

**Arguments**
- ``slug`` *(required positional)* – configuration family identifier (kebab or snake case).

**Example**
```bash
$ lib_layered_config env-prefix config-kit
CONFIG_KIT
```

### `read`
**Purpose**
    Execute the layered configuration pipeline (application → host → user → dotenv → environment) and
    print the merged configuration as JSON. Optionally includes provenance metadata for each key.

**Options**
- ``--vendor`` *(required)* – vendor namespace used to resolve OS-specific directories.
- ``--app`` *(required)* – application name combined with the vendor to locate host/user directories.
- ``--slug`` *(required)* – configuration family identifier; also influences environment prefixes.
- ``--prefer`` *(repeatable)* – ordered suffix list (no leading dots) prioritising files inside
  ``config.d`` directories (e.g. ``--prefer toml --prefer json``).
- ``--start-dir`` *(path, optional)* – directory where the dotenv loader begins its upward search;
  defaults to the current working directory.
- ``--indent`` *(int, optional)* – pretty-print JSON with the specified indentation.
- ``--provenance/--no-provenance`` *(flag, default: ``--no-provenance``)* – when enabled, include a
  ``{"config": ..., "provenance": ...}`` envelope describing the source layer/path for each key.

**Example**
```bash
$ lib_layered_config read \
    --vendor Acme \
    --app Demo \
    --slug demo \
    --prefer toml --prefer json \
    --indent 2 \
    --provenance
{
  "config": {
    "service": {
      "endpoint": "https://api.example.com"
    }
  },
  "provenance": {
    "service.endpoint": {
      "layer": "app",
      "path": "/etc/demo/config.toml",
      "key": "service.endpoint"
    }
  }
}
```

Pass ``--start-dir PATH`` to anchor the dotenv search at a project directory, and repeat ``--prefer``
to control precedence among sibling files in ``config.d`` directories.

### `deploy`
**Purpose**
    Copy an existing configuration artefact into one or more canonical layer directories (system app,
    host overrides, user profile) using the same resolver logic as ``read_config``.

**Options**
- ``--source`` *(required path)* – file to deploy.
- ``--vendor`` / ``--app`` *(required)* – identifiers that drive platform-specific target directories.
- ``--slug`` *(required)* – configuration family name; CLI does not assume defaults.
- ``--target`` *(repeatable)* – any combination of ``app``, ``host``, ``user``; order determines the
  deployment attempts.
- ``--platform`` *(optional)* – override auto-detected platform (accepts ``linux``, ``darwin``,
  ``win32`` and common aliases).
- ``--force/--no-force`` *(flag, default: ``--no-force``)* – overwrite existing files when set; skip
  them otherwise.

**Example**
```bash
$ lib_layered_config deploy \
    --source ./config/app.toml \
    --vendor Acme \
    --app Demo \
    --slug demo \
    --target app \
    --target user
["/etc/demo/config.toml", "/home/user/.config/demo/config.toml"]
```

### `generate-examples`
**Purpose**
    Scaffold the commented example files shipped in ``lib_layered_config.examples`` under a chosen
    destination directory. Useful for documentation, demos, or quick-start boilerplates.

**Options**
- ``--destination`` *(required path)* – directory where the example tree should be created (created if
  absent).
- ``--slug`` / ``--vendor`` / ``--app`` *(required)* – values injected into filenames and file
  contents so the examples read naturally.
- ``--platform`` *(optional)* – choose ``posix`` or ``windows`` explicitly; defaults to the host
  platform.
- ``--force/--no-force`` *(flag, default: ``--no-force``)* – overwrite existing example files when set;
  otherwise only missing files are created.

**Example**
```bash
$ lib_layered_config generate-examples \
    --destination ./examples/demo \
    --slug demo \
    --vendor Acme \
    --app Demo \
    --platform posix
[
  "/absolute/path/examples/demo/etc/demo/config.toml",
  "/absolute/path/examples/demo/.env.example",
  ...
]
```

### `fail`
**Purpose**
    Deliberately raise ``RuntimeError('i should fail')`` to exercise error handling, logging, and
    traceback formatting.

**Options**
    None (besides the global ``--traceback`` toggle).

**Example**
```bash
$ lib_layered_config fail
Error: i should fail
```

## Packaging targets

The repository ships manifests for common ecosystems (PyPI, Conda, Homebrew, Nix). Each target now
declares the `tomli>=2.0.1` dependency so that Python 3.10 environments have a compatible TOML parser
out of the box. On Python 3.11+ the stdlib `tomllib` takes over automatically.

## Further documentation

- [CHANGELOG](CHANGELOG.md) — user-facing release notes.
- [CONTRIBUTING](CONTRIBUTING.md) — guidelines for issues, pull requests, and coding style.
- [DEVELOPMENT](DEVELOPMENT.md) — local tooling, recommended workflow, and release checklist.
- [LICENSE](LICENSE) — project licensing details (MIT).
- [Module Reference](docs/systemdesign/module_reference.md) — architecture-aligned module-by-module responsibilities.

## Development & Testing

- `make dev` installs the project with development extras.
- `make test` runs linting, type checking, full pytest (including notebooks) and uploads coverage.
- For quicker feedback, run `pytest -m "not slow"` to skip the notebook suite.
- Coverage files are emitted under `/tmp/.coverage*`; delete them if you need to reset a failed local run.
