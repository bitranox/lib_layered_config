# CLI Reference

Full command-line reference for `lib_layered_config`, including the file-overwrite and
backup behavior and the per-layer permission and secret-handling guidance. For the
overview and installation see the [README](../README.md).

## CLI Usage

### Command Summary

| Command                                | Description                                           |
|----------------------------------------|-------------------------------------------------------|
| `lib_layered_config read`              | Load configuration (human readable by default)        |
| `lib_layered_config read-json`         | Emit config + provenance JSON envelope                |
| `lib_layered_config deploy`            | Copy a source file into one or more layer directories |
| `lib_layered_config generate-examples` | Scaffold example trees (POSIX/Windows layouts)        |
| `lib_layered_config env-prefix`        | Compute the canonical environment prefix              |
| `lib_layered_config info`              | Print package metadata                                |
| `lib_layered_config fail`              | Intentionally raise a `RuntimeError` (for testing)    |

### Global options and exit codes

Given before the command (`lib_layered_config --traceback read ...`):

| Option                           | Effect                                                                     |
|----------------------------------|----------------------------------------------------------------------------|
| `--version`                      | Print `lib_layered_config version <version>` and exit 0                    |
| `--traceback` / `--no-traceback` | On an error, print the full Python traceback on stderr instead of one line |
| `-h`, `--help`                   | Print the usage and exit 0                                                 |

A command exits 0 on success and with the error's code on failure:

| Failure                                                                                                                                   | Linux and macOS                                                                  | Windows                           |
|-------------------------------------------------------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------|-----------------------------------|
| A usage error: an unknown option, a missing or refused argument                                                                           | 2                                                                                | 2                                 |
| `ValidationError` or a subclass: a refused vendor, app, slug, profile, target or mode; a linked deploy destination; a relative layer root | 22                                                                               | 87                                |
| Any other library error: a file that cannot be read or parsed (`LayerLoadError`), no home directory (`HomeDirectoryUnknownError`)         | 1                                                                                | 1                                 |
| An operating-system error                                                                                                                 | its errno: 13 permission denied, 27 file too large, 28 disk full, 2 no such file | its Windows code: 5 access denied |

A path option naming a file that does not exist is a usage error (2), checked before the command runs. A file
that disappears while the command runs exits with its errno, also 2 on Linux and macOS; `--json` tells the two
apart by `error.type` (`BadParameter` against `FileNotFoundError`). When the reader of stdout goes away
first (`lib_layered_config info | head -0`), the command exits 141 and prints nothing more. That holds
for every output a command writes to stdout, so under `--json` a failure, whose envelope goes to stdout,
exits 141 too; without `--json` a failure is printed on stderr and keeps its own code.

### Machine-readable output: `--json`

Every command accepts `--json`. It replaces the command's normal output with one JSON document on
stdout, on success and on failure alike. Without `--json` the output is unchanged.

```bash
lib_layered_config env-prefix config-kit --json
# {"ok": true, "command": "env-prefix",
#  "data": {"slug": "config-kit", "prefix": "CONFIG_KIT___"}, "skipped": []}

lib_layered_config fail --json
# {"ok": false, "command": "fail",
#  "error": {"type": "RuntimeError", "message": "i should fail", "exit_code": 1}}
```

| Field             | Meaning                                                                                                          |
|-------------------|------------------------------------------------------------------------------------------------------------------|
| `ok`              | `true` when the command succeeded                                                                                |
| `command`         | the command that ran                                                                                             |
| `data`            | on success, the command's result (see the table below)                                                           |
| `skipped`         | on success, what the command deliberately left alone; `[]` for most commands                                     |
| `error.type`      | on failure, the exception class (`LayerLoadError`, `UsageError`, ...)                                            |
| `error.message`   | on failure, the message the command prints without `--json`, in full (printed, it is cut at 4000 characters)     |
| `error.exit_code` | on failure, the process exit code, the same one the command returns                                              |
| `error.written`   | `deploy` and `generate-examples`, on a failure after writing something: every path written, in order (see below) |

| Command             | `data`                                                                                                   |
|---------------------|----------------------------------------------------------------------------------------------------------|
| `read`, `read-json` | `{"config": ..., "provenance": ...}`; `provenance` is `null` under `--no-provenance`, `--redact` applies |
| `deploy`            | every result list, empty ones included, `.d` lists prefixed `dot_d_`                                     |
| `generate-examples` | `{"created": [paths], "skipped": [paths]}`; `skipped` holds the existing files kept without `--force`    |
| `info`              | the package metadata fields                                                                              |
| `env-prefix`        | `{"slug": ..., "prefix": ...}`                                                                           |

For `deploy`, `skipped` lists the destinations left alone because they already held the same
content, the `.d` directory's included. For `generate-examples`, it lists the example files that
already existed and were kept because `--force` was not given.

The exit code is the one the command returns without `--json`, so a script can branch on either. A
usage error Click finds while reading the arguments (a missing required option, a `--source` that
does not exist, an unknown option) prints the envelope too, with `error.type` set to Click's
exception (`MissingParameter`, `BadParameter`, `NoSuchOption`) and exit code 2. `--json` is
recognised as written among the command's arguments, so an option value spelled `--json` counts as
well. Two cases keep Click's usage text on stderr: an unknown command
(`lib_layered_config nosuch --json`), which fails before any command is chosen, and the same errors
without `--json`. An interrupt (Ctrl-C) exits with the signal's code and prints no envelope.

### Warnings on stderr

While a command runs, each warning the library logs is printed on stderr as one line, in every output
mode, `--json` included, so stdout and the envelope stay unchanged:

```text
warning: dotenv_skipped_foreign_owner layer=dotenv path=/tmp/.env owner_uid=1001
warning: type_conflict key=database layer=app path=/etc/xdg/myapp/config.toml old_type=scalar new_type=mapping
```

The events are `dotenv_skipped_foreign_owner`, `deploy_setting_ignored`, `deploy_directory_mode_skipped`,
`type_conflict`, `list_index_out_of_range`, `case_folded_key_ambiguous`, `user_layer_skipped_no_home` and
`host_layer_skipped_invalid_hostname`. Their fields are key names, paths, layers, types, owners, a
hostname and the reason it was refused, never configuration values, so a warning line cannot print a
secret. A field's value is printed as it is, spaces included (a `reason` holds several words), so read
a line by its field names rather than by splitting on spaces. A control
character in a key or path (a newline, an ESC) is printed as a `\uXXXX` escape, so a warning is always
one line and never sends a terminal sequence; a backslash prints as it is. A program that
calls the Python API instead gets the same events as WARNING records on the `lib_layered_config`
logger, which prints nothing until the application configures logging.

---

### `read`

Load configuration and print it either as TOML annotated with each value's source, or as JSON.

**Usage:**
```bash
lib_layered_config read --vendor Acme --app ConfigKit --slug config-kit \
  [--profile production] \
  [--start-dir /path/to/project] \
  [--default-file ./config.defaults.toml] \
  [--env-file /path/to/.env] \
  [--format human|json] \
  [--indent | --no-indent] \
  [--provenance | --no-provenance] \
  [--redact | --no-redact]
```

**Parameters:**

