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
)
```

### `read_config(*, vendor, app, slug, prefer=None, start_dir=None) -> Config`
**Why**: Load all configured layers (application, host, user, dotenv, environment) and hand back an immutable `Config` so callers can read settings without knowing how precedence works.

**Parameters**
- `vendor` *(str)* – organisation or vendor namespace used by path resolvers (`/etc/<vendor>/…`, `%APPDATA%\<vendor>\…`).
- `app` *(str)* – application name combined with the vendor to build host and user directories.
- `slug` *(str)* – identifier for the configuration family (also feeds environment prefixes).
- `prefer` *(Sequence[str] | None)* – optional ordered list of suffixes (e.g. `("toml", "json")`) used to prioritise files inside `config.d` directories.
- `start_dir` *(str | None)* – directory the dotenv loader should start its upward search from; defaults to the current working directory.

**Returns**: `Config` – immutable mapping with provenance metadata attached.

**Side Effects**: Emits observability events via `lib_layered_config.observability`.

**Example**
```python
>>> from pathlib import Path
>>> from tempfile import TemporaryDirectory
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
**Why**: Some tools need the raw `dict` and provenance map (for JSON APIs, dashboards, or templating) instead of the `Config` wrapper.

**Parameters**: Same as `read_config`.

**Returns**: `(merged_data, provenance)` where `merged_data` mirrors the final configuration and `provenance` maps dotted keys to `{"layer", "path", "key"}` records.

**Example**
```python
>>> from pathlib import Path
>>> from tempfile import TemporaryDirectory
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
**Why**: Translates a slug into the canonical uppercase environment prefix (`demo-service` → `DEMO_SERVICE`) so automation scripts can check the right variables.

**Parameters**: `slug` *(str)* – configuration slug (kebab or snake case).

**Returns**: Uppercase prefix ending with no underscore.

**Example**
```python
>>> default_env_prefix('config-kit')
'CONFIG_KIT'
```

### `deploy_config(source, *, vendor, app, targets, slug=None) -> list[pathlib.Path]`
**Why**: Provision configuration artifacts into the canonical layer directories (system app, host overrides, user profiles) without overwriting operator-managed files.

**Parameters**
- `source` *(str | Path)* – existing configuration file to copy.
- `vendor` / `app` *(str)* – same identifiers used by `read_config`; drive target locations.
- `targets` *(Sequence[str])* – any combination of `"app"`, `"host"`, `"user"`; order determines copy attempts.
- `slug` *(str | None)* – optional slug for directory naming; defaults to `app` when omitted.

**Returns**: list of destination paths that were created. Existing files are left untouched.

**Example**
```python
>>> from tempfile import TemporaryDirectory
>>> from pathlib import Path
>>> from lib_layered_config.examples import deploy_config
>>> import os
>>> tmp = TemporaryDirectory()
>>> source = Path(tmp.name) / 'base.toml'
>>> _ = source.write_text('[service]\nendpoint = "https://api.example.com"\n', encoding='utf-8')
>>> os.environ['LIB_LAYERED_CONFIG_ETC'] = str(Path(tmp.name) / 'etc')
>>> os.environ['XDG_CONFIG_HOME'] = str(Path(tmp.name) / 'xdg')
>>> paths = deploy_config(source, vendor='Acme', app='Demo', targets=['app', 'user'], slug='demo')
>>> sorted(p.name for p in paths)
['config.toml', 'config.toml']
>>> tmp.cleanup()
```

### `i_should_fail() -> None`
**Why**: Provide a deterministic failure hook for integration tests and CLI demonstrations.

**Behaviour**: Always raises `RuntimeError` with the message `"i should fail"`.

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
**Why**: Acts as the immutable façade returned by `read_config`, preserving provenance while behaving like a mapping.

**Key Methods**
- `Config.get(key, default=None)` – dotted-path lookup (`cfg.get("service.timeout")`).
- `Config.origin(key)` – return provenance metadata for a dotted key or `None`.
- `Config.to_json(indent=None)` – serialise configuration for logs or debugging.
- `Config.with_overrides(mapping)` – return a shallow copy with specific top-level overrides (useful in tests).

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

For shell usage, the CLI replicates these capabilities:

```bash
lib_layered_config read --vendor Acme --app Demo --slug demo --provenance --indent 2
```

## CLI usage

The package installs two entry points (``lib_layered_config`` and ``lib-layered-config``).
All commands share the global option ``--traceback`` which toggles full Python stack traces
when something goes wrong. The core subcommands are:

- ``info`` – print installed metadata, version, and project URLs.
- ``env-prefix <slug>`` – return the canonical environment prefix for a slug (e.g. ``config-kit`` → ``CONFIG_KIT``).
- ``read`` – execute the layered configuration pipeline and emit JSON (optionally with provenance).
- ``fail`` – raise a deliberate ``RuntimeError('i should fail')`` to test error handling and traceback output.

### Inspect metadata
```bash
$ lib_layered_config info
Info for lib_layered_config:
  Version         : 0.0.1
  Requires-Python : >=3.12
  Summary         : Cross-platform layered configuration loader for Python
```

### Compute an environment prefix
```bash
$ lib_layered_config env-prefix config-kit
CONFIG_KIT
```

### Trigger a failure to inspect tracebacks
```bash
$ lib_layered_config fail
Error: i should fail
```

### Read configuration with precedence controls
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

Pass ``--start-dir PATH`` when you want the dotenv loader to begin from a specific
project directory instead of the current working directory. Repeat ``--prefer`` to
prioritise multiple suffixes inside ``config.d`` (e.g. TOML over JSON). For large
results, combine ``--indent`` with shell tools like ``jq`` to focus on specific keys.

## Example config generators (coming soon)

Utility functions in `lib_layered_config.examples` (to be implemented in follow-up milestones) will scaffold commented example files for each layer.


## Further documentation

- [CHANGELOG](CHANGELOG.md) — user-facing release notes.
- [CONTRIBUTING](CONTRIBUTING.md) — guidelines for issues, pull requests, and coding style.
- [DEVELOPMENT](DEVELOPMENT.md) — local tooling, recommended workflow, and release checklist.
- [LICENSE](LICENSE) — project licensing details (MIT).
- [Module Reference](docs/systemdesign/module_reference.md) — architecture-aligned module-by-module responsibilities.
