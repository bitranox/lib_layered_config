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

**A `--set` style override names itself as the source (5.7.0 and later).** Every key
`with_overrides` supplies reads back from `origin()` as layer `override` (the exported
`OVERRIDE_LAYER`), path `None`, so a caller content with that label needs no provenance code of
its own. Keys it did not touch keep their file. When a scalar replaces a table, the scalar's key
(`db`) reads as `override` and the keys it removed (`db.host`) have no source at all:

```python
from lib_layered_config import Config

cfg = Config({"db": {"host": "a"}}, {"db.host": {"layer": "app", "path": "/etc/app.toml", "key": "db.host"}})
cfg.with_overrides({"db": {"host": "b"}}).origin("db.host")
# {'layer': 'override', 'path': None, 'key': 'db.host'}
```

Before 5.7.0 it returned the ORIGINAL provenance map, so a `--set` value was shown beside the file
it replaced: the value right, the answer to "where did this come from" wrong, and no test of the
value catches it. Check the floor in `pyproject.toml` before relying on the new behaviour.

To label the layer `cli` instead, or to support a floor below 5.7.0, rebuild provenance for exactly
the keys the override supplied - layer `cli`, path `None` - and leave every other key's source
alone. Three details decide whether that lands:

- the dotted key is the SECTION plus the key path, because a parsed override's key path EXCLUDES
  its section; joining only the key path matches nothing and silently changes no entry.
- overriding a key that no file defined must still record a source, or the key appears with a
  value and no origin at all.
- a `Config` you rebuild yourself takes a THIRD argument:
  `Config(data, provenance, NotSensitiveKeys.of(NOT_SENSITIVE))`, built from the same set your
  loader passes to `read_config(not_sensitive=...)`. It defaults to `NotSensitiveKeys.NONE`, so
  leaving it out drops the declaration silently, and a redacted display then masks keys the app
  declared safe. `with_overrides` carries the declaration through; only a hand-built `Config`
  loses it.

Assert it end to end, by running the command and reading the printed source, not by unit-testing
the merge: the merge is correct in isolation, and the defect only exists in what is displayed. Use
an override value that differs from every file layer, so a source still pointing at a file cannot
pass by showing the same value; and when the display redacts, check a declared not-sensitive key
still shows its value.

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

- Values coerce: `true`/`false` -> bool, `null`/`none` -> None, ints/floats, else string. A sensitive key
  (one `redact=True` masks: `password`, `token`, `secret`, `*_key`) keeps `null`/`none` as text
  unless declared with `read_config(not_sensitive=[...])`; a number under a sensitive key still converts.
- A value starting with `[` or `{` is parsed as JSON, in the environment AND unquoted in `.env`
  (`REPLICAS='["a","b"]'` in a shell, `REPLICAS=["a","b"]` in `.env`); a quoted `.env` value is always literal
  text; a comma list is never split.
- A number converts only when it reads back as the same text: `5` and `3.5` do, `007123`, `0640` and `1.50`
  stay strings.
- So an unquoted digit-only value with no leading zero (`DIR_MODE=2770`, a uid, an all-digit password)
  arrives as an `int`, in `.env` and the environment alike; the sensitive-key rule protects only
  `null`/`none`, never a number. A pydantic `str` field then fails startup with
  `Input should be a valid string [type=string_type, input_value=2770, input_type=int]`. Put
  `model_config = ConfigDict(coerce_numbers_to_str=True)` on one shared base class for every section
  model, not per field: the conversion is lossless, so the text comes back exactly as written, `int`
  fields stay ints, and field validators still check the text. Quoting the value fixes only that one
  line, and the next digit-only value breaks startup again. Pin it with a test that writes a real
  `.env` through the real loader and asserts the raw value is an `int` before the model parses it.
- A `.env` key is the key path WITHOUT the prefix: `DATABASE__HOST=db1`. A `MY_APP___DATABASE__HOST` line in
  `.env` does not override `database.host`; it creates a separate `my_app` section.