| Parameter                          | Type   | Required | Default        | Description                                                                                                                                                         |
|------------------------------------|--------|----------|----------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `--vendor`                         | string | Yes      | -              | Vendor namespace used to compute filesystem paths                                                                                                                   |
| `--app`                            | string | Yes      | -              | Application name used to compute filesystem paths                                                                                                                   |
| `--slug`                           | string | Yes      | -              | Configuration slug for file paths and environment prefix                                                                                                            |
| `--profile`                        | string | No       | -              | Configuration profile name (e.g., `test`, `production`). Reads the app, host and user files (and the user `.env` fallback) from their `profile/<name>/` directories |
| `--prefer`                         | string | No       | None           | Deprecated, no effect: each layer reads `config.toml` and `config.d/`. Prints a warning on stderr; removed in a future major release                                |
| `--start-dir`                      | path   | No       | current dir    | Starting directory for upward `.env` file search. Must be an existing directory                                                                                     |
| `--default-file`                   | path   | No       | None           | Path to lowest-precedence defaults file. Must be an existing file ending in `.toml`, `.json`, `.yaml` or `.yml`                                                     |
| `--env-file`                       | path   | No       | None           | Explicit `.env` file path. Skips upward directory search when set. Must exist; a FIFO such as `<(...)` is read too, waiting for its writer like `cat`               |
| `--format`                         | choice | No       | `human`        | Output format. Valid values: `human` (TOML with `# source:` comments), `json` (structured JSON)                                                                     |
| `--indent` / `--no-indent`         | flag   | No       | `--indent`     | Pretty-print JSON output with indentation. Only applies when `--format json`                                                                                        |
| `--provenance` / `--no-provenance` | flag   | No       | `--provenance` | Include provenance metadata in JSON output: with `--format json`, and in the `--json` envelope, where `--no-provenance` gives `"provenance": null`                  |
| `--redact` / `--no-redact`         | flag   | No       | `--redact`     | Mask sensitive values (passwords, tokens, `*_key`) as `***REDACTED***` in every format; `--no-redact` prints them                                                   |

**Examples:**

**Example 1: Basic configuration inspection (human-readable)**
```bash
# Load and display configuration in human-readable format
lib_layered_config read --vendor Acme --app MyApp --slug myapp
```

**Output:**
```
[service]
  # source: layer=app, path=/etc/xdg/myapp/config.toml
  timeout = 30
  # source: layer=user, path=/home/alice/.config/myapp/config.toml
  endpoint = "https://api.example.com"

[database]
  # source: layer=app, path=/etc/xdg/myapp/config.toml
  port = 5432
  # source: layer=env, path=(memory)
  host = "localhost"
```

**Explanation:** The default format prints the merged configuration as TOML, one table per section, with a `# source:` comment above each value naming the layer and file it came from (`(memory)` for a value from the environment). Here `MYAPP___DATABASE__HOST=localhost` was set in the environment. The output reads back as the TOML it shows, which makes it handy for quick debugging.

**Example 2: JSON output for automation scripts**
```bash
# Get configuration as JSON for use in shell scripts
config_json=$(lib_layered_config read \
  --vendor Acme --app MyApp --slug myapp \
  --format json --no-provenance --no-indent)

# Parse with jq
echo "$config_json" | jq -r '.database.host'
# Output: localhost
```

**Explanation:** Use `--format json --no-provenance --no-indent` to get just the configuration values as compact JSON, perfect for piping to `jq` or other JSON processors.

**Example 3: Full audit with provenance (JSON)**
```bash
# Get both configuration and provenance metadata
lib_layered_config read \
  --vendor Acme --app MyApp --slug myapp \
  --format json --provenance --indent > config-audit.json

# View the structure
cat config-audit.json
```

**Output:**
```json
{
  "config": {
    "service": {
      "timeout": 30,
      "endpoint": "https://api.example.com"
    },
    "database": {
      "host": "localhost",
      "port": 5432
    }
  },
  "provenance": {
    "service.timeout": {
      "layer": "app",
      "path": "/etc/xdg/myapp/config.toml",
      "key": "service.timeout"
    },
    "service.endpoint": {
      "layer": "user",
      "path": "/home/alice/.config/myapp/config.toml",
      "key": "service.endpoint"
    },
    "database.host": {
      "layer": "env",
      "path": null,
      "key": "database.host"
    }
  }
}
```

**Explanation:** This gives you complete audit information - both the final configuration values and where each one came from.

**Example 4: Settings split across TOML, JSON and YAML**
```bash
# ~/.config/myapp/config.toml           main file of the user layer
# ~/.config/myapp/config.d/10-db.json   merged after config.toml
# ~/.config/myapp/config.d/20-log.yaml  merged after 10-db.json
lib_layered_config read --vendor Acme --app MyApp --slug myapp
```

**Explanation:** Each layer's main file is `config.toml`; JSON and YAML files go in its `config.d/` directory, merged after `config.toml` in file-name order. The `--prefer` flag is deprecated and has no effect.

**Example 5: Load with defaults and specific .env location**
```bash
# Load configuration with shipped defaults and project-specific .env
lib_layered_config read \
  --vendor Acme --app MyApp --slug myapp \
  --default-file ./config/defaults.toml \
  --start-dir /opt/myapp \
  --format human
```

**Explanation:** Use `--default-file` to provide application defaults that ship with your app, and `--start-dir` to specify where to start searching for `.env` files (useful when running from a different directory). On Linux and macOS the search passes over a `.env` that neither you nor root owns, so a `.env` another user left in a parent directory such as `/tmp` is not loaded; the warning `dotenv_skipped_foreign_owner` names it.

**Example 6: Explicit .env file (skip directory search)**
```bash
# Load a specific .env file instead of searching upward
lib_layered_config read \
  --vendor Acme --app MyApp --slug myapp \
  --env-file /opt/myapp/secrets/.env.production
```

**Explanation:** Use `--env-file` to load a specific `.env` file directly. This bypasses the upward directory search entirely, and its owner check with it, which is useful in CI/CD pipelines or containers where the `.env` file lives in a known location.

**Example 7: Debugging configuration issues**
```bash
# Check if environment variables are overriding your config
MYAPP___SERVICE__TIMEOUT=5 lib_layered_config read \
  --vendor Acme --app MyApp --slug myapp \
  --format human | grep -B1 "timeout ="
```

**Output:**
```
  # source: layer=env, path=(memory)
  timeout = 5
```

**Explanation:** Set environment variables before the command to test how they override file-based configuration. The `# source:` comment sits on the line above its value, hence `grep -B1`, and shows which layer won.

---

### `read-json`

Always emit combined JSON output (config + provenance). This is a convenience alias for `read --format json --provenance`.

**Usage:**
```bash
lib_layered_config read-json --vendor Acme --app ConfigKit --slug config-kit \
  [--profile production] \
  [--start-dir /path/to/project] \
  [--default-file ./config.defaults.toml] \
  [--env-file /path/to/.env] \
  [--indent | --no-indent] \
  [--redact | --no-redact]
```

**Parameters:**

| Parameter                  | Type   | Required | Default     | Description                                                                                                                                                         |
|----------------------------|--------|----------|-------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `--vendor`                 | string | Yes      | -           | Vendor namespace                                                                                                                                                    |
| `--app`                    | string | Yes      | -           | Application name                                                                                                                                                    |
| `--slug`                   | string | Yes      | -           | Configuration slug                                                                                                                                                  |
| `--profile`                | string | No       | -           | Configuration profile name (e.g., `test`, `production`). Reads the app, host and user files (and the user `.env` fallback) from their `profile/<name>/` directories |
| `--prefer`                 | string | No       | None        | Deprecated, no effect; prints a warning on stderr                                                                                                                   |
| `--start-dir`              | path   | No       | current dir | Starting directory for `.env` search                                                                                                                                |
| `--default-file`           | path   | No       | None        | Path to defaults file                                                                                                                                               |
| `--env-file`               | path   | No       | None        | Explicit `.env` file (skips search)                                                                                                                                 |
| `--indent` / `--no-indent` | flag   | No       | `--indent`  | Pretty-print JSON output                                                                                                                                            |
| `--redact` / `--no-redact` | flag   | No       | `--redact`  | Mask sensitive values as `***REDACTED***`; `--no-redact` prints them                                                                                                |

**Example:**
```bash
lib_layered_config read-json --vendor Acme --app ConfigKit --slug config-kit --indent
```

---

### `deploy`

Copy a source configuration file into one or more layer directories.

