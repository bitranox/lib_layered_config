---
name: python-layered-config
description: Use when building or designing configuration for a Python app or CLI with lib_layered_config - deciding where config files live on Linux, macOS, or Windows, choosing the environment-variable override names, adding environment profiles (test/staging/production), loading config in code or from the shell, redacting secrets, or working out which layer and file a setting actually came from (provenance).
---

# lib_layered_config

Load one immutable configuration object by deep-merging six layers, and be able to say
where every value came from. `lib_layered_config` is a cross-platform config loader for
Python 3.10+ with a matching CLI. It is designed to be driven by an LLM/agent as well as a
human - this skill is that agent guide.

## The core model

Six layers are merged in a fixed precedence, **lowest to highest**:

```
defaults -> app -> host -> user -> dotenv -> env
```

Later layers override earlier ones key-by-key (unrelated keys are kept, not dropped). The
result is a frozen `Config`. Every value records the layer and file that produced it.

Do not forget `defaults` (the lowest layer, seeded from an explicit `default_file`) or that
`env` (process environment variables) wins over everything.

## Install

```bash
pip install lib_layered_config          # TOML + JSON (via rtoml / orjson)
pip install "lib_layered_config[yaml]"  # add optional YAML support
```

Requires Python 3.10+. Install the `yaml` extra only if you ship `.yml` files.

## Load config (Python)

```python
from lib_layered_config import read_config

config = read_config(
    vendor="Acme Corp",
    app="My App",
    slug="my-app",
    default_file="defaults.toml",  # seeds the `defaults` layer (the lowest one)
)
config.get("service.timeout", default=30)  # dotted-path access
config["database"]["host"]  # mapping access
config.origin("service.timeout")  # -> which layer + file set it (provenance)
```

- `vendor` and `app` are used **verbatim** (spaces and case preserved) in the macOS and
  Windows paths.
- `slug` (lowercase-with-hyphens) is the Linux directory name AND the environment-variable
  prefix.
- `default_file` seeds the `defaults` layer. It is the ONLY way to supply that layer - omit it
  and there are no defaults at all, whatever the precedence chain says.
- `read_config` returns a frozen `Config`; `read_config_raw(...)` returns `.data` plus
  `.provenance`; `read_config_json(...)` returns a JSON string of config + provenance.

## Where a setting comes from (provenance)

The whole point of the library. To answer "why is this value what it is":

- **Python:** `config.origin("database.host")` returns the layer and file path. Or
  `read_config_raw(...).provenance["database.host"]` -> `{"layer": ..., "path": ..., "key": ...}`.
- **CLI:** `lib_layered_config read-json --vendor "Acme Corp" --app "My App" --slug my-app`
  prints the merged config **and** the provenance map. `read --format json` does the same;
  human output (`read`) prints a `# source:` comment above each value.

## Environment-variable overrides (the trap)

An env var overriding a config key is built as:

```
<SLUG_UPPERCASED_WITH_DASHES_AS_UNDERSCORES> + "___" + <SECTION>__<SUBSECTION>__<KEY>
```

- Prefix ends in a **TRIPLE** underscore `___` (separates the app prefix from the key path).
- Key-path segments are joined by a **DOUBLE** underscore `__`.

So for `slug="my-app"`, the key `database.host` is set by **`MY_APP___DATABASE__HOST`**
(not `MY_APP_DATABASE__HOST`, not `MYAPP___...`). Compute the prefix with
`lib_layered_config env-prefix my-app` (the slug is POSITIONAL; prints `MY_APP___`) or
`default_env_prefix("my-app")` in Python.

- Values coerce: `true`/`false` -> bool, `null`/`none` -> None, ints/floats, else string.
- A value starting with `[` or `{` is parsed as JSON (`REPLICAS='["a","b"]'`).
- A numeric segment overrides one element of a file-defined array:
  `MY_APP___DATASET__0__DSN=...` overrides element 0's `dsn`, leaving the rest of the array.

## Per-OS config paths

Each layer resolves to a `config.toml` (with an optional companion `config.d/` directory,
and `.yaml`/`.json` also accepted). `<Vendor>`/`<App>` are verbatim; `<slug>` is the slug.

| Layer  | Linux                                   | macOS                                                      | Windows                                    |
|--------|-----------------------------------------|------------------------------------------------------------|--------------------------------------------|
| app    | `/etc/xdg/<slug>/config.toml`           | `/Library/Application Support/<Vendor>/<App>/config.toml`  | `%ProgramData%\<Vendor>\<App>\config.toml` |
| host   | `/etc/xdg/<slug>/hosts/<hostname>.toml` | `.../<Vendor>/<App>/hosts/<hostname>.toml`                 | `...\<Vendor>\<App>\hosts\<hostname>.toml` |
| user   | `~/.config/<slug>/config.toml`          | `~/Library/Application Support/<Vendor>/<App>/config.toml` | `%APPDATA%\<Vendor>\<App>\config.toml`     |
| dotenv | `~/.config/<slug>/.env`                 | `~/Library/Application Support/<Vendor>/<App>/.env`        | user `%APPDATA%\<Vendor>\<App>\.env`       |
| env    | process environment, prefix `<SLUG>___` | same                                                       | same                                       |