- An unquoted `.env` value converts exactly like an environment value; a quoted one stays literal text.
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

Notes: Linux `app`/`host` also read `/etc/<slug>/...`, after `/etc/xdg/<slug>/...`, so a key set in both
takes the `/etc/<slug>` value; Linux honours
`$XDG_CONFIG_HOME` for the user layer; Windows reads the user layer from
`%LOCALAPPDATA%\<Vendor>\<App>` when the `%APPDATA%` one holds no config file. Roots are
overridable for tests (`LIB_LAYERED_CONFIG_ETC`, `LIB_LAYERED_CONFIG_PROGRAMDATA`,
`LIB_LAYERED_CONFIG_MAC_APP_ROOT`, `LIB_LAYERED_CONFIG_MAC_HOME_ROOT`,
`LIB_LAYERED_CONFIG_APPDATA`, `LIB_LAYERED_CONFIG_LOCALAPPDATA`).

The dotenv row is only the LAST place searched. The dotenv layer first looks for `.env` in
`start_dir` and in every parent up to the filesystem root (the current directory and its parents
when `start_dir` is not given; a RELATIVE `start_dir` is not resolved, so its search covers
`start_dir` and its relative parents and ends at the current directory, not above it), then at the
per-user path above, and loads only the first file it finds. `dotenv_path=` (CLI `--env-file`)
loads that one file with no search.

## Probing and testing an app built on it

- **A probe or test started inside a repo loads that repo's `.env` secrets.** A `read_config`
  probe, the app's CLI, or its pytest run from a repo root finds the repo's local `.env` (upload
  tokens, passwords) by the upward search, and `config.as_dict()`, a full provenance dump or a
  pytest assertion diff prints them. A gitignored `.env` is absent in a fresh git worktree, so a
  test can pass there and leak in the main checkout's gate. Run probes from an empty temp
  directory and pass `start_dir=` that directory (or `dotenv_path=` a test file); in tests anchor
  every `start_dir` under `tmp_path` (or `monkeypatch.chdir(tmp_path)` first), never a relative
  path. Print only what the question is about (`config.get(key)`, `config.origin(key)`), or use
  `as_dict(redact=True)` / `to_json(redact=True)`. To isolate a run from every deployed layer
  too, point `HOME`, `XDG_CONFIG_HOME`, `APPDATA`, `LOCALAPPDATA` and the
  `LIB_LAYERED_CONFIG_*` roots above into that temp directory, and any network endpoint the app
  reads at a closed local port (`127.0.0.1:1`). Strip every inherited `LIB_LAYERED_CONFIG*` and
  `<SLUG>___` variable from the copied environment first, then set all six roots. The three APP
  roots are the ones a partial setup misses, `LIB_LAYERED_CONFIG_ETC`,
  `LIB_LAYERED_CONFIG_MAC_APP_ROOT` and `LIB_LAYERED_CONFIG_PROGRAMDATA`: each platform reads only
  its own, so a test that sets one is isolated on one OS and reads the deployed config on the
  others. Setting the OS variable
  `PROGRAMDATA` instead does nothing: without `LIB_LAYERED_CONFIG_PROGRAMDATA` the Windows
  resolver looks up `ProgramData` in a plain-dict copy of `os.environ`, whose keys Windows
  upper-cases, so the lookup misses and it reads the real `C:\ProgramData`.
- **A Windows user-layer deploy whose `%APPDATA%` directory does not exist writes under
  `%LOCALAPPDATA%` instead.** `deploy --target user` (and `deploy_config(..., targets=["user"])`)
  on Windows writes `%LOCALAPPDATA%\<Vendor>\<App>\config.toml` whenever the `%APPDATA%`
  directory is MISSING and `LIB_LAYERED_CONFIG_APPDATA` is unset; Linux and macOS have no such
  fallback. A fixture that sets `APPDATA` to a `tmp_path` subdirectory it never creates sends
  every Windows deploy elsewhere: a "file was written" check fails with the file not found, and
  a "the refused deploy wrote nothing" check passes whatever the deploy did. Create the
  directory in the fixture (`roaming.mkdir(parents=True)`), or set `LIB_LAYERED_CONFIG_APPDATA`,
  which disables the fallback.