**Usage:**
```bash
lib_layered_config deploy --source ./config/app.toml \
  --vendor Acme --app ConfigKit --slug config-kit \
  --target app [--target host] [--target user] \
  [--profile production] \
  [--platform linux|darwin|windows] \
  [--force] [--batch] \
  [--permissions | --no-permissions] [--dir-mode MODE] [--file-mode MODE]
```

**Parameters:**

| Parameter                            | Type   | Required | Default                       | Description                                                                                                                                                                                                          |
|--------------------------------------|--------|----------|-------------------------------|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `--source`                           | path   | Yes      | -                             | Path to the configuration file to copy. Must be an existing `.toml` file                                                                                                                                             |
| `--vendor`                           | string | Yes      | -                             | Vendor namespace                                                                                                                                                                                                     |
| `--app`                              | string | Yes      | -                             | Application name                                                                                                                                                                                                     |
| `--slug`                             | string | Yes      | -                             | Configuration slug                                                                                                                                                                                                   |
| `--profile`                          | string | No       | -                             | Configuration profile name (e.g., `test`, `production`). Adds `profile/<name>/` segment to deployment paths                                                                                                          |
| `--target`                           | choice | Yes      | -                             | Layer targets to deploy to (repeatable flag). Valid values: `app`, `host`, `user`. Can specify multiple: `--target app --target user`                                                                                |
| `--platform`                         | string | No       | auto-detect                   | Override platform. `linux`, `posix` give the Linux layout; `darwin`, `macos`, `mac` the macOS layout; `windows`, `win`, `win32`, `wine` the Windows layout; any case. Any other value is a usage error (exit code 2) |
| `--force`                            | flag   | No       | `false`                       | When file exists with different content: backup existing file to `.bak` and overwrite                                                                                                                                |
| `--batch`                            | flag   | No       | `false`                       | Non-interactive mode: keeps existing files and writes new config as `.ucf` for review (CI/CD pipelines). Combined with `--force` it is a usage error (exit code 2)                                                   |
| `--permissions` / `--no-permissions` | flag   | No       | configured `enabled`, else on | Set Unix file permissions on deployed files. Uses the configured modes, else app/host = 755/644 (world-readable), user = 700/600 (private). Skipped on Windows                                                       |
| `--dir-mode`                         | string | No       | -                             | Directory mode for every target, octal (`750` or `0o750`). Refused when unsafe (see File Permissions)                                                                                                                |
| `--file-mode`                        | string | No       | -                             | File mode for every target, octal (`640` or `0o640`). Refused when unsafe (see File Permissions)                                                                                                                     |

**Returns:** JSON object with keys for each action taken:
- `created`: Array of paths for newly created files
- `skipped`: Array of paths for files that were skipped (identical content)
- `overwritten`: Array of paths for files that were overwritten
- `backups`: Array of paths for backup files created (`.bak` files)
- `kept`: Array of paths for existing files that were kept
- `ucf_files`: Array of paths for UCF files created (`.ucf` files with new config)

Only non-empty arrays are included in the output.

**Profile Examples:**
```bash
# Deploy to production profile
lib_layered_config deploy --source ./configs/prod.toml \
  --vendor Acme --app MyApp --slug myapp \
  --profile production --target app
# Linux: /etc/xdg/myapp/profile/production/config.toml

# Deploy to test profile
lib_layered_config deploy --source ./configs/test.toml \
  --vendor Acme --app MyApp --slug myapp \
  --profile test --target app --target user
# Linux: /etc/xdg/myapp/profile/test/config.toml
#        ~/.config/myapp/profile/test/config.toml
```

---

### 🔒 File Overwrite Behavior

The `deploy` command has **safe-by-default** behavior with smart conflict handling:

#### **Source Check**

Before anything is written, `deploy` parses the source and every TOML, YAML or JSON file in its `.d`
directory with the same loaders the application uses. A file that does not parse is refused with the
loader's message (`config.toml is not valid TOML (line 1, column 9)`), whatever `--force`, `--batch`,
`--dir-mode`/`--file-mode` or `--no-permissions` say. Other files in the `.d` directory (a README) are
copied as they are.

The source itself must be a `.toml` file (any case): every destination is `config.toml` or
`hosts/<hostname>.toml`, which the application reads only as TOML. A `config.json`, `config.yaml` or
`app.conf` source is refused the same way, before anything is written: `<source> is not a .toml file, but
deploy writes it as config.toml or <hostname>.toml, which are read only as TOML`. Files in its `.d`
directory keep their own TOML, YAML or JSON format.

#### **Smart Skipping (Content-Aware)**

Before any conflict handling, the deploy command compares the source content with the existing destination file byte-by-byte. If the content is **identical**, the file is skipped without creating backups:

```bash
# First deployment - creates file
lib_layered_config deploy --source ./config.toml \
  --vendor Acme --app MyApp --slug myapp --target user
# Output: {"created": ["/home/alice/.config/myapp/config.toml"]}

# Second deployment with SAME content - smart skip (no backup needed)
lib_layered_config deploy --source ./config.toml \
  --vendor Acme --app MyApp --slug myapp --target user --force
# Output: {"skipped": ["/home/alice/.config/myapp/config.toml"]}
```

This prevents unnecessary `.bak` file proliferation when repeatedly deploying unchanged configurations.

#### **Default Behavior (Interactive Mode)**

When a file exists with **different content** and neither `--force` nor `--batch` is set:
- Prompts user with two options:
  - **[K]eep existing** - Save new config as `.ucf` (Update Configuration File) - **default**
  - **[O]verwrite** - Backup original to `.bak`, then write new file
- The prompt is written to stderr, so stdout carries only the JSON result. The answer can come from a
  pipe (`echo o | lib_layered_config deploy ...`).
- When no answer can be read (stdin at end of file), deploy exits with a usage error (exit code 2)
  naming the file and both unattended choices, `--batch` and `--force`. Files deployed before that
  conflict stay deployed.
- A deploy that stops on any error after writing something prints `deploy stopped after writing:` on
  stderr before the error, then each path it created, overwrote, backed up or kept as `.ucf`, one per
  line, in write order, a control character in a path printed as `\uXXXX`. Targets are written in the order given, so the same conflict leaves different
  files behind for `--target user --target app` and `--target app --target user`. With `--json` the
  same paths are the failure envelope's `error.written`, absent when nothing was written.

#### **With `--force` Flag:**
- **Creates new files** if they don't exist
- **Smart skips** if content is identical (no backup created)
- **Backs up and overwrites** if content differs - existing file saved to `.bak`
- 📋 Returns JSON with `overwritten` and `backups` arrays

```bash
# Force deploy with different content - creates backup
lib_layered_config deploy --source ./new-config.toml \
  --vendor Acme --app MyApp --slug myapp --target user --force
# Output: {"overwritten": ["/home/alice/.config/myapp/config.toml"],
#          "backups": ["/home/alice/.config/myapp/config.toml.bak"]}
```

#### **With `--batch` Flag:**
- **Creates new files** if they don't exist
- **Smart skips** if content is identical
- 📄 **Creates `.ucf` files** when content differs - keeps existing, writes new as `.ucf` for review
- 🛡 **Safe for CI/CD pipelines** - predictable behavior without user interaction

```bash
# Batch mode - keeps existing file, writes new config as .ucf for review
lib_layered_config deploy --source ./new-config.toml \
  --vendor Acme --app MyApp --slug myapp --target user --batch
# Output: {"kept": ["/home/alice/.config/myapp/config.toml"],
#          "ucf_files": ["/home/alice/.config/myapp/config.toml.ucf"]}
```

> **Note:** In `--batch` mode, when content differs, the new configuration is written to a `.ucf` file for manual review. This allows CI/CD pipelines to deploy updates without overwriting user customizations, while making new configs available for review.

#### **Numbered Backup Suffixes**