Notes: Linux `app`/`host` also fall back to `/etc/<slug>/...`; Linux honours
`$XDG_CONFIG_HOME` for the user layer; Windows also checks `%LOCALAPPDATA%` for the user
layer. Roots are overridable for tests (`LIB_LAYERED_CONFIG_ETC`,
`LIB_LAYERED_CONFIG_MAC_APP_ROOT`, etc.).

## Profiles (per-environment config)

A profile keeps test/staging/production in separate trees. Pass `profile=`:

```python
config = read_config(vendor="Acme Corp", app="My App", slug="my-app", profile="production")
```

This inserts a `profile/<name>/` segment into every layer path, e.g.
`/etc/xdg/my-app/profile/production/config.toml`. Without a profile you get the base paths.
Profile names are validated (no path traversal, control chars, reserved names, non-ASCII;
max 64 chars). `--profile` is an OPTION on `deploy`, not a command on its own - the required
flags come too: `deploy --source cfg.toml --vendor acme --app my-app --slug my-app --target user
--profile production`.

## CLI commands

Same engine as the library. Run any command with `-h` for full flags.

| Command             | Purpose                                                                                                                                             |
|---------------------|-----------------------------------------------------------------------------------------------------------------------------------------------------|
| `read`              | Load and print config (human by default; `--format json`, `--redact`).                                                                              |
| `read-json`         | Print merged config + provenance as JSON.                                                                                                           |
| `deploy`            | Copy a config file into app/host/user layers (`--target`, `--profile`, `--force`/`--batch`, `.bak`/`.ucf` conflict handling, permission hardening). |
| `generate-examples` | Scaffold an example config tree to bootstrap a project.                                                                                             |
| `env-prefix`        | Print the `<SLUG>___` env-var prefix for a slug.                                                                                                    |
| `info`              | Print resolved package metadata.                                                                                                                    |

Flags are PER-SUBCOMMAND, not CLI-wide - run `<cmd> -h` before composing a call:

| Flag                                          | read | read-json | deploy | generate-examples | env-prefix | info |
|-----------------------------------------------|------|-----------|--------|-------------------|------------|------|
| `--vendor` / `--app` / `--slug`               | yes  | yes       | yes    | yes               | no         | no   |
| `--profile`                                   | yes  | yes       | yes    | no                | no         | no   |
| `--env-file <path>` (load an explicit `.env`) | yes  | yes       | no     | no                | no         | no   |
| `--redact` (mask secrets in output)           | yes  | yes       | no     | no                | no         | no   |

`env-prefix` and `info` accept no options at all beyond `--help` (`env-prefix` takes a
positional SLUG). Passing one of the others raises `NoSuchOption`.

## Designing config files

- **Structure maps to access and to env vars.** A `[database]` section with `host = "..."`
  is read as `config.get("database.host")` and overridden by `MY_APP___DATABASE__HOST`. A
  `[database.pool]` subtable's `size` is `database.pool.size` / `MY_APP___DATABASE__POOL__SIZE`.
- **Keep secrets OUT of committed files.** Put passwords/tokens in the `env` layer or a
  `.env` file (both outrank the committed config); use `--redact` / `Config.to_json(redact=True)`
  when printing or logging.
- **Split large config with `.d/`.** `config.toml` may have a companion `config.d/` whose
  files (`10-db.toml`, `20-cache.yaml`, ...) load in lexicographic order and can mix formats.
- **Use profiles for environments**, not copy-pasted files.
- **Scaffold** a starting tree with `generate-examples` rather than hand-building paths.

## Common mistakes

| Mistake                                                    | Fix                                                                        |
|------------------------------------------------------------|----------------------------------------------------------------------------|
| Env prefix with a single/double underscore (`MY_APP_...`)  | The prefix ends in a **triple** underscore: `MY_APP___`. Run `env-prefix`. |
| Forgetting the `defaults` layer or the `env`-wins ordering | Precedence is `defaults -> app -> host -> user -> dotenv -> env`.          |
| Slugifying vendor/app for macOS/Windows paths              | `vendor`/`app` are used verbatim (spaces kept); only `slug` is normalized. |
| Hunting for "why is this value X" by hand                  | Use `config.origin(key)` or `read-json` - provenance is built in.          |
| Committing a `.env` with secrets                           | `.env` is for local secrets only; never commit it; keep mode `0o600`.      |

## Full detail

This skill is the self-contained agent guide; the repository docs are not shipped with the
installed package, so use these web links for exhaustive detail:

- Project (GitHub): https://github.com/bitranox/lib_layered_config
- Package (PyPI): https://pypi.org/project/lib-layered-config/
- README: https://github.com/bitranox/lib_layered_config/blob/master/README.md
- Identifiers, profiles, per-OS paths: https://github.com/bitranox/lib_layered_config/blob/master/docs/identifiers.md
- Configuration file structure: https://github.com/bitranox/lib_layered_config/blob/master/docs/config-file-structure.md
- CLI reference: https://github.com/bitranox/lib_layered_config/blob/master/docs/cli-reference.md
- Python API reference: https://github.com/bitranox/lib_layered_config/blob/master/docs/python-api.md