- **Configured permission modes are not read on Windows.** Windows applies no modes, so a deploy
  there never reads `[lib_layered_config.default_permissions]` and cannot refuse an unsafe
  configured mode; it deploys. An explicit `--dir-mode`/`--file-mode` (`dir_mode=`/`file_mode=`)
  or a `permission_overrides` mode (what an app's `--set` passes) is still validated on every
  platform. Mark a test of a configured-mode refusal POSIX-only, and pin the Windows behaviour in
  its own arm: the deploy proceeds.

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

| Command             | Purpose                                                                                                                                                                         |
|---------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `read`              | Load and print config (human by default; `--format json`, `--redact`).                                                                                                          |
| `read-json`         | Print merged config + provenance as JSON.                                                                                                                                       |
| `deploy`            | Copy a config file into app/host/user layers (`--target`, `--profile`, `--force`/`--batch`, `--dir-mode`/`--file-mode`, `.bak`/`.ucf` conflict handling, permission hardening). |
| `generate-examples` | Scaffold an example config tree to bootstrap a project.                                                                                                                         |
| `env-prefix`        | Print the `<SLUG>___` env-var prefix for a slug.                                                                                                                                |
| `info`              | Print resolved package metadata.                                                                                                                                                |
| `fail`              | Raise a deliberate `RuntimeError`, to test how a harness reports a failing command.                                                                                             |

Flags are PER-SUBCOMMAND, not CLI-wide - run `<cmd> -h` before composing a call:

| Flag                                          | read | read-json | deploy | generate-examples | env-prefix | info |
|-----------------------------------------------|------|-----------|--------|-------------------|------------|------|
| `--vendor` / `--app` / `--slug`               | yes  | yes       | yes    | yes               | no         | no   |
| `--profile`                                   | yes  | yes       | yes    | no                | no         | no   |
| `--env-file <path>` (load an explicit `.env`) | yes  | yes       | no     | no                | no         | no   |
| `--redact` (mask secrets in output)           | yes  | yes       | no     | no                | no         | no   |

`env-prefix`, `info` and `fail` accept no options at all beyond `--help` (`env-prefix` takes a
positional SLUG). Passing one of the others raises `NoSuchOption`.

## Designing config files

- **Structure maps to access and to env vars.** A `[database]` section with `host = "..."`
  is read as `config.get("database.host")` and overridden by `MY_APP___DATABASE__HOST`. A
  `[database.pool]` subtable's `size` is `database.pool.size` / `MY_APP___DATABASE__POOL__SIZE`.
- **Keep secrets OUT of committed files.** Put passwords/tokens in the `env` layer or a
  `.env` file (both outrank the committed config); use `--redact` / `Config.to_json(redact=True)`
  when printing or logging. A key whose name only LOOKS secret (`max_token_bytes`) is declared with
  `read_config(..., not_sensitive=["performance.max_token_bytes"])`; the returned Config shows it
  under `redact=True` and in `display_config`.
- **Split large config with `.d/`.** `config.toml` may have a companion `config.d/` whose
  files (`10-db.toml`, `20-cache.yaml`, ...) load in lexicographic order and can mix formats.
- **Quote YAML keys that look like numbers or booleans** (`'1':`, `'true':`): an unquoted one is not a
  string key, and the loader refuses the whole file.
- **Write ordered YAML as a plain mapping, never `!!omap` or `!!pairs`**: a plain mapping keeps the
  file's key order through `read_config` and `as_dict()`, while those two tags load as `(key, value)`
  tuples whose keys redaction cannot see, so the loader refuses the whole file.
- **Write a set as a list and binary data as a base64 string, never `!!set` or `!!binary`**: those
  load as a Python `set` and `bytes`, which no JSON view can carry, so the loader refuses the whole file.
- **Write an integer outside `-2**63` to `2**64-1` as a string**: no JSON view can write one, so a TOML
  or YAML file holding it is refused whole, naming each integer's position and width.
- **Use profiles for environments**, not copy-pasted files.
- **Scaffold** a starting tree with `generate-examples` rather than hand-building paths.

## Python API beyond read_config

Everything below is importable from `lib_layered_config`.

**Errors.** Catch `ConfigError`, the base of every library error. Its subclasses:

- `LayerLoadError` - `read_config*` could not decode or parse a layer file (broken TOML, invalid
  UTF-8, a malformed `.env` line), or the loader refused one (a rule under "Designing config files").
- `InvalidFormatError` - a source cannot be parsed. `read_config*` re-raises it as `LayerLoadError`,
  so you meet it directly only from lower-level calls (nesting deeper than the limit in
  `redact_mapping`, for example).
- `NotFoundError` - an optional source is unavailable, e.g. a `.yaml` file without the `yaml` extra.
- `ValidationError` (also a `ValueError`) - an identifier or profile name is refused. Its subclasses
  `DeployModeError` (an unsafe or malformed mode, or `dir_mode`/`file_mode` given together with
  `set_permissions=False`) and `DeployPermissionsError` (unusable permission settings, one line per
  problem) come from deploy.

**Redaction helpers.** `is_sensitive("smtp_password")` -> `True` checks one key NAME against the
built-in patterns (a field named just `key` is not sensitive). `is_sensitive_at(("performance",
"max_token_bytes"), not_sensitive=NotSensitiveKeys.of([...]))` checks a key PATH and honours a
declaration; pass a tuple of segments, never a dotted `str` (refused with `TypeError`).
`redact_mapping(data, not_sensitive=["performance.max_token_bytes"])` returns a masked deep copy
of a plain dict; `not_sensitive` takes dotted paths or a `NotSensitiveKeys`. Use it on
`read_config_raw(...).data`, which does not carry the declaration.

**Profiles.** `validate_profile_name("production")` returns the name or raises `ValidationError`;
`is_valid_profile_name(name)` answers `True`/`False` instead. Both take `max_length=` (default 64).

**Deploying and scaffolding.** `deploy_config("app.toml", vendor=..., app=..., slug=..., targets=["user"])`
is the `deploy` command in Python (`source` is the path of the file to copy). It returns a list
with one `DeployResult` per destination: `.destination`, `.backup_path`, `.ucf_path`, and `.action`,
an enum - compare `.action.value == "created"` (or `"overwritten"`, `"kept"`, `"skipped"`), since
`.action == "created"` is always `False`. Permission keywords: `set_permissions`, `dir_mode`,
`file_mode`, `permissions=` (a whole `DeployPermissions`) and `permission_overrides={"user_file": "0o640"}`. `deploy_permissions_from_config(config)` builds a
`DeployPermissions` from a merged config's `[lib_layered_config.default_permissions]`.
`ModeKind.DIRECTORY` / `ModeKind.FILE` names which kind of mode a `DeployModeError` is about.
`force=True` backs up and overwrites an existing file, `batch=True` keeps it and writes a `.ucf`.
A missing source raises `FileNotFoundError`; a source or a file in its `.d` directory behind a
permission wall raises `PermissionError` on every Python, before anything is written.

**What a deploy sees, before it runs** (7.2.0 and later). `deploy_config_paths(source, vendor=...,
app=..., slug=..., targets=[...])` returns every file that deploy writes, resolved, as a frozenset:
each target's config file (`config.toml`, or `hosts/<hostname>.toml` for host) plus, in the `.d`
directory beside it (`config.d/`, `hosts/<hostname>.d/`), a copy of each file in the source's own `.d`
(`defaults.d/` for `defaults.toml`).
`read_deploy_config(source, vendor=..., app=..., slug=..., skip=...)` returns the configuration deploy
reads its modes from: the source as defaults, the app, host and user files not in `skip`, the
environment, never `.env`, and only `user_*`/`enabled` from a user file. Pass
`skip=deploy_config_paths(...)` for the deploy's exact read, or a subset (say, only the files that no
longer parse) to read past a broken file a forced deploy will replace; `skip` must be an iterable of
paths, never one bare path (`TypeError`). Both take `profile=`/`platform=` like `deploy_config`, raise
`FileNotFoundError` for a missing source, and a file not skipped (the source included) that does not
parse raises `LayerLoadError`. Then `perms = deploy_permissions_from_config(that_config,
overrides=<what you pass as permission_overrides>)`: `perms.enabled` says whether modes are set at all,
and `perms.for_layer("app" | "host" | "user")` gives a `LayerModes` whose `.directory` and `.file`
(each a `DeployMode`, printing as `0o700`) are that layer's modes, unless you pass an explicit
`dir_mode`/`file_mode`, which wins. Modes are never applied on Windows, and a deploy there never
reads the configured ones (see "Probing and testing an app built on it"). Use these instead of
importing anything from `lib_layered_config.core` or `lib_layered_config.examples.deploy`.
`generate_examples(destination, slug=..., vendor=..., app=...)` is `generate-examples` and returns
the list of written paths.