If `.bak` or `.ucf` files already exist, numbered suffixes are used:
- `config.toml.bak` → `config.toml.bak.1` → `config.toml.bak.2`
- `config.toml.ucf` → `config.toml.ucf.1` → `config.toml.ucf.2`

Any existing name counts as taken, a dangling symbolic link included, so a backup or `.ucf` file is
never written through a link someone left at that name.

#### **Symbolic Links**

If a destination, or one of its `.d` copies, is a symbolic link (dangling or not), deploy refuses it
before writing anything, in every mode, with or without `--force`/`--batch`:

```
~/.config/myapp/config.toml is a symbolic link; deploy neither writes through nor replaces one
```

Writing through the link would change the file it points at, and replacing it would break a link made
on purpose. Remove the link, or deploy its target yourself. Every linked destination is named, one per
line. A linked parent directory (`~/.config` itself a link) is followed as usual. A layer directory that is
a link (`~/.config/myapp` linked to a dotfiles checkout) is written through too, but deploy does not set the
layer's directory mode on the directory it links to, which it neither made nor owns at that path; it logs
`deploy_directory_mode_skipped` instead. The files still get their modes. Only the linked directory itself is
skipped: a directory deploy writes into below it (`config.d/`, `hosts/`, `profile/<name>/`) still gets the
layer's directory mode, inside the link's target, so a shared `config.d/` at 0755 becomes 0700 on the user
layer.

A destination that exists but is not a regular file (a directory, FIFO, device or socket) is refused
the same way, with `is not a regular file; deploy writes only regular files`.

Deploy copies and compares files a chunk at a time, so a large file in the `.d` directory costs no more
memory than a small one.

---

### Decision Flow Diagram

```
┌─────────────────────────────────────┐
│  lib_layered_config deploy          │
│  --source config.toml               │
│  --target user                      │
└──────────────────┬──────────────────┘
                   ▼
           ┌─────────────────┐
           │ Does destination│
           │   file exist?   │
           └───────┬─────────┘
             YES   │   NO
          ┌────────┴────────┐
          ▼                 ▼
    ┌───────────────┐ ┌─────────────┐
    │ Content same? │ │ Create file │
    └───────┬───────┘ │  (created)  │
       YES  │  NO     └─────────────┘
      ┌─────┴─────┐
      ▼           ▼
 ┌─────────┐ ┌───────────┐
 │  Skip   │ │ --force ? │
 │(skipped)│ └─────┬─────┘
 └─────────┘  YES  │  NO
            ┌──────┴───────┐
            ▼              ▼
       ┌─────────┐   ┌───────────┐
       │ Backup  │   │ --batch ? │
       │  .bak   │   └─────┬─────┘
       │Overwrite│    YES  │  NO
       │(overwr.)│   ┌─────┴─────┐
       └─────────┘   ▼           ▼
                ┌─────────┐ ┌──────────┐
                │Keep +   │ │ Prompt:  │
                │Write UCF│ │ K/O ?    │
                │ (kept)  │ │(default K)│
                └─────────┘ └──────────┘
```

---

### Practical Scenarios

#### **Scenario 1: Initial Installation**
```bash
# First time deploying - no files exist yet
sudo lib_layered_config deploy \
  --source ./dist/config.toml \
  --vendor Acme --app MyApp --slug myapp \
  --target app

# Result: File created
# Output: {"created": ["/etc/xdg/myapp/config.toml"]}
```

#### **Scenario 2: Redeploy Same Content (Smart Skip)**
```bash
# Deploy same config again - content identical
lib_layered_config deploy \
  --source ./dist/config.toml \
  --vendor Acme --app MyApp --slug myapp \
  --target app --force

# Result: Skipped (no backup created - content identical)
# Output: {"skipped": ["/etc/xdg/myapp/config.toml"]}
```

#### **Scenario 3: Update with Backup**
```bash
# Deploy new version with --force - creates automatic backup
lib_layered_config deploy \
  --source ./v2-config.toml \
  --vendor Acme --app MyApp --slug myapp \
  --target user --force

# Result: Old file backed up, new file written
# Output: {"overwritten": ["/home/alice/.config/myapp/config.toml"],
#          "backups": ["/home/alice/.config/myapp/config.toml.bak"]}
# User's old config is preserved in .bak file!
```

#### **Scenario 4: CI/CD Pipeline (Batch Mode)**
```bash
# Deploy in CI - keeps existing, writes new config as .ucf for review
lib_layered_config deploy \
  --source ./new-config.toml \
  --vendor Acme --app MyApp --slug myapp \
  --target app --batch

# Result: Creates new files, keeps existing and writes UCF for review
# Output: {"kept": ["/etc/xdg/myapp/config.toml"],
#          "ucf_files": ["/etc/xdg/myapp/config.toml.ucf"]}
```

#### **Scenario 5: Multiple Targets (Mixed Result)**
```bash
# Deploy to both app and user
# App: file exists with same content, User: no file exists
lib_layered_config deploy \
  --source ./config.toml \
  --vendor Acme --app MyApp --slug myapp \
  --target app --target user --force

# 📋 Result: App skipped (same content), user created
# Output: {"created": ["/home/alice/.config/myapp/config.toml"],
#          "skipped": ["/etc/xdg/myapp/config.toml"]}
```

#### **Scenario 6: Deploy to Specific User (as Root)**
```bash
# As root/admin, deploy user config for a specific user
# Uses sudo -u to run as that user, ensuring correct $HOME and permissions
sudo -u alice lib_layered_config deploy \
  --source ./user-defaults.toml \
  --vendor Acme --app MyApp --slug myapp \
  --target user

# Result: Config deployed to alice's home directory with correct ownership
# Output: {"created": ["/home/alice/.config/myapp/config.toml"]}
# File is owned by alice:alice with 600 permissions

# Deploy to multiple users in a loop
for user in alice bob charlie; do
  sudo -u "$user" lib_layered_config deploy \
    --source ./user-defaults.toml \
    --vendor Acme --app MyApp --slug myapp \
    --target user --batch
done
```

> **Why `sudo -u` instead of just `sudo`?** Running as root would deploy to `/root/.config/`, not the target user's home. Using `sudo -u <user>` ensures:
> - Correct `$HOME` directory resolution
> - Files owned by the target user (not root)
> - Proper user-layer permissions (700/600)

---

### Best Practices

#### **DO:**

1. **Use `--batch` for CI/CD pipelines:**
   ```bash
   # Predictable behavior - keeps existing, writes new as .ucf for review
   lib_layered_config deploy --source ./config.toml \
     --vendor Acme --app MyApp --slug myapp --target app --batch
   ```

2. **Use `--force` when you want automatic backups:**
   ```bash
   # Force creates .bak backup before overwriting
   lib_layered_config deploy --source ./new-config.toml \
     --vendor Acme --app MyApp --slug myapp --target user --force
   # Old config preserved in config.toml.bak
   ```

3. **Check the JSON output keys to understand what happened:**
   ```bash
   result=$(lib_layered_config deploy --source config.toml \
     --vendor Acme --app MyApp --slug myapp --target user --batch)

   # Check what action was taken
   if echo "$result" | jq -e '.created' > /dev/null 2>&1; then
     echo "New file created"
   elif echo "$result" | jq -e '.kept' > /dev/null 2>&1; then
     echo "File kept, new config at .ucf for review"
   elif echo "$result" | jq -e '.skipped' > /dev/null 2>&1; then
     echo "File skipped (identical content)"
   fi
   ```

4. **Document in installation scripts:**
   ```bash
   #!/bin/bash
   # Installation script

   echo "Deploying system-wide defaults..."
   result=$(sudo lib_layered_config deploy \
     --source ./defaults.toml \
     --vendor Acme --app MyApp --slug myapp \
     --target app --batch)

   if echo "$result" | jq -e '.created' > /dev/null 2>&1; then
     echo "Configuration deployed"
   elif echo "$result" | jq -e '.kept' > /dev/null 2>&1; then
     echo "ℹ  Configuration already exists, new config at .ucf for review"
   else
     echo "ℹ  Configuration unchanged (identical content)"
   fi
   ```

#### **DON'T:**

1. **Don't ignore the JSON output keys:**
   ```bash
   # BAD: Assuming array format
   result=$(lib_layered_config deploy --source config.toml --target user --batch)
   if [ "$result" = "[]" ]; then  # Wrong! Output is now a JSON object
     echo "Nothing deployed"
   fi

   # GOOD: Parse JSON properly
   result=$(lib_layered_config deploy --source config.toml --target user --batch)
   if echo "$result" | jq -e '.created' > /dev/null 2>&1; then
     echo "Files created"
   fi
   ```

2. **Don't forget to check backup files after `--force`:**
   ```bash
   # After force deploy, check for backups
   result=$(lib_layered_config deploy --source ./new-config.toml \
     --vendor Acme --app MyApp --slug myapp --target user --force)

   # If overwritten, backups array contains the .bak file paths
   echo "$result" | jq -r '.backups[]?' 2>/dev/null
   ```

---

### 🔐 File Permissions

The `deploy` command automatically sets appropriate Unix file permissions based on the target layer. This ensures configuration files have the right access controls without manual `chmod` commands.

#### Which mode is applied

For each target layer and each side (directory, file), the first of these wins:

1. `--dir-mode` / `--file-mode` (Python: `dir_mode` / `file_mode`);
2. the configured `[lib_layered_config.default_permissions]` setting for that layer;
3. the built-in layer mode:

| Layer  | Directory Mode    | File Mode         | Rationale                                         |
|--------|-------------------|-------------------|---------------------------------------------------|
| `app`  | `755` (rwxr-xr-x) | `644` (rw-r--r--) | System-wide config readable by all processes      |
| `host` | `755` (rwxr-xr-x) | `644` (rw-r--r--) | Machine-specific config readable by all processes |
| `user` | `700` (rwx------) | `600` (rw-------) | Private user config not accessible by others      |

`--permissions` / `--no-permissions` turns permission setting on or off; without either, a mode option turns it
on, and otherwise the configured `enabled` decides (on when unset).

#### Which modes are refused

A deployed file can hold credentials, so a mode may widen read access but nothing else. Refused, with every
offending bit named, before anything is written:

- anything outside 0..0o7777, and any text that is not a plain octal literal (`-1`, `7_5_0`, `0x1ed`, `10000`);
- the setuid, setgid and sticky bits;
- group write and world write (a group can be every local account, `staff` on macOS);
- for a directory, a mode without owner rwx; for a file, any execute bit or a mode without owner rw.

#### Configuring the modes

The deployed application's configuration can set the modes per layer:

```toml
[lib_layered_config.default_permissions]
app_directory = "0o750"
app_file = "0o640"
user_file = "0o600"
enabled = true
```

Write each mode as a quoted octal string. A bare integer is refused rather than guessed at: TOML reads
`user_file = 400` as the decimal 400 (0o620), and the TOML literal `0o640` arrives as the integer 416. In the
environment use the `0o` prefix (`MYAPP___LIB_LAYERED_CONFIG__DEFAULT_PERMISSIONS__USER_FILE=0o640`), since a
bare `640` there is a number (`0640` stays text and also works); the same goes for an application's `--set`
option, where `...user_file=640` arrives as a number and `...user_file=0o640` as text. `deploy` reads these
settings only when a configured value can change the result, from the deployed source (the defaults layer), the
app, host and user files it does not itself write, and the environment, taking `app_*` and `host_*` from all of
those except the user files (see below). It never reads `.env` (whose search
starts at the working directory), and the file being replaced never decides its replacement's mode, so a broken
destination does not block `deploy --force`. If those settings cannot be read, or the section is invalid,
`deploy` stops with one line per problem, naming the key and its source (and the line, for a file that cannot
be parsed) but never its content. Both `--dir-mode` and
`--file-mode` deploy anyway; `--no-permissions` does too, but leaves every mode to the umask, which can make a
user file that holds secrets readable by other accounts. `--no-permissions` together with a mode option is a
usage error.

Modes are applied to each file `deploy` writes. A file whose content already matches is skipped and keeps its
mode, so changing a configured mode and redeploying the same release changes nothing on disk; `chmod` the
file, or remove it and deploy again.

A deployed copy's own section is never consulted by the deploy that writes or keeps it. Two effects follow:
with `--batch` a file that differs is KEPT (the new content goes to a `.ucf` beside it) and stays the live
configuration, but the directory and the `.ucf` get their modes from the other layers, not from the kept copy;
and the result depends on the targets, since `--target app --target user` treats the app `config.toml` as a
destination and does not read its `user_*` settings, while `--target user` alone does. Put local settings in a
file the package does not ship, such as `config.d/99-local.toml` in the layer directory, which `deploy` never
writes, so it is read whenever the configured modes are.

`app_*` and `host_*` are taken only from the deployed source, the app and host files and the environment,
never from a user-layer file (the user `config.toml` or a file in the user `config.d/`); a user-layer file
decides only `user_*` and `enabled`. A root `deploy --target app` that runs with the invoking account's `HOME`
or `XDG_CONFIG_HOME` (`sudo -E`, or a sudoers rule that keeps `HOME`) therefore cannot widen the modes of the
system files it writes through that account's files. A user-layer `app_*` or `host_*` value is ignored, not
refused: it neither decides a mode nor hides one set in a lower layer (an app file's `app_file = "0o640"` applies
even when the user file says `"0o644"`), a malformed one does not stop the deploy, and each ignored key is logged
as a `deploy_setting_ignored` warning naming the key and the file, never the value.

The environment can still set `app_*` and `host_*`. A root deploy that keeps an environment the invoking
account controls (`sudo -E`) therefore reads that account's variables, and a mode there can widen the READ
access of the system files the deploy writes. It can never add write access or an execute bit, since the
refusal rules above hold for every source. Run a system-wide deploy with root's own environment (`sudo -i`), or
pass both `--dir-mode` and `--file-mode`, which no configured value overrides.

```bash
lib_layered_config deploy --source ./config.toml \
  --vendor Acme --app MyApp --slug myapp --target user --dir-mode 750 --file-mode 640
```

From Python, `deploy_config_paths(...)` lists the files a deploy writes and `read_deploy_config(..., skip=...)`
returns the configuration described above; see
[python-api.md](python-api.md#deploy_config_paths-and-read_deploy_config).

#### Python API Usage

```python
from lib_layered_config import deploy_config

# Configured or built-in modes per layer
deploy_config(source="./config.toml", vendor="Acme", app="MyApp", slug="myapp", targets=["user"])

# Explicit modes win over the configured ones
deploy_config(
    source="./config.toml", vendor="Acme", app="MyApp", slug="myapp", targets=["app"], dir_mode=0o750, file_mode=0o640
)

# Runtime overrides of the section (for example from a --set option) go on top of deploy's own read
deploy_config(
    source="./config.toml",
    vendor="Acme",
    app="MyApp",
    slug="myapp",
    targets=["user"],
    permission_overrides={"user_file": "0o640"},
)
```

`permission_overrides` takes the section's own setting names (`app_directory`, `app_file`, `host_directory`,
`host_file`, `user_directory`, `user_file`, `enabled`); a refused value is reported as `(source: override)`.
`{"enabled": False}` turns permission setting off without reading the configuration, like `set_permissions=False`
(unless a mode or `set_permissions=True` is also given, which set modes whatever `enabled` says).
`permissions=` takes a complete `DeployPermissions` instead and cannot be combined with it. Do not build that
object from your application's `read_config(...)` to carry overrides: that read includes `.env` (searched upward
from the working directory), the deployed files and a user file's `app_*`/`host_*` modes, which the deploy's own
read leaves out on purpose. `deploy_permissions_from_config` reads the merged `Config` it is given as it is, so
it does not apply the user-file rule above.