**Display and logging.** `display_config(config, output_format=OutputFormat.HUMAN)` prints a config
section by section, each key under a `# layer:<layer> profile:<profile> (<path>)` comment and
TOML-quoted where it needs it (`OutputFormat.JSON` for plain JSON). The `read` command has its own
renderer, `# source: layer=<layer>, path=<path>` above each key, so one parser does not fit both;
both quote keys, headers and strings the same way, so a key named `"a.b"` reads back as one key.
`get_logger()` returns the stdlib `logging.Logger` named `lib_layered_config`; attach handlers to
it. Each record carries a `context` dict: always `record.context["trace_id"]`, plus the event's
own fields (often `layer` and `path`). `bind_trace_id("abc123")` sets that trace id for the current
context (a `ContextVar`); `read_config*` and `deploy_config` tag their events with it and leave it
bound, and with nothing bound the id is `None`. `i_should_fail()` raises a `RuntimeError` on
purpose, for testing failure paths.

## Common mistakes

| Mistake                                                                              | Fix                                                                                                                                                    |
|--------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------|
| Env prefix with a single/double underscore (`MY_APP_...`)                            | The prefix ends in a **triple** underscore: `MY_APP___`. Run `env-prefix`.                                                                             |
| Forgetting the `defaults` layer or the `env`-wins ordering                           | Precedence is `defaults -> app -> host -> user -> dotenv -> env`.                                                                                      |
| Slugifying vendor/app for macOS/Windows paths                                        | `vendor`/`app` are used verbatim (spaces kept); only `slug` is normalized.                                                                             |
| Hunting for "why is this value X" by hand                                            | Use `config.origin(key)` or `read-json` - provenance is built in.                                                                                      |
| Committing a `.env` with secrets                                                     | `.env` is for local secrets only; never commit it; keep mode `0o600`.                                                                                  |
| Writing `user_file = 640` (a TOML int is decimal)                                    | Quote it: `user_file = "0o640"`; deploy refuses a bare integer and any group-writable, world-writable mode, or an execute bit on a file.               |
| Reaching for `--no-permissions` when deploy refuses a broken config                  | Give both `--dir-mode` and `--file-mode`; `--no-permissions` leaves a secrets file to the umask.                                                       |
| Building `permissions=` from the application's `read_config(...)` to carry a `--set` | Pass `permission_overrides={"user_file": "0o640"}`: the application's read includes `.env` and the deployed files, which deploy leaves out on purpose. |

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