#### Platform Behavior

| Platform    | Behavior                                                |
|-------------|---------------------------------------------------------|
| **Linux**   | Full permission support via `chmod()`                   |
| **macOS**   | Full permission support via `chmod()`                   |
| **Windows** | Permissions skipped (Windows uses ACLs, not Unix modes) |

> **Note:** On Windows, file access control should be managed through Windows ACLs (Access Control Lists) using native tools like `icacls` or PowerShell's `Set-Acl`. The library sets no ACL of its own, but a deploy that replaces a file keeps the access list that file had: the new file, its `.bak` backup and a `.ucf` sidecar get the replaced file's DACL, protected or inherited as it was. A file deployed for the first time takes its directory's. Where the access list cannot be set, a replacing deploy stops with `cannot set the access list of <file>` (an `OSError` carrying the system's error code) before the destination is replaced; it does not fall back to a file its directory makes readable more widely. A volume without access lists (FAT, exFAT) is not affected.

---

### 🛡 Security Best Practices

#### Recommended Permissions by File Type

| File Type          | Location                       | Owner:Group     | Mode  | Notes                                |
|--------------------|--------------------------------|-----------------|-------|--------------------------------------|
| **App defaults**   | `/etc/xdg/<slug>/config.toml`  | `root:root`     | `644` | World-readable system defaults       |
| **Host overrides** | `/etc/xdg/<slug>/hosts/*.toml` | `root:root`     | `644` | Machine-specific settings            |
| **User config**    | `~/.config/<slug>/config.toml` | `<user>:<user>` | `600` | Private user preferences             |
| **Project `.env`** | `/path/to/project/.env`        | `<user>:<user>` | `600` | Contains secrets - highly restricted |
| **User `.env`**    | `~/.config/<slug>/.env`        | `<user>:<user>` | `600` | Contains secrets - highly restricted |

#### Dotenv Layer (`.env` Files)

`.env` files often contain secrets (API keys, database passwords, tokens) and should be **highly restricted**:

```bash
# Secure your .env files
chmod 600 .env
chmod 600 ~/.config/myapp/.env

# Verify permissions
ls -la .env
# -rw------- 1 alice alice 256 Jan 31 12:00 .env
```

> **Warning:** Never commit `.env` files to version control. Add `.env` to your `.gitignore`.

#### macOS Considerations

macOS respects Unix permissions but also has additional security layers:

```bash
# Set restrictive permissions on macOS
chmod 600 ~/Library/Application\ Support/Acme/MyApp/config.toml

# Check extended attributes (if any)
xattr -l ~/Library/Application\ Support/Acme/MyApp/config.toml
```

For applications distributed via App Store or notarized packages, additional entitlements may be required to access certain directories.

#### Windows Considerations

Windows uses Access Control Lists (ACLs) instead of Unix-style permissions:

```powershell
# View current ACL
Get-Acl "$env:APPDATA\Acme\MyApp\config.toml" | Format-List

# Set restrictive ACL (current user only)
$acl = Get-Acl "$env:APPDATA\Acme\MyApp\config.toml"
$acl.SetAccessRuleProtection($true, $false)
$rule = New-Object System.Security.AccessControl.FileSystemAccessRule(
    $env:USERNAME, "FullControl", "Allow")
$acl.SetAccessRule($rule)
Set-Acl "$env:APPDATA\Acme\MyApp\config.toml" $acl
```

A forced or confirmed deploy keeps such a restricted ACL on the new file and on its `.bak` and `.ucf` copies; the file's owner is not copied, a replaced file is owned by the user who deployed it.

For system-wide configuration in `%ProgramData%`, use Windows built-in permissions that allow read access for all users but write access only for administrators.

---

### 🔑 Recommendations for Sensitive Data

**Best Practice:** Don't store secrets in configuration files at all. Instead:

1. **Use environment variables** for secrets (highest precedence layer)
   ```bash
   export MYAPP___DATABASE__PASSWORD="secret123"
   # Config will have database.password = "secret123" from env layer
   ```

2. **Use `.env` files** with `600` permissions for local development
   ```bash
   # .env file (chmod 600)
   DATABASE__PASSWORD=secret123
   API__TOKEN=tok_abc123
   ```
   A `.env` key takes no `MYAPP___` prefix: `MYAPP___DATABASE__PASSWORD` in a `.env` file is read as
   `myapp._database.password`, not `database.password`.

3. **Use a secrets manager** for production
   - **HashiCorp Vault** - Enterprise-grade secret management
   - **AWS Secrets Manager** - Native AWS integration
   - **Azure Key Vault** - Native Azure integration
   - **Google Secret Manager** - Native GCP integration
   - **1Password CLI** - Developer-friendly with `op` CLI

   ```bash
   # Example: Inject secrets from Vault at runtime
   export MYAPP___DATABASE__PASSWORD=$(vault kv get -field=password secret/myapp/db)
   ```

4. **Use redaction** when displaying or logging configuration
   ```python
   from lib_layered_config import read_config

   config = read_config(vendor="Acme", app="MyApp", slug="myapp")

   # Redacted output for logs (masks passwords, tokens, etc.)
   safe_json = config.to_json(redact=True)
   print(safe_json)  # {"database": {"password": "***REDACTED***", "host": "localhost"}}

   # A key whose NAME looks secret but whose value is not: declare it once
   config = read_config(vendor="Acme", app="MyApp", slug="myapp", not_sensitive=["performance.max_token_bytes"])
   print(config.to_json(redact=True))  # max_token_bytes shown, passwords still masked
   ```

   A declaration covers its own path only: keys below it are still checked,
   and a masked section stays masked unless the section itself is declared. Only the Python API can
   declare; a config file or environment variable cannot unmask anything.

#### Environment Variable Security

Environment variables provide the highest precedence layer and are ideal for secrets because:

- Not stored in files (no accidental commits)
- Process-scoped (visible only to the process and its children)
- Easy to rotate (just restart with new values)
- Compatible with container orchestration (Kubernetes secrets, Docker secrets)

```bash
# Linux/macOS: Set secrets at runtime
MYAPP___DATABASE__PASSWORD=secret123 \
MYAPP___API__TOKEN=tok_abc123 \
python -m myapp

# Or export for the session
export MYAPP___DATABASE__PASSWORD=secret123
python -m myapp
```

---

### Python API Equivalent

The Python `deploy_config()` function returns `list[DeployResult]` with rich information:

```python
from lib_layered_config import DeployAction, deploy_config

# Deploy with batch mode (CI/CD safe)
results = deploy_config(
    source="./config.toml",
    vendor="Acme",
    app="MyApp",
    targets=["user"],
    slug="myapp",
    batch=True,  # Keep existing, write new as .ucf for review
)

for result in results:
    print(f"{result.action.value}: {result.destination}")
    if result.ucf_path:
        print(f"  UCF file: {result.ucf_path}")

# Force deploy with automatic backups
results = deploy_config(
    source="./config.toml",
    vendor="Acme",
    app="MyApp",
    targets=["user"],
    slug="myapp",
    force=True,  # Creates .bak backup before overwriting
)

for result in results:
    if result.action == DeployAction.OVERWRITTEN:
        print(f"Overwrote: {result.destination}")
        print(f"Backup at: {result.backup_path}")
    elif result.action == DeployAction.SKIPPED:
        print(f"Skipped (identical content): {result.destination}")
    elif result.action == DeployAction.CREATED:
        print(f"Created: {result.destination}")
```

**Examples:**

**Example 1: Deploy system-wide defaults during installation**
```bash
# Deploy app defaults to the system directory (requires sudo on Linux/macOS)
sudo lib_layered_config deploy \
  --source ./dist/config.toml \
  --vendor Acme --app MyApp --slug myapp \
  --target app
```

**Output:**
```json
{"created": ["/etc/xdg/myapp/config.toml"]}
```

**Explanation:** This copies your configuration file to the system-wide location (`/etc/xdg/myapp/config.toml` on Linux, `/Library/Application Support/Acme/MyApp/config.toml` on macOS, etc.). If the source has a companion `.d` directory (e.g., `./dist/config.d/`), those files are also deployed to `/etc/xdg/myapp/config.d/`. This is typically done during package installation.

**Example 2: Deploy user-specific configuration**
```bash
# Deploy user config (no sudo needed)
lib_layered_config deploy \
  --source ./my-preferences.toml \
  --vendor Acme --app MyApp --slug myapp \
  --target user
```

**Output:**
```json
{"created": ["/home/alice/.config/myapp/config.toml"]}
```

**Explanation:** Deploys configuration to the current user's config directory. Great for user onboarding or preference templates.

**Example 3: Deploy to multiple layers with --force**
```bash
# Deploy base configuration to both system and user levels
lib_layered_config deploy \
  --source ./config/base.toml \
  --vendor Acme --app MyApp --slug myapp \
  --target app --target user \
  --force
```

**Output (if content differs from existing files):**
```json
{
  "overwritten": ["/etc/xdg/myapp/config.toml", "/home/alice/.config/myapp/config.toml"],
  "backups": ["/etc/xdg/myapp/config.toml.bak", "/home/alice/.config/myapp/config.toml.bak"]
}
```

**Output (if content is identical - smart skip):**
```json
{"skipped": ["/etc/xdg/myapp/config.toml", "/home/alice/.config/myapp/config.toml"]}
```

**Explanation:** Using multiple `--target` flags deploys the same file to multiple locations. The `--force` flag creates `.bak` backups before overwriting. If content is identical, files are skipped without creating backups.

**Example 4: Cross-platform deployment**
```bash
# Deploy for Windows even when running on Linux (for CI/testing)
lib_layered_config deploy \
  --source ./config.toml \
  --vendor Acme --app MyApp --slug myapp \
  --target user \
  --platform windows
```

**Output:**
```json
{"created": ["C:\\Users\\alice\\AppData\\Roaming\\Acme\\MyApp\\config.toml"]}
```

**Explanation:** Use `--platform` to override platform detection. Useful for testing deployment paths on different platforms without actually being on that platform.
The `app` and `host` targets need an absolute ProgramData root there: set
`LIB_LAYERED_CONFIG_PROGRAMDATA` (or `ProgramData`). Off Windows the built-in `C:\ProgramData` is a
relative path, so the deploy is refused (exit 22) and nothing is written. A relative value in any of
the Windows root variables is refused the same way, on every platform.

**Example 5: Deploy host-specific configuration**
```bash
# Deploy configuration specific to this server
hostname=$(hostname)
lib_layered_config deploy \
  --source ./hosts/${hostname}.toml \
  --vendor Acme --app MyApp --slug myapp \
  --target host
```

**Output:**
```json
{"created": ["/etc/xdg/myapp/hosts/server-01.toml"]}
```

**Explanation:** Host-specific configurations are stored in the `hosts/` subdirectory with the hostname as the filename. They override app defaults but only on machines with matching hostnames.

**Example 6: CI/CD deployment with --batch**
```bash
# Deploy in CI pipeline - keeps existing, writes new as .ucf for review
lib_layered_config deploy \
  --source ./config.toml \
  --vendor Acme --app MyApp --slug myapp \
  --target user \
  --batch

# If file exists with identical content - smart skipped
# Output: {"skipped": ["/home/alice/.config/myapp/config.toml"]}

# If file exists with different content - kept and UCF created
# Output: {"kept": ["/home/alice/.config/myapp/config.toml"],
#          "ucf_files": ["/home/alice/.config/myapp/config.toml.ucf"]}

# If file doesn't exist - created
# Output: {"created": ["/home/alice/.config/myapp/config.toml"]}
```

**Explanation:** Use `--batch` for non-interactive deployments in CI/CD pipelines. When content differs, the existing file is kept and the new config is written to a `.ucf` file for manual review, making automation predictable while preserving user customizations.

---

### `generate-examples`

Generate example configuration trees for documentation or onboarding.

**Usage:**
```bash
lib_layered_config generate-examples --destination ./examples \
  --vendor Acme --app ConfigKit --slug config-kit \
  [--platform posix|windows] \
  [--force | --no-force]
```

**Parameters:**

| Parameter                | Type   | Required | Default      | Description                                                                                                                                                                                                                                                      |
|--------------------------|--------|----------|--------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `--destination`          | path   | Yes      | -            | Directory that will receive the example tree. Will be created if it doesn't exist                                                                                                                                                                                |
| `--slug`                 | string | Yes      | -            | Configuration slug used in generated files                                                                                                                                                                                                                       |
| `--vendor`               | string | Yes      | -            | Vendor namespace interpolated into examples                                                                                                                                                                                                                      |
| `--app`                  | string | Yes      | -            | Application name interpolated into examples                                                                                                                                                                                                                      |
| `--platform`             | string | No       | auto-detect  | Override platform layout. `posix`, `linux`, `darwin`, `macos`, `mac` write the POSIX layout (`xdg/`, `home/`); `windows`, `win`, `win32`, `wine` write the Windows layout (`ProgramData/`, `AppData/`); any case. Any other value is a usage error (exit code 2) |
| `--force` / `--no-force` | flag   | No       | `--no-force` | Overwrite existing example files                                                                                                                                                                                                                                 |

**Returns:** JSON array of file paths created; existing files kept without `--force` are not in it
(`--json` lists them under `skipped`). A `--slug`, `--vendor` or `--app` that is not a
safe path segment (`../x`, an absolute path, a control character) is refused with
`ValidationError` before anything is written, as `read` and `deploy` refuse it. With `--force`, an
example path that is a symbolic link or not a regular file (a directory, FIFO, device or socket) is
refused with `GenerateDestinationError` (exit code 22 on Linux and macOS, 87 on Windows), one line per path, before anything is
written; without `--force` only a link that resolves to nothing is refused, and anything else already
there is kept. A run that stops on any error after writing some examples (a regular file where a
directory must go, a permission wall, a full disk, an interrupt) prints `generate-examples stopped after
writing:` on stderr before the error, then each example it wrote, one per line, in write order, a
control character in a path printed as `\uXXXX`. With `--json` the same paths are the failure envelope's
`error.written`, absent when nothing was written.

**Examples:**

**Example 1: Generate examples for your project documentation**
```bash
# Create example configuration files in your docs directory
lib_layered_config generate-examples \
  --destination ./docs/configuration-examples \
  --vendor Acme --app MyApp --slug myapp
```

**Output:**
```json
[
  "/path/to/docs/configuration-examples/xdg/myapp/config.toml",
  "/path/to/docs/configuration-examples/xdg/myapp/hosts/your-hostname.toml",
  "/path/to/docs/configuration-examples/home/myapp/config.toml",
  "/path/to/docs/configuration-examples/home/myapp/config.d/10-override.toml",
  "/path/to/docs/configuration-examples/.env.example"
]
```

**File contents preview:**
```toml
# docs/configuration-examples/xdg/myapp/config.toml
# Application-wide defaults for myapp
[service]
endpoint = "https://api.example.com"
timeout = 10
```

**Explanation:** Creates a complete set of example configuration files showing users how to configure your application. Include these in your documentation or repository.

**Example 2: Generate both POSIX and Windows examples**
```bash
# Generate Linux/macOS examples
lib_layered_config generate-examples \
  --destination ./docs/examples/unix \
  --vendor Acme --app MyApp --slug myapp \
  --platform posix

# Generate Windows examples
lib_layered_config generate-examples \
  --destination ./docs/examples/windows \
  --vendor Acme --app MyApp --slug myapp \
  --platform windows
```

**Explanation:** Generate platform-specific examples for comprehensive documentation. Windows examples use paths like `ProgramData\Acme\MyApp\config.toml`, while POSIX examples use `/etc/xdg/myapp/config.toml`.

**Example 3: Update examples after configuration changes**
```bash
# Regenerate examples with --force to update them
lib_layered_config generate-examples \
  --destination ./examples \
  --vendor Acme --app MyApp --slug myapp \
  --force
```

**Explanation:** When you update your configuration schema, use `--force` to regenerate all example files. This ensures your documentation stays in sync with your application.

**Example 4: Generated file structure (POSIX)**
```bash
lib_layered_config generate-examples \
  --destination ./examples \
  --vendor Acme --app MyApp --slug myapp \
  --platform posix

# View the generated files
cd ./examples && find . -type f | sort
```

**Output:**
```
./.env.example                            # .env template: copy to .env (keys take no prefix)
./home/myapp/config.d/10-override.toml    # user layer: split overrides, applied in lexical order
./home/myapp/config.toml                  # user layer: belongs in ~/.config/myapp/
./xdg/myapp/config.toml                   # app layer: belongs in /etc/xdg/myapp/
./xdg/myapp/hosts/your-hostname.toml      # host layer: belongs in /etc/xdg/myapp/hosts/
```

**Explanation:** `xdg/` holds the system-wide files (app and host layers, installed under `/etc/xdg/`) and `home/` the per-user ones (installed under `~/.config/`), so users can see which file goes where.

**Example 5: Use examples as onboarding templates**
```bash
# Generate examples in a temp directory
lib_layered_config generate-examples \
  --destination /tmp/myapp-examples \
  --vendor Acme --app MyApp --slug myapp

# User can copy these to actual locations
echo "To get started, copy these examples:"
echo "  sudo cp /tmp/myapp-examples/xdg/myapp/config.toml /etc/xdg/myapp/"
echo "  cp /tmp/myapp-examples/home/myapp/config.toml ~/.config/myapp/"
echo "  cp /tmp/myapp-examples/.env.example .env"
```

**Explanation:** Generate examples in a temporary location, then provide instructions for users to copy them to the actual configuration directories.

**Example 6: CI/CD - Validate configuration structure**
```bash
#!/bin/bash
# In your CI pipeline, generate examples and validate them

# Generate examples
lib_layered_config generate-examples \
  --destination ./ci-examples \
  --vendor Acme --app MyApp --slug myapp

# Check that all expected files were created
expected_files=(
  "xdg/myapp/config.toml"
  "home/myapp/config.toml"
  ".env.example"
)

for file in "${expected_files[@]}"; do
  if [ ! -f "./ci-examples/$file" ]; then
    echo "ERROR: Missing example file: $file"
    exit 1
  fi
done

echo "✓ All configuration examples are valid"
```

**Explanation:** Use in CI/CD to ensure your configuration structure is correct and all example files can be generated successfully.

---

### `env-prefix`

Compute the canonical environment variable prefix for a configuration slug.

**Usage:**
```bash
lib_layered_config env-prefix <slug>
```

**Parameters:**

| Parameter | Type   | Required         | Default | Description                                         |
|-----------|--------|------------------|---------|-----------------------------------------------------|
| `slug`    | string | Yes (positional) | -       | Configuration slug to convert to environment prefix |

**Returns:** Uppercase environment prefix with dashes converted to underscores. A slug `read` and `deploy`
refuse (they exit 22) is a usage error here (exit code 2), because the slug is this command's only argument: an empty one (`slug cannot be empty`), one holding a path
separator or whitespace (`slug contains invalid characters: ../x`), starting with a dot, or non-ASCII.
A refusal names the value it refused with each control character written as `\uXXXX` (`demo\u000a` for a
slug ending in a newline), so a trailing newline is visible and an ESC never reaches the terminal raw; a
backslash prints as it is. The same holds for the vendor, app and hostname refusals and for a layer
root that is not absolute.

A dot in the slug stays in the prefix (`my.app` gives `MY.APP___`), and so does a leading digit (`2app` gives
`2APP___`). Such a variable is read like any other, but no POSIX shell can `export` the name, so the command adds
a note on stderr saying so; stdout and the `--json` data are unchanged. Set those variables with env(1)
(`env 'MY.APP___DB__HOST=x' myapp`) or a container's or service's environment, or choose a slug that starts with
a letter and holds only letters, digits, `-` and `_`.

**Examples:**

**Example 1: Check what environment prefix your app uses**
```bash
lib_layered_config env-prefix myapp
```

**Output:**
```
MYAPP___
```

**Explanation:** This shows the environment variable prefix for your application (including the `___` separator). Use this prefix with double underscores for nested keys: `MYAPP___DATABASE__HOST`, `MYAPP___SERVICE__TIMEOUT`.

**Example 2: Generate documentation for users**
```bash
#!/bin/bash
# Script to document environment variables

app_slug="myapp"
prefix=$(lib_layered_config env-prefix "$app_slug")

cat << EOF
Environment Variables for $app_slug
====================================

All environment variables must be prefixed with: ${prefix}

Examples:
  ${prefix}DATABASE__HOST=localhost
  ${prefix}DATABASE__PORT=5432
  ${prefix}SERVICE__TIMEOUT=30
  ${prefix}SERVICE__RETRY__MAX_ATTEMPTS=3

Note: Use double underscores (__) to denote nesting in configuration keys.
EOF
```

**Output:**
```
Environment Variables for myapp
====================================

All environment variables must be prefixed with: MYAPP___

Examples:
  MYAPP___DATABASE__HOST=localhost
  MYAPP___DATABASE__PORT=5432
  MYAPP___SERVICE__TIMEOUT=30
  MYAPP___SERVICE__RETRY__MAX_ATTEMPTS=3

Note: Use double underscores (__) to denote nesting in configuration keys.
```

**Explanation:** Use this in documentation generation scripts to automatically show users the correct environment variable format.

**Example 3: Validate environment variables in a script**
```bash
#!/bin/bash
# Validate that users have set required environment variables

app_slug="config-kit"
prefix=$(lib_layered_config env-prefix "$app_slug")

required_vars=(
  "${prefix}DATABASE__HOST"
  "${prefix}DATABASE__PASSWORD"
  "${prefix}API__SECRET_KEY"
)

missing=()
for var in "${required_vars[@]}"; do
  if [ -z "${!var}" ]; then
    missing+=("$var")
  fi
done

if [ ${#missing[@]} -gt 0 ]; then
  echo "Error: Missing required environment variables:"
  printf '  %s\n' "${missing[@]}"
  exit 1
fi

echo "✓ All required environment variables are set"
```

**Explanation:** Programmatically check that required environment variables are set with the correct prefix before starting your application.

**Example 4: Set test environment variables**
```bash
# In a test script, set environment variables with the correct prefix
prefix=$(lib_layered_config env-prefix myapp)

export ${prefix}DATABASE__HOST="test-db.local"
export ${prefix}DATABASE__PORT="5432"
export ${prefix}SERVICE__TIMEOUT="5"

# Run tests
python -m pytest tests/
```

**Explanation:** Dynamically generate environment variable names for testing, ensuring they match your application's expected prefix.

---

### `info`

Print package metadata: name, title, version, homepage, author, author e-mail and shell command.

**Usage:**
```bash
lib_layered_config info
```

**Parameters:** only `--json` (see [Machine-readable output](#machine-readable-output---json))

**Example:**
```bash
lib_layered_config info
```

---

### `fail`

Intentionally raise a `RuntimeError` for testing error handling and CLI behavior.

**Usage:**
```bash
lib_layered_config fail
```

**Parameters:** only `--json` (see [Machine-readable output](#machine-readable-output---json))

**Raises:** `RuntimeError` with message `"i should fail"`.

**Example:**
```bash
lib_layered_config fail
# Output: RuntimeError: i should fail
# Exit code: 1
```
