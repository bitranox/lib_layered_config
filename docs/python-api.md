# Python API Reference

Full Python API reference for `lib_layered_config`. For the overview and installation see
the [README](../README.md).

## Python API

```python
from lib_layered_config import (
    Config,
    Layer,
    read_config,
    read_config_json,
    read_config_raw,
    MergeResult,  # what read_config_raw returns
    default_env_prefix,
    deploy_config,
    deploy_config_paths,
    deployed_before_failure,  # what a failed deploy_config wrote first
    read_deploy_config,
    DeployResult,  # what deploy_config returns, one per file
    DeployAction,
    generate_examples,
    i_should_fail,
    # Profile validation
    DEFAULT_MAX_PROFILE_LENGTH,
    validate_profile_name,
    is_valid_profile_name,
    # Permission constants (for deploy_config)
    DEFAULT_APP_DIR_MODE,
    DEFAULT_APP_FILE_MODE,
    DEFAULT_USER_DIR_MODE,
    DEFAULT_USER_FILE_MODE,
    # Deploy permission types (for deploy_config's dir_mode/file_mode/permissions/permission_overrides)
    DeployMode,
    ModeKind,
    DeployModeError,
    DeployDestinationError,
    GenerateDestinationError,
    LayerModes,
    DeployPermissions,
    DeployPermissionsError,
    PermissionProblem,
    deploy_permissions_from_config,
    # Display and logging
    display_config,
    OutputFormat,
    get_logger,
    bind_trace_id,
    # Errors
    ConfigError,
    LayerLoadError,
    InvalidFormatError,
    NotFoundError,
    ValidationError,
)
```

### `Layer` Enum

The `Layer` enum provides type-safe constants for configuration layer names:

```python
from lib_layered_config import Layer

# Available layers (in precedence order, lowest to highest):
Layer.DEFAULTS  # "defaults" - bundled application defaults
Layer.APP  # "app" - system-wide application config
Layer.HOST  # "host" - machine-specific overrides
Layer.USER  # "user" - per-user preferences
Layer.DOTENV  # "dotenv" - project-local .env file
Layer.ENV  # "env" - environment variables (highest precedence)

# Layer values are strings, so they work seamlessly with provenance:
origin = config.origin("service.timeout")
if origin and origin["layer"] == Layer.ENV:
    print("Value comes from environment variable")
```

### `Config` Class

Immutable configuration value object with provenance tracking and dotted-path lookups.

#### Methods

##### `Config.get(key, default=None)`

Return the value for a dotted key path or a default when the path is missing.

**Parameters:**
- `key` (str, required): Dotted path identifying nested entries (e.g., `"service.timeout"` or `"db.host"`).
- `default` (Any, optional): Value to return when the path does not resolve or encounters a non-mapping. Default: `None`.

**Returns:** The resolved value or `default` when missing.

**Examples:**

**Example 1: Basic dotted-path lookup**
```python
from lib_layered_config import read_config

# Load configuration
config = read_config(vendor="Acme", app="Demo", slug="demo")

# Access nested configuration values using dotted paths
timeout = config.get("service.timeout", default=30)
endpoint = config.get("service.endpoint")
db_host = config.get("database.host", default="localhost")

print(f"Service timeout: {timeout}s")
print(f"Service endpoint: {endpoint}")
print(f"Database host: {db_host}")
```
**Explanation:** The `get` method traverses nested dictionaries using dot notation. If `service.timeout` exists in your configuration, it returns that value; otherwise, it returns the default (30).

**Example 2: Handling missing keys gracefully**
```python
# This returns None if the key doesn't exist
api_key = config.get("api.secret_key")
if api_key is None:
    print("Warning: API key not configured")

# This returns a default value
max_retries = config.get("api.max_retries", default=3)
print(f"Max retries: {max_retries}")
```
**Explanation:** When you don't provide a default, `get` returns `None` for missing keys. This is useful for optional configuration values where you need to check if they were configured.

**Example 3: Deep nested paths**
```python
# Access deeply nested configuration
smtp_host = config.get("email.smtp.host", default="smtp.gmail.com")
smtp_port = config.get("email.smtp.port", default=587)
use_tls = config.get("email.smtp.tls.enabled", default=True)

print(f"SMTP: {smtp_host}:{smtp_port} (TLS: {use_tls})")
```
**Explanation:** The dotted path can be arbitrarily deep. If any intermediate key is missing or not a dictionary, the default value is returned.

##### `Config.origin(key)`

Return provenance metadata for a dotted key when available.

**Parameters:**
- `key` (str, required): Dotted key in the metadata map (e.g., `"service.timeout"`).

**Returns:** Dictionary with keys `layer` (str), `path` (str | None), and `key` (str), or `None` if the key was never observed. A table that holds values has no entry of its own (its values carry theirs), so `origin()` returns `None` for it; an empty table reports where it was last declared.

**Examples:**

**Example 1: Check where a value came from**
```python
from lib_layered_config import read_config

config = read_config(vendor="Acme", app="Demo", slug="demo")

# Get provenance information
timeout_origin = config.origin("service.timeout")
if timeout_origin:
    print(f"service.timeout = {config.get('service.timeout')}")
    print(f"  Layer: {timeout_origin['layer']}")
    print(f"  Source: {timeout_origin['path'] or 'environment variable'}")
    print(f"  Key: {timeout_origin['key']}")

# Output example:
# service.timeout = 30
#   Layer: env
#   Source: environment variable
#   Key: service.timeout
```
**Explanation:** The `origin` method tells you which configuration layer provided a value. This is crucial for debugging when you need to understand why a particular value is being used.

**Example 2: Debugging configuration precedence**
```python
# Check multiple values to understand the configuration hierarchy
keys_to_check = ["database.host", "database.port", "service.timeout"]

for key in keys_to_check:
    value = config.get(key)
    origin = config.origin(key)

    if origin:
        layer = origin["layer"]
        source = origin["path"] or "(ephemeral)"
        print(f"{key}: {value} [from {layer}] {source}")
    else:
        print(f"{key}: Not configured")

# Output example:
# database.host: localhost [from user] /home/alice/.config/demo/config.toml
# database.port: 5432 [from app] /etc/demo/config.toml
# service.timeout: 30 [from env] (ephemeral)
```
**Explanation:** This shows how to audit your entire configuration to see which layer each value came from. Useful when troubleshooting unexpected configuration values.

**Example 3: Validate configuration source for security**
```python
# Ensure sensitive values come from environment or dotenv
sensitive_keys = ["api.secret_key", "database.password"]

for key in sensitive_keys:
    origin = config.origin(key)
    if origin:
        if origin["layer"] not in ["env", "dotenv"]:
            print(f"WARNING: {key} should come from env/dotenv, not {origin['layer']}")
            print(f"  Currently in: {origin['path']}")
    else:
        print(f"ERROR: {key} is not configured!")

# This helps ensure secrets aren't committed to config files
```
**Explanation:** You can use provenance to enforce security policies, ensuring sensitive values only come from appropriate sources (environment variables or .env files, not checked-in config files).

##### `Config.as_dict(*, redact=False)`

Return a deep, mutable copy of the configuration tree.

**Parameters:**
- `redact` (bool, optional): Replace the values of sensitive keys with `***REDACTED***`; keys declared through `read_config(not_sensitive=...)` stay visible. Default: `False`.

**Returns:** Dictionary containing a deep copy of all configuration data.

**Examples:**

**Example 1: Export configuration for serialization**
```python
from lib_layered_config import read_config
import json

config = read_config(vendor="Acme", app="Demo", slug="demo")

# Get a mutable copy of the entire configuration
data = config.as_dict()

# Now you can serialize it however you want
with open("config-snapshot.json", "w") as f:
    json.dump(data, f, indent=2)

print("Configuration exported to config-snapshot.json")
```
**Explanation:** Use `as_dict()` when you need to export or serialize the configuration data. The returned dictionary is completely independent from the original Config object.

**Example 2: Modify configuration copy for testing**
```python
# Create a modified copy for testing without affecting the original
test_config = config.as_dict()
test_config["database"]["host"] = "test-db.example.com"
test_config["service"]["timeout"] = 1  # Short timeout for tests

# Original config is unchanged
print(f"Original DB: {config.get('database.host')}")  # localhost
print(f"Test DB: {test_config['database']['host']}")  # test-db.example.com
```
**Explanation:** This is useful in tests where you want to create variations of your configuration without modifying the immutable Config object.

##### `Config.get_redacted(key, default=None)`

Return the value at a dotted key as `as_dict(redact=True)` shows it, for a display that shows one key or section. A key below a masked section is masked too, so a single key never shows what the whole view hides; keys declared not sensitive stay visible. Only the key's path and value are walked, so a call costs that key, not the size of the configuration; the redaction depth limit (300 levels) applies to that path and value, not to nesting elsewhere.

**Parameters:**
- `key` (str, required): Dotted path identifying nested entries.
- `default` (Any, optional): Value returned when `key` does not exist. Default: `None`.

**Returns:** The redacted value, or `default`.

**Example:**
```python
from lib_layered_config import Config

config = Config({"credentials": {"user": "alice"}, "db": {"host": "h"}}, {})
print(config.get_redacted("credentials.user"))  # ***REDACTED***
print(config.get_redacted("db.host"))  # h
print(config.get_redacted("db.port", 0))  # 0
```

##### `Config.to_json(*, indent=None, redact=False)`

Serialize the configuration as JSON.

**Parameters:**
- `indent` (int | None, optional): Indentation level for pretty-printing. `None` produces compact output. Default: `None`.
- `redact` (bool, optional): Replace the values of sensitive keys with `***REDACTED***`; keys declared through `read_config(not_sensitive=...)` stay visible. Default: `False`.

**Returns:** JSON string containing the configuration data.

**Examples:**

**Example 1: Pretty-printed JSON for logs**
```python
from lib_layered_config import read_config

config = read_config(vendor="Acme", app="Demo", slug="demo")

# Pretty-printed JSON with 2-space indentation
pretty_json = config.to_json(indent=2)
print("Current configuration:")
print(pretty_json)

# Output:
# {
#   "service": {
#     "timeout": 30,
#     "endpoint": "https://api.example.com"
#   },
#   "database": {
#     "host": "localhost"
#   }
# }
```
**Explanation:** Use `indent=2` or `indent=4` for human-readable JSON output, perfect for logging or debugging.

**Example 2: Compact JSON for APIs or storage**
```python
# Compact JSON (no whitespace)
compact_json = config.to_json()
print(compact_json)
# Output: {"service":{"timeout":30,"endpoint":"https://api.example.com"},...}

# This is useful when sending config over the network or storing in databases
```
**Explanation:** Compact JSON (no indent) minimizes the payload size, useful for network transmission or storage.

##### `Config.with_overrides(overrides)`

Return a new configuration with *overrides* deep-merged in: nested tables merge key by key, while scalars and lists replace the value they meet.

**Parameters:**
- `overrides` (Mapping[str, Any], required): Nested mapping of keys and values to merge in.

**Returns:** New `Config` instance with overrides applied. Every key the override supplies reports `origin()` as layer `"override"` (`OVERRIDE_LAYER`), path `None`; keys it did not touch keep their original source, and keys it removed have none. The original instance is unchanged.

**Examples:**

**Example 1: Override configuration for specific environment**
```python
from lib_layered_config import read_config

# Load base configuration
config = read_config(vendor="Acme", app="Demo", slug="demo")

# Create a version with production overrides
prod_config = config.with_overrides(
    {
        "service": {"endpoint": "https://prod-api.example.com", "timeout": 60},
        "database": {"host": "prod-db.example.com", "pool_size": 100},
    }
)

print(f"Dev endpoint: {config.get('service.endpoint')}")
print(f"Prod endpoint: {prod_config.get('service.endpoint')}")

# Original config is unchanged
```
**Explanation:** This allows you to create environment-specific configurations from a base configuration without mutating the original.

**Example 2: Testing with feature flags**
```python
# Enable feature flags for testing
test_config = config.with_overrides({"features": {"new_ui": True, "experimental_api": True, "debug_mode": True}})

# Use test_config in your tests
if test_config.get("features.new_ui"):
    print("Running tests with new UI enabled")
```
**Explanation:** Great for testing different configurations or feature flag combinations without modifying files or environment variables.

##### `Config[key]` (item access)

Access top-level keys directly using bracket notation.

**Parameters:**
- `key` (str): Top-level key to retrieve.

**Returns:** Stored value.

**Raises:** `KeyError` when key does not exist.

**Examples:**

**Example 1: Direct access to top-level keys**
```python
from lib_layered_config import read_config

config = read_config(vendor="Acme", app="Demo", slug="demo")

# Access top-level sections directly
service_config = config["service"]
database_config = config["database"]

print(f"Service section: {service_config}")
# Output: {'timeout': 30, 'endpoint': 'https://api.example.com'}

print(f"DB host: {database_config['host']}")
# Output: localhost
```
**Explanation:** Use bracket notation `config[key]` to access top-level configuration sections. This returns the full nested dictionary for that section.

**Example 2: Iterate over configuration sections**
```python
# Iterate over all top-level configuration keys
for section in config:
    print(f"Section: {section}")
    print(f"  Keys: {list(config[section].keys())}")

# Output:
# Section: service
#   Keys: ['timeout', 'endpoint']
# Section: database
#   Keys: ['host', 'port']
```
**Explanation:** Since Config implements the Mapping protocol, you can iterate over it like a dictionary to discover all configured sections.

---

### `read_config`

Load and merge all configuration layers into an immutable `Config` object with provenance metadata.

**Parameters:**
- `vendor` (str, required): Vendor namespace used to compute filesystem paths (e.g., `"Acme"`).
- `app` (str, required): Application name used to compute filesystem paths (e.g., `"ConfigKit"`).
- `slug` (str, required): Configuration slug used for file paths and environment variable prefix (e.g., `"config-kit"`).
- `profile` (str | None, optional): Configuration profile name (e.g., `"test"`, `"production"`). When specified, adds a `profile/<name>/` segment to all configuration paths. Default: `None` (no profile).
- `max_profile_length` (int, optional): Longest `profile` name accepted. A longer one raises `ValidationError` (`"profile exceeds maximum length of N: M characters"`). A value above 255, or `0` or negative, uses the absolute maximum of 255 characters (the longest file name), so length is always checked. Default: `64` (`DEFAULT_MAX_PROFILE_LENGTH`).
- `prefer` (Sequence[str] | None, optional): Deprecated, no effect: each layer reads only `config.toml` and its `config.d/` directory, so there is no second main file for a suffix ranking to choose; put JSON or YAML files in `config.d/`. Passing it emits a `DeprecationWarning`; it will be removed in a future major release. A single `str` is still refused with `TypeError`. Default: `None`.
- `start_dir` (str | Path | None, optional): Starting directory for upward `.env` file search; a directory the search cannot enter is skipped, and so is a `.env` that neither the current user nor root owns (POSIX; logged as the warning `dotenv_skipped_foreign_owner`). Default: `None` (uses current working directory; when the operating system cannot name it - a removed directory, or on macOS one the user cannot enter - no project `.env` is searched).
- `default_file` (str | Path | None, optional): Path to a file injected as the lowest-precedence layer (loaded before app/host/user layers). Default: `None` (no defaults layer).
- `dotenv_path` (str | Path | None, optional): Explicit path to a `.env` file. When set, this file is loaded directly instead of searching upward from `start_dir`. A FIFO (a shell's `<(...)`) or a device is read like a file, up to the same 10 MiB cap; like `cat`, the read waits for a FIFO's writer and for it to close. A path that does not exist loads nothing; a socket raises the unreadable-file error. Default: `None` (use directory search).
- `not_sensitive` (Iterable[str] | None, optional): Dotted key paths you declare as not secret although their name looks like one (e.g. `["performance.max_token_bytes"]`). Redaction leaves them visible, and an unquoted `null`/`none` in the environment or `.env` reads as `None` for them. The returned `Config` carries the declaration. A bare `str` or a non-`str` entry raises `TypeError`; an empty segment (`"a..b"`) raises `ValueError`. Default: `None`.

**Returns:** Immutable `Config` object with merged configuration and provenance tracking.

**Raises:** `LayerLoadError` (a `ConfigError`) when a layer file cannot be decoded or parsed: `"<path> is not
valid <FORMAT>"`, or `"<path> nests deeper than the <FORMAT> parser allows"` when the parser stopped at its
nesting limit (TOML 80 levels, JSON 1024, YAML Python's recursion limit), plus `" (line N, column M)"` when the
parser reports a position; `"<path> is not valid UTF-8
(line N, byte offset M)"` for an undecodable file, or `"<path> is not valid UTF-16|UTF-32 (byte offset M)"` for
a BOM-marked YAML file that does not decode; `"<path> has keys that are not strings (quote them): <parent>:
<key> (<type>)"` for a YAML mapping key such as an unquoted `1:` or `true:`; `"<path> uses !!omap or
!!pairs, whose keys redaction cannot see; write a plain mapping instead: <position>[; <position>...]"`
for a YAML `!!omap` or `!!pairs` value with entries (an empty one loads); `"<path> uses !!set or !!binary,
which have no JSON form; write a list or a base64 string instead: <position> (<type>)[; ...]"` for a YAML
`!!set` or `!!binary` value; `"<path> holds an integer JSON cannot write (it takes -2**63 to 2**64-1); write
it as a string instead: <position> (int, N bits)[; ...]"` for a TOML or YAML integer outside that range (TOML
reads up to 128 bits, a YAML hex literal any width); `"<path> nests <position> N levels deep; JSON output
takes 253, counted from the top-level table: flatten it, or write it as a string"` for a TOML, JSON or YAML
file nesting deeper than any JSON view can write; `"<path>: configuration nesting exceeds the maximum depth
of 100 at <key path>"` for tables nested more than 100 deep, from a file or (as `"environment: ..."`) from an
environment key with more than 100 `__` segments, the key path cut after 80 characters; `"<path> repeats a key, and only its last value would
load: <position>[; <position>...]"` for a JSON or YAML file naming the same key twice in one table (a YAML
position adds `" (line N, column M)"`; a YAML merge key `<<` may appear more than once; TOML refuses such a
file as invalid TOML); `"environment variable <NAME> is not valid UTF-8 (byte
offset N)"` (or `environment variable name <NAME>`, its bad bytes written as `\xNN`) for a variable under the
app's prefix whose value or name is not UTF-8, never naming the value; `"<path> is a directory, not a
configuration file"` when `default_file`, a discovered config path or `dotenv_path` names a directory;
`"<path> is a FIFO, not a configuration file"` (or `character device`, `block device`, `socket`) when
`default_file` names one, a shell's `<(...)` included (a `default_file` that does not exist is no defaults
layer, and a discovered config path that is one of these is passed over); `"<path> has no supported format
(.toml, .json, .yaml, .yml)"` when `default_file` is a file with any other suffix, or none (matched without
regard to case);
`"<path> cannot be read: <reason>"` when a layer's config location, the platform `.env` location, `default_file` or
`dotenv_path` sits behind a permission wall (a directory on its path the user cannot enter, or a file the user
cannot read) or is a name the operating system cannot take (a NUL byte). With `dotenv_path` set, the search
and its platform `.env` location are never probed. The upward
`.env` search is the exception: a directory it cannot enter holds no `.env` for it and is skipped. None of
these quotes the file's content.

**Examples:**

**Example 1: Basic usage - Load configuration with defaults**
```python
from lib_layered_config import read_config

# Simplest usage - just specify your app identity
config = read_config(vendor="Acme", app="MyApp", slug="myapp")

# Access configuration values
timeout = config.get("service.timeout", default=30)
endpoint = config.get("service.endpoint", default="https://api.example.com")

print(f"Service will connect to {endpoint} with {timeout}s timeout")
```
**Explanation:** This is the minimal setup. The library will automatically look for configuration files in standard locations (`/etc/myapp/`, `~/.config/myapp/`, etc.) and merge them with environment variables.

**Example 2: Keeping JSON or YAML settings beside the TOML**
```python
from lib_layered_config import read_config

# ~/.config/myapp/config.toml          main file of the user layer
# ~/.config/myapp/config.d/10-db.json  merged after config.toml
# ~/.config/myapp/config.d/20-log.yaml merged after 10-db.json
config = read_config(vendor="Acme", app="MyApp", slug="myapp")
```
**Explanation:** Each layer's main file is `config.toml`. JSON and YAML files go in its `config.d/` directory, which is merged after `config.toml` in lexicographic file-name order, so a later file overrides an earlier one. YAML needs the `yaml` extra: without it, a `.yaml` file raises `LayerLoadError` naming the file and `lib_layered_config[yaml]` instead of being skipped.

**Example 3: Using a defaults file**
```python
from pathlib import Path
from lib_layered_config import read_config

# Start with application defaults before applying environment-specific overrides
config = read_config(vendor="Acme", app="MyApp", slug="myapp", default_file=Path("./config/defaults.toml"))

# Precedence order now becomes:
# 1. defaults.toml (lowest)
# 2. /etc/myapp/config.toml (app layer)
# 3. /etc/myapp/hosts/hostname.toml (host layer)
# 4. ~/.config/myapp/config.toml (user layer)
# 5. .env files (dotenv layer)
# 6. Environment variables (highest)
```
**Explanation:** Use `default_file` to ship reasonable defaults with your application that can be overridden by system admins (app layer), per-machine configs (host layer), or users.

**Example 4: Project-specific .env search**
```python
from pathlib import Path
from lib_layered_config import read_config

# Specify where to start searching for .env files
project_root = Path(__file__).parent.parent
config = read_config(vendor="Acme", app="MyApp", slug="myapp", start_dir=str(project_root))

# The library will search for .env files starting from project_root
# and moving upward through parent directories
```
**Explanation:** Use `start_dir` to control where `.env` file discovery begins. This ensures your project's `.env` file is found even if your script runs from a subdirectory.

**Example 5: Explicit .env file path**
```python
from pathlib import Path
from lib_layered_config import read_config

# Load a specific .env file instead of searching upward
config = read_config(vendor="Acme", app="MyApp", slug="myapp", dotenv_path=Path("/opt/myapp/secrets/.env.production"))

# The library loads /opt/myapp/secrets/.env.production directly
# without searching parent directories for .env files
```
**Explanation:** Use `dotenv_path` when you know the exact location of the `.env` file. This is common in containers and CI/CD where secrets are mounted at a known path.

**Example 6: Complete setup with all parameters**
```python
from pathlib import Path
from lib_layered_config import read_config

# Production-ready configuration loading
config = read_config(
    vendor="Acme",
    app="MyApp",
    slug="myapp",
    start_dir=Path.cwd(),  # Search .env from current directory
    default_file=Path(__file__).parent / "defaults.toml",  # Ship defaults
)

# Use the configuration
db_host = config.get("database.host", default="localhost")
db_port = config.get("database.port", default=5432)
db_name = config.get("database.name", default="myapp")

print(f"Connecting to PostgreSQL at {db_host}:{db_port}/{db_name}")

# Check where each value came from
for key in ["database.host", "database.port", "database.name"]:
    origin = config.origin(key)
    if origin:
        print(f"  {key}: from {origin['layer']} layer")
```
**Explanation:** This complete example shows production-ready configuration loading with defaults and provenance tracking for debugging.

---

### `read_config_json`

Load configuration and return it as JSON with provenance metadata.

**Parameters:**
- `vendor` (str, required): Vendor namespace.
- `app` (str, required): Application name.
- `slug` (str, required): Configuration slug.
- `profile` (str | None, optional): Configuration profile name. Adds `profile/<name>/` to paths. Default: `None`.
- `max_profile_length` (int, optional): Longest `profile` name accepted. A longer one raises `ValidationError` (`"profile exceeds maximum length of N: M characters"`). A value above 255, or `0` or negative, uses the absolute maximum of 255 characters (the longest file name), so length is always checked. Default: `64` (`DEFAULT_MAX_PROFILE_LENGTH`).
- `prefer` (Sequence[str] | None, optional): Deprecated, no effect; see `read_config`. Passing it emits a `DeprecationWarning`; a single `str` is still refused with `TypeError`. Default: `None`.
- `start_dir` (str | Path | None, optional): Starting directory for `.env` search. Default: `None`.
- `default_file` (str | Path | None, optional): Path to lowest-precedence defaults file. Default: `None`.
- `dotenv_path` (str | Path | None, optional): Explicit `.env` file path (skips upward search). Default: `None`.
- `indent` (int | None, optional): JSON indentation level. `None` for compact output. Default: `None`.
- `redact` (bool, optional): Replace the values of sensitive keys (`password`, `token`, `secret`, `*_key`, ...) with `***REDACTED***` in the config data. Default: `False`.
- `not_sensitive` (Iterable[str] | None, optional): Dotted key paths you declare as not secret although their name looks like one (e.g. `["performance.max_token_bytes"]`). Redaction leaves them visible, and an unquoted `null`/`none` in the environment or `.env` reads as `None` for them. Declared keys stay visible when `redact` is set. A bare `str` or a non-`str` entry raises `TypeError`; an empty segment (`"a..b"`) raises `ValueError`. Default: `None`.

**Returns:** JSON string containing `{"config": {...}, "provenance": {...}}`.

A path whose name holds a byte that is not UTF-8 (possible on Linux, where a file name is bytes) is
written with that byte as the four characters `\xNN`: a config under `/opt/x<0xFF>y/` shows
`"/opt/x\\xffy/..."` in the JSON text, which reads back as `x\xffy`. The same holds for every JSON
output, `Config.to_json` and the CLI's `--json` included.

**Examples:**

**Example 1: API endpoint - Return configuration as JSON**
```python
from lib_layered_config import read_config_json
from flask import Flask, jsonify

app = Flask(__name__)


@app.route("/api/config")
def get_config():
    # Load and return configuration as JSON with provenance
    json_payload = read_config_json(
        vendor="Acme",
        app="MyApp",
        slug="myapp",
        indent=2,  # Pretty-printed for readability
    )
    return json_payload, 200, {"Content-Type": "application/json"}


# The response includes both config values and their sources
```
**Explanation:** Perfect for exposing configuration through APIs. The JSON includes provenance data so clients can see where each value came from.

**Example 2: Configuration audit tool**
```python
from lib_layered_config import read_config_json
import json

# Load configuration with provenance
payload = read_config_json(vendor="Acme", app="MyApp", slug="myapp", indent=2)

data = json.loads(payload)

# Audit where sensitive values come from
print("Configuration Audit Report")
print("=" * 50)

for key, info in data["provenance"].items():
    value = data["config"]
    # Navigate to the value using the key
    for part in key.split("."):
        value = value.get(part, {})

    print(f"\n{key}: {value}")
    print(f"  Source Layer: {info['layer']}")
    print(f"  File Path: {info['path'] or '(environment variable)'}")
```
**Explanation:** Use this for creating audit reports that show exactly where each configuration value originated from.

**Example 3: Compact JSON for logging**
```python
from lib_layered_config import read_config_json
import logging

# Get compact JSON (no indentation) for structured logging
compact_json = read_config_json(
    vendor="Acme",
    app="MyApp",
    slug="myapp",
    indent=None,  # Compact output
)

# Log the configuration snapshot
logging.info(f"Application started with config: {compact_json}")
```
**Explanation:** Compact JSON is ideal for log aggregation systems where you want to log the entire configuration as a single line.

---

### `read_config_raw`

Return raw data and provenance mappings for advanced tooling.

**Parameters:**
- `vendor` (str, required): Vendor namespace.
- `app` (str, required): Application name.
- `slug` (str, required): Configuration slug.
- `profile` (str | None, optional): Configuration profile name. Adds `profile/<name>/` to paths. Default: `None`.
- `max_profile_length` (int, optional): Longest `profile` name accepted. A longer one raises `ValidationError` (`"profile exceeds maximum length of N: M characters"`). A value above 255, or `0` or negative, uses the absolute maximum of 255 characters (the longest file name), so length is always checked. Default: `64` (`DEFAULT_MAX_PROFILE_LENGTH`).
- `prefer` (Sequence[str] | None, optional): Deprecated, no effect; see `read_config`. Passing it emits a `DeprecationWarning`; a single `str` is still refused with `TypeError`. Default: `None`.
- `start_dir` (str | Path | None, optional): Starting directory for `.env` search. Default: `None`.
- `default_file` (str | Path | None, optional): Path to lowest-precedence defaults file. Default: `None`.
- `dotenv_path` (str | Path | None, optional): Explicit `.env` file path (skips upward search). Default: `None`.
- `not_sensitive` (Iterable[str] | None, optional): Dotted key paths you declare as not secret although their name looks like one (e.g. `["performance.max_token_bytes"]`). An unquoted `null`/`none` in the environment or `.env` reads as `None` for them. The returned plain dicts do not carry the declaration: pass it again as `redact_mapping(data, not_sensitive=...)` when you redact them. A bare `str` or a non-`str` entry raises `TypeError`; an empty segment (`"a..b"`) raises `ValueError`. Default: `None`.

**Returns:** `MergeResult` with two mutable dictionaries: `.data`, the merged nested configuration, and
`.provenance`, a flat mapping from each dotted key to `{"layer": ..., "path": ..., "key": ...}`.

**Examples:**

**Example 1: Template rendering with configuration**
```python
from lib_layered_config import read_config_raw
from jinja2 import Template

# Load configuration as raw dictionaries
data = read_config_raw(vendor="Acme", app="MyApp", slug="myapp").data

# Use in template rendering
template = Template("""
Database Configuration:
  Host: {{ database.host }}
  Port: {{ database.port }}
  Database: {{ database.name }}

Service Configuration:
  Timeout: {{ service.timeout }}s
  Endpoint: {{ service.endpoint }}
""")

output = template.render(**data)
print(output)
```
**Explanation:** Raw dictionaries are perfect for template rendering where you need mutable data structures.

**Example 2: Configuration validation**
```python
from lib_layered_config import read_config_raw

# Load configuration
data = read_config_raw(vendor="Acme", app="MyApp", slug="myapp").data

# Validate required fields
required_keys = [
    ("database.host", str),
    ("database.port", int),
    ("service.timeout", int),
]

errors = []
for key, expected_type in required_keys:
    # Navigate the nested dictionary
    value = data
    for part in key.split("."):
        value = value.get(part) if isinstance(value, dict) else None
        if value is None:
            break

    if value is None:
        errors.append(f"Missing required key: {key}")
    elif not isinstance(value, expected_type):
        errors.append(f"{key} must be {expected_type.__name__}, got {type(value).__name__}")

if errors:
    print("Configuration validation errors:")
    for error in errors:
        print(f"  - {error}")
else:
    print("Configuration is valid!")
```
**Explanation:** Use `read_config_raw` for advanced validation or transformation where you need full control over the data structures.

**Example 3: Merge with runtime overrides**
```python
from lib_layered_config import read_config_raw

# Load base configuration; result.provenance says where each value came from
result = read_config_raw(vendor="Acme", app="MyApp", slug="myapp")
data = result.data

# Apply runtime overrides (e.g., from command-line arguments)
if args.db_host:
    data["database"]["host"] = args.db_host
if args.debug:
    data["logging"]["level"] = "DEBUG"

# Now use the modified configuration
print(f"Final configuration: {data}")
```
**Explanation:** Raw dictionaries can be mutated, making them useful when you need to apply runtime overrides from command-line arguments or other sources.

---

### Redaction helpers

`is_sensitive(name)` decides by key name alone, so a size such as `max_token_bytes` is masked like a token.
`NotSensitiveKeys` lets an application declare such keys; the helpers below are importable from `lib_layered_config`.

##### `NotSensitiveKeys.of(declared)`

Build the declaration from dotted paths (matched case-insensitively; an item in a list is addressed by the
list's own path, with no index). Pass `None` for none (returns `NotSensitiveKeys.NONE`) or an existing instance
(returned as is). It covers its own path only: keys below it are still checked, and a masked section stays masked
unless the section itself is declared. `covers(path)` returns whether a sequence of segments was declared;
iterating an instance yields the declared dotted paths, sorted.

**Raises:** `TypeError` for a single `str` or a non-`str` entry, and `ValueError` for an empty segment. `covers`
refuses a `str` path with `TypeError`, as does `NotSensitiveKeys(paths)` built directly from anything `of` would not produce
(`ValueError` for an empty or non-lowercase segment).

##### `is_sensitive_at(path, *, not_sensitive=NotSensitiveKeys.NONE)`

Return whether the key at `path` is masked: its own name looks secret and nothing declared it.

**Parameters:**
- `path` (Sequence[str], required): The key's segments from the root, its own name last. A dotted `str` raises
  `TypeError`; write `tuple("db.password".split("."))`.
- `not_sensitive` (NotSensitiveKeys, optional): Declared paths. Default: `NotSensitiveKeys.NONE`.

**Returns:** `bool`.

##### `redact_mapping(data, *, not_sensitive=None)`

Return a deep copy of `data` with sensitive values replaced by `REDACTED_PLACEHOLDER` (`"***REDACTED***"`).

**Parameters:**
- `data` (dict[str, Any], required): Configuration mapping to redact.
- `not_sensitive` (Iterable[str] | None, optional): Dotted paths declared not sensitive; same validation as `NotSensitiveKeys.of`. Default: `None`.

**Example:**
```python
from lib_layered_config import redact_mapping

print(redact_mapping({"max_token_bytes": 4096, "password": "x"}, not_sensitive=["max_token_bytes"]))
# {'max_token_bytes': 4096, 'password': '***REDACTED***'}
```

### `default_env_prefix`

Compute the canonical environment variable prefix for a slug.

**Parameters:**
- `slug` (str, required): Configuration slug (e.g., `"config-kit"`).

**Returns:** Uppercase environment prefix with dashes converted to underscores, ending in the `___` separator
(`"config-kit"` gives `"CONFIG_KIT___"`, `"myapp"` gives `"MYAPP___"`).

**Raises:** `ValidationError` for a `slug` that `read_config`, `deploy_config` and `generate_examples` refuse
too: empty (`"slug cannot be empty"`), holding a path separator or whitespace (`"slug contains invalid
characters: ../x"`), starting with a dot (`"slug cannot start with a dot: .x"`), or non-ASCII.

**Examples:**

**Example 1: Generate documentation for environment variables**
```python
from lib_layered_config import default_env_prefix

# Calculate the prefix for your application
slug = "myapp"
prefix = default_env_prefix(slug)

print(f"Environment Variables for {slug}:")
print(f"=" * 50)
print(f"\n{prefix}<SECTION>__<KEY>=<value>\n")
print("Examples:")
print(f"  {prefix}DATABASE__HOST=localhost")
print(f"  {prefix}DATABASE__PORT=5432")
print(f"  {prefix}SERVICE__TIMEOUT=30")
print(f"\nNote: Use double underscores (__) for nested keys")
```
**Explanation:** Use this to generate documentation showing users how to set environment variables for your application.

**Example 2: Programmatically set environment variables**
```python
import os
from lib_layered_config import default_env_prefix

# Calculate prefix
prefix = default_env_prefix("myapp")

# Set environment variables programmatically (useful in tests)
os.environ[f"{prefix}DATABASE__HOST"] = "test-db.example.com"
os.environ[f"{prefix}DATABASE__PORT"] = "5432"
os.environ[f"{prefix}SERVICE__TIMEOUT"] = "5"

# Now when you load configuration, these will be picked up
from lib_layered_config import read_config

config = read_config(vendor="Acme", app="MyApp", slug="myapp")

print(f"DB Host: {config.get('database.host')}")  # test-db.example.com
```
**Explanation:** Programmatically generate environment variable names for testing or dynamic configuration.

**Example 3: Validate environment variable names**
```python
import os
from lib_layered_config import default_env_prefix

slug = "myapp"
expected_prefix = default_env_prefix(slug)

# Check if environment variables are correctly namespaced
print(f"Checking environment variables for prefix: {expected_prefix}")  # MYAPP___

mismatched = []
for key in os.environ:
    if "DATABASE" in key or "SERVICE" in key:
        if not key.startswith(expected_prefix):
            mismatched.append(key)

if mismatched:
    print("\nWarning: Found environment variables that won't be loaded:")
    for key in mismatched:
        correct_name = f"{expected_prefix}{key}"
        print(f"  {key} should be {correct_name}")
else:
    print("All environment variables are correctly prefixed!")
```
**Explanation:** Validate that your environment variables are correctly prefixed so they'll be picked up by the configuration loader.

---

### `deploy_config`

Copy a source configuration file into one or more layer directories with conflict handling.

**Parameters:**
- `source` (str | Path, required): Path to the configuration file to copy. It must be a `.toml` file (any case), since every destination is read only as TOML; any other suffix raises `LayerLoadError` before anything is written.
- `vendor` (str, required): Vendor namespace.
- `app` (str, required): Application name.
- `targets` (Sequence[str], required): Layer targets to deploy to. Valid values: `"app"`, `"host"`, `"user"`. A single str (`targets="user"`) raises `ValidationError`: write `["user"]`.
- `slug` (str | None, optional): Configuration slug. Default: `None` (uses `app` as slug).
- `profile` (str | None, optional): Configuration profile name. Adds `profile/<name>/` to deployment paths. Default: `None`.
- `max_profile_length` (int, optional): Longest `profile` name accepted. A longer one raises `ValidationError` (`"profile exceeds maximum length of N: M characters"`). A value above 255, or `0` or negative, uses the absolute maximum of 255 characters (the longest file name), so length is always checked. Default: `64` (`DEFAULT_MAX_PROFILE_LENGTH`).
- `platform` (str | None, optional): Override the auto-detected platform. Takes the CLI's `--platform` names: `"linux"`/`"posix"`, `"darwin"`/`"macos"`/`"mac"`, `"win32"`/`"windows"`/`"win"`/`"wine"`, in any case. Any other name raises `ValidationError` listing them. A Windows layout off Windows needs an absolute `LIB_LAYERED_CONFIG_PROGRAMDATA` (or `ProgramData`) for the `app` and `host` targets: the built-in `C:\ProgramData` is relative there and raises `ValidationError` before anything is written, as does a relative value in any Windows root variable on every platform. Default: `None` (auto-detects from current platform).
- `force` (bool, optional): When True and file exists with different content, backup to `.bak` and overwrite. Default: `False`.
- `batch` (bool, optional): Non-interactive mode - keeps existing files and writes new config as `.ucf` for review (CI/CD). Default: `False`. Together with `force=True` it raises `ValidationError` before anything is written: one overwrites an existing file, the other keeps it.
- `conflict_resolver` (Callable[[Path], DeployAction] | None, optional): Called with the destination of each file whose content differs; returns `DeployAction.OVERWRITTEN` or `DeployAction.KEPT`. Any other answer raises `ValidationError` naming the two, and nothing is written for that destination. `force` and `batch` decide first: with either set, the resolver is never called. Default: `None` (with neither `force` nor `batch`, a differing file is left unchanged and reported as `CONFLICT`).
- `set_permissions` (bool | None, optional): `True` sets modes, `False` leaves them to the umask, `None` follows the configured `[lib_layered_config.default_permissions].enabled` (true when unset). An explicit `dir_mode` or `file_mode` means modes are set; one given with `False` is refused. Skipped on Windows. Default: `None`.
- `dir_mode` (int | None, optional): Directory mode for every target, overriding the configured and built-in ones. Default: `None`.
- `file_mode` (int | None, optional): File mode for every target, overriding the configured and built-in ones. Default: `None`.
- `permissions` (DeployPermissions | None, optional): A complete settings object to use instead of reading the configuration, for a caller that builds one on purpose. One built with `deploy_permissions_from_config(read_config(...))` includes `.env`, the deployed files and a user file's `app_*`/`host_*` modes, which the deploy's own read leaves out; use `permission_overrides` for runtime overrides. Default: `None`.
- `permission_overrides` (Mapping[str, object] | None, optional): Runtime values for keys of `[lib_layered_config.default_permissions]`, by setting name (`{"user_file": "0o640"}`), laid over the deploy's own read and validated like configured values; a refusal names `(source: override)`. Validated on every call. `{"enabled": False}` with `set_permissions=None` and no mode turns permission setting off without reading the configuration. Cannot be combined with `permissions`. Default: `None`.

**Returns:** `list[DeployResult]` - Each result contains:
- `destination`: Path to the target file
- `action`: `DeployAction` enum: `CREATED`, `OVERWRITTEN`, `KEPT`, `SKIPPED` (byte-identical, nothing written) or `CONFLICT` (content differs and no `force`, `batch` or `conflict_resolver` decided; the file is left unchanged and nothing else is written for it)
- `backup_path`: Path to `.bak` file (if action was `OVERWRITTEN`)
- `ucf_path`: Path to `.ucf` file (if action was `KEPT`)
- `dot_d_results`: List of `DeployResult` for companion `.d` directory files (if any)

**`.d` Directory Support:** If the source file has a companion `.d` directory (e.g., `defaults.toml` → `defaults.d/`), those files are also deployed to the corresponding `.d` directory at each destination. User-added files in the destination `.d` directory are preserved.

**Smart Skipping:** If the source content is byte-identical to the existing destination file, the file is skipped without creating backups (regardless of `force` or `batch` flags). This applies to both base files and `.d` directory files.

**Permissions:** Each side (directory, file) resolves as `dir_mode`/`file_mode`, else the configured
`[lib_layered_config.default_permissions]` setting for that layer, else the built-in layer mode (app/host
755/644, user 700/600); an unsafe mode is refused before anything is written. A user-layer file decides only
`user_*` and `enabled`: its `app_*`/`host_*` values are ignored (logged, never refused). See
[cli-reference.md#-file-permissions](cli-reference.md#-file-permissions) for the full resolution order and the
refusal rule.

**Raises:** `FileNotFoundError` (the source is not a regular file; the message says what is there:
`"Configuration source not found: <path>"` for a missing path or a dangling link,
`"Configuration source is a directory, not a file: <path>"`, or `"Configuration source is not a regular file:
<path>"` for a FIFO, device or socket), `LayerLoadError`
(the source is not a `.toml` file, or does not parse as TOML: `"<path> is not valid TOML (line N, column M)"`;
nothing is written), `PermissionError` (the source, a file in its `.d`
directory, or a destination cannot be read or sits behind a permission wall; the same on every Python, and for
the source and its `.d` files in every mode, before anything is written), `ValidationError` (an invalid `vendor`, `app`,
`slug` or `profile`, an unknown target, or `force` with `batch`, before anything is written; a `conflict_resolver`
answer other than `OVERWRITTEN` or `KEPT`, when that destination is reached, so the files deployed before it stay
written), `DeployModeError` (a refused `dir_mode` /
`file_mode`, or one given with `set_permissions=False`), `DeployPermissionsError` (the permission settings are
not readable, the section is invalid, a refused `permission_overrides` value, or `permission_overrides`
combined with `permissions`; nothing is written), `DeployDestinationError` (a destination or one of its `.d`
copies is a symbolic link, dangling or not, or not a regular file - a directory, FIFO, device or socket;
deploy neither writes through a link nor replaces it, and nothing is written).

**Partial failure:** targets are deployed in the order given, each one's `.d` files after its main file.
An error raised partway is the same exception, re-raised, and carries the results already written:
`deployed_before_failure(error)` returns them as `DeployResult` items in write order (a `.d` file sits in
its main file's `dot_d_results`), and `[]` for an error that carries none.

```python
from lib_layered_config import deploy_config, deployed_before_failure

try:
    deploy_config("./config.toml", vendor="Acme", app="Demo", targets=["user", "app"], force=True)
except PermissionError as error:
    for result in deployed_before_failure(error):
        print("already written:", result.destination, result.action)
    raise
```

**Examples:**

**Example 1: Deploy system-wide defaults**
```python
from lib_layered_config import DeployAction, deploy_config

# Deploy app-wide defaults to the system directory
results = deploy_config(
    source="./config/defaults.toml",
    vendor="Acme",
    app="MyApp",
    targets=["app"],  # Deploy to system-wide location
    slug="myapp",
)

# On Linux, this copies to: /etc/xdg/myapp/config.toml (+ config.d/ if exists)
# On macOS: /Library/Application Support/Acme/MyApp/config.toml (+ config.d/)
# On Windows: C:\ProgramData\Acme\MyApp\config.toml (+ config.d\)

for result in results:
    print(f"{result.action.value}: {result.destination}")
    for dot_d_result in result.dot_d_results:
        print(f"  .d: {dot_d_result.action.value}: {dot_d_result.destination}")
```
**Explanation:** Use the `"app"` target to deploy system-wide defaults that all users share. If a `defaults.d/` directory exists alongside `defaults.toml`, its contents are also deployed. This is typically done during installation.

**Example 2: Deploy with batch mode (CI/CD safe)**
```python
from lib_layered_config import DeployAction, deploy_config

# Deploy in CI - keeps existing, writes new config as .ucf for review
results = deploy_config(
    source="./my-config.toml",
    vendor="Acme",
    app="MyApp",
    targets=["user"],
    slug="myapp",
    batch=True,  # Non-interactive, creates .ucf for review
)

for result in results:
    if result.action == DeployAction.CREATED:
        print(f"Created: {result.destination}")
    elif result.action == DeployAction.KEPT:
        print(f"Kept: {result.destination}")
        print(f"  Review new config at: {result.ucf_path}")
    elif result.action == DeployAction.SKIPPED:
        print(f"Skipped (identical content): {result.destination}")
```
**Explanation:** Use `batch=True` for CI/CD pipelines. When content differs, the existing file is kept and new config is written to `.ucf` for review.

**Example 3: Deploy with force and check backups**
```python
from lib_layered_config import DeployAction, deploy_config

# Force deploy - creates backups before overwriting
results = deploy_config(
    source="./new-config.toml",
    vendor="Acme",
    app="MyApp",
    targets=["user"],
    slug="myapp",
    force=True,  # Backup to .bak, then overwrite
)

for result in results:
    if result.action == DeployAction.OVERWRITTEN:
        print(f"Overwrote: {result.destination}")
        print(f"Backup at: {result.backup_path}")
    elif result.action == DeployAction.SKIPPED:
        print(f"Skipped (content identical): {result.destination}")
    elif result.action == DeployAction.CREATED:
        print(f"Created: {result.destination}")
```
**Explanation:** With `force=True`, existing files with different content are backed up to `.bak` before overwriting. If content is identical, files are smart-skipped without backups.

**Example 4: Deploy to multiple layers at once**
```python
from lib_layered_config import DeployAction, deploy_config

# Deploy the same config to multiple layers
results = deploy_config(
    source="./base-config.toml",
    vendor="Acme",
    app="MyApp",
    targets=["app", "user"],  # Deploy to both system and user directories
    slug="myapp",
    force=True,
)

print(f"Deployed to {len(results)} locations:")
for result in results:
    status = "✓" if result.action in (DeployAction.CREATED, DeployAction.OVERWRITTEN) else "○"
    print(f"  {status} {result.destination} ({result.action.value})")
```
**Explanation:** Deploy to multiple layers simultaneously. Useful for setting up consistent defaults across system and user levels. The `force=True` parameter allows overwriting existing files.

**Example 5: Cross-platform deployment script**
```python
from lib_layered_config import DeployAction, deploy_config
import sys

# Deployment script that works across platforms
source_config = "./dist/config.toml"

print(f"Deploying configuration on {sys.platform}...")

try:
    results = deploy_config(
        source=source_config,
        vendor="Acme",
        app="MyApp",
        targets=["app"],
        slug="myapp",
        batch=True,  # Non-interactive for scripts
    )

    for result in results:
        if result.action == DeployAction.CREATED:
            print(f"✓ Created: {result.destination}")
        elif result.action == DeployAction.KEPT:
            print(f"○ Kept existing, review new config at: {result.ucf_path}")
        elif result.action == DeployAction.SKIPPED:
            print(f"○ Skipped (identical content): {result.destination}")

except FileNotFoundError:
    print(f"Error: Source file '{source_config}' not found")
    sys.exit(1)
```
**Explanation:** The function automatically detects the platform and deploys to the appropriate directories. Use `batch=True` for non-interactive scripts; new configs are written to `.ucf` files for review.

**Example 6: Deploy to a specific profile (environment-specific)**
```python
from lib_layered_config import DeployAction, deploy_config

# Deploy production configuration to the production profile
results = deploy_config(
    source="./configs/production.toml",
    vendor="Acme",
    app="MyApp",
    targets=["app"],
    slug="myapp",
    profile="production",  # Deploy to profile-specific subdirectory
)

# On Linux: /etc/xdg/myapp/profile/production/config.toml (+ config.d/ if exists)
# On macOS: /Library/Application Support/Acme/MyApp/profile/production/config.toml
# On Windows: C:\ProgramData\Acme\MyApp\profile\production\config.toml

for result in results:
    print(f"Production config: {result.action.value} -> {result.destination}")

# Deploy test configuration to a separate profile
test_results = deploy_config(
    source="./configs/test.toml",
    vendor="Acme",
    app="MyApp",
    targets=["app", "user"],
    slug="myapp",
    profile="test",  # Completely isolated from production
)

# On Linux: /etc/xdg/myapp/profile/test/config.toml (+ config.d/)
#           ~/.config/myapp/profile/test/config.toml (+ config.d/)
```
**Explanation:** Use the `profile` parameter to deploy environment-specific configurations to isolated subdirectories. If the source has a companion `.d` directory, it's also deployed. This keeps production, staging, and test configurations completely separate, preventing accidental cross-environment configuration leaks.

**Example 7: Deploy multiple profiles in a CI/CD pipeline**
```python
from lib_layered_config import DeployAction, deploy_config
from pathlib import Path

# Deploy configurations for all environments
environments = ["development", "staging", "production"]

for env in environments:
    config_file = Path(f"./environments/{env}.toml")
    if not config_file.exists():
        print(f"Skipping {env}: config file not found")
        continue

    results = deploy_config(
        source=config_file,
        vendor="Acme",
        app="MyApp",
        targets=["app"],
        slug="myapp",
        profile=env,
        force=True,  # Update existing configs (creates backups)
    )

    for result in results:
        if result.action == DeployAction.CREATED:
            print(f"✓ {env}: created {result.destination}")
        elif result.action == DeployAction.OVERWRITTEN:
            print(f"✓ {env}: updated {result.destination} (backup: {result.backup_path})")
        elif result.action == DeployAction.SKIPPED:
            print(f"○ {env}: unchanged {result.destination}")
```
**Explanation:** Profiles are ideal for CI/CD pipelines where you need to deploy different configurations for each environment. Each profile is isolated, so you can safely deploy all environments to the same system. With `force=True`, backups are created before overwriting.

**Example 8: Deploy with custom permissions**
```python
from lib_layered_config import DeployAction, deploy_config

# Deploy with configured or built-in layer defaults (the default: set_permissions=None)
# - App layer: 755 dirs, 644 files (world-readable), unless configured otherwise
# - User layer: 700 dirs, 600 files (private), unless configured otherwise
results = deploy_config(
    source="./config.toml",
    vendor="Acme",
    app="MyApp",
    targets=["user"],
    slug="myapp",
)

# Deploy with custom permissions (e.g., group-readable) - explicit modes win over configured ones
results = deploy_config(
    source="./config.toml",
    vendor="Acme",
    app="MyApp",
    targets=["app"],
    slug="myapp",
    dir_mode=0o750,  # rwxr-x--- (owner + group read/execute)
    file_mode=0o640,  # rw-r----- (owner + group read)
)

# Deploy without setting permissions (use umask defaults)
results = deploy_config(
    source="./config.toml",
    vendor="Acme",
    app="MyApp",
    targets=["user"],
    slug="myapp",
    set_permissions=False,  # Skip chmod, use system umask
)

# Runtime override of one setting (e.g. from an application's own --set option), laid over
# whatever deploy_config would otherwise read from the configured section
results = deploy_config(
    source="./config.toml",
    vendor="Acme",
    app="MyApp",
    targets=["user"],
    slug="myapp",
    permission_overrides={"user_file": "0o640"},
)

for result in results:
    if result.action == DeployAction.CREATED:
        print(f"Created: {result.destination}")
        # Check actual permissions (Linux/macOS)
        import stat

        mode = result.destination.stat().st_mode
        print(f"  Mode: {stat.filemode(mode)}")
```
**Explanation:** Leave `set_permissions` at its default (`None`) for configured-or-built-in, layer-aware
permissions. Use `dir_mode` and `file_mode` to override them for special requirements (e.g., group-readable
configs); an unsafe mode is refused. Use `set_permissions=False` when permissions should be inherited from
umask. Use `permission_overrides` for a runtime value (such as a `--set` option) laid over deploy's own read,
rather than building a `permissions=` object from `read_config(...)`, which includes `.env`, the deployed
files and a user file's `app_*`/`host_*` modes. On Windows, permission setting is automatically skipped.

---

### `deploy_config_paths` and `read_deploy_config`

```python
def deploy_config_paths(
    source: str | Path,
    *,
    vendor: str,
    app: str,
    targets: Sequence[str],
    slug: str | None = None,
    profile: str | None = None,
    platform: str | None = None,
    max_profile_length: int = DEFAULT_MAX_PROFILE_LENGTH,
) -> frozenset[Path]

def read_deploy_config(
    source: str | Path,
    *,
    vendor: str,
    app: str,
    skip: Iterable[str | Path],
    slug: str | None = None,
    profile: str | None = None,
    platform: str | None = None,
    max_profile_length: int = DEFAULT_MAX_PROFILE_LENGTH,
) -> Config
```

What `deploy_config` sees, for a caller that must see the same: an application that reports which
permission modes a deploy will use, or one that must read its configuration while a file the deploy is
about to replace no longer parses.

- `deploy_config_paths` returns every file a `deploy_config` of `source` to `targets` writes, resolved,
  whether or not it exists yet: each target's configuration file and, in its companion `.d` directory, a
  copy of every file in the source's own `.d` directory. It is computed by the code the deploy runs, so
  it cannot drift from what the deploy reports writing.
- `read_deploy_config` returns the configuration the deploy reads for its modes: `source` as the defaults
  layer, then the app, host and user files not in `skip`, then the environment. It reads no `.env` file,
  and a user-layer file keeps only its `user_*` and `enabled` permission settings. Each `skip` entry is
  resolved before it is compared, so any spelling of a path matches; a single `str` or `Path` given as
  `skip` raises `TypeError`.

**Raises:** `FileNotFoundError` for a source that does not exist or is not a regular file (worded as for `deploy_config`), `ValueError` for an invalid profile, `ValidationError`
for an unknown target (`deploy_config_paths`), and `LayerLoadError` for a file not left out that cannot be
read or parsed (`read_deploy_config`).

```python
from lib_layered_config import deploy_config_paths, deploy_permissions_from_config, read_deploy_config

identity = {"vendor": "Acme", "app": "MyApp", "slug": "myapp"}
written = deploy_config_paths("./config.toml", targets=["user"], **identity)

# The deploy's own read: every file it writes is left out, so none decides its own replacement
used = read_deploy_config("./config.toml", skip=written, **identity)
settings = deploy_permissions_from_config(used)  # the modes deploy_config would apply

# Leave out fewer files: here only the main file, as an application might after finding it no longer
# parses and before a forced deploy replaces it; the rest of what the deploy writes is still read
broken = {path for path in written if path.name == "config.toml"}
repaired = read_deploy_config("./config.toml", skip=broken, **identity)
```

---

### `generate_examples`

Generate example configuration trees for documentation or onboarding.

**Parameters:**
- `destination` (str | Path, required): Directory that will receive the example tree.
- `slug` (str, required): Configuration slug used in generated files.
- `vendor` (str, required): Vendor namespace.
- `app` (str, required): Application name.
- `force` (bool, optional): Overwrite existing example files. Default: `False`.
- `platform` (str | None, optional): Override platform layout. `"posix"`, `"linux"`, `"darwin"`, `"macos"` and `"mac"` write the POSIX layout (`xdg/`, `home/`); `"windows"`, `"win"`, `"win32"` and `"wine"` write the Windows layout (`ProgramData/`, `AppData/`); case and surrounding spaces are ignored. Any other name raises `ValidationError` listing them. Default: `None` (uses current platform).

**Returns:** List of `Path` objects for files created. Existing files are kept unless `force=True`
and are not in the list; `generate_examples_report(...)` in `lib_layered_config.generate` takes the same
arguments and returns an `ExamplesReport` with `.created` and `.kept`.

**Raises:** `ValidationError` before anything is written when `slug`, `vendor` or `app` is not a
safe path segment (`../x`, an absolute path, a control character, empty), checked like
`read_config` checks them, or when `platform` is not one of the names above. `vendor` and `app`
may contain spaces; `slug` may not. `GenerateDestinationError`, also before anything is written and one
line per path: with `force=True`, an example path that is a symbolic link (dangling or not) or not a
regular file (a directory, FIFO, device or socket); without it, an example path that is a link
resolving to nothing, which a create would write through. Without `force` anything else already at an
example path is kept. A written example replaces the old one through a temporary file, except that a
file with other hard links, another owner or its own extended attributes is rewritten in place, as
`deploy_config` does with permission setting off.

**Examples:**

**Example 1: Generate documentation examples**
```python
from lib_layered_config import generate_examples
from pathlib import Path

# Generate example configuration files for documentation
docs_dir = Path("./docs/examples")
created_files = generate_examples(
    destination=docs_dir,
    slug="myapp",
    vendor="Acme",
    app="MyApp",
    platform="posix",  # Generate Linux/macOS examples
)

print(f"Generated {len(created_files)} example files:")
for file_path in created_files:
    relative = file_path.relative_to(docs_dir)
    print(f"  - {relative}")

# Output shows:
#   - xdg/myapp/config.toml (app defaults, for /etc/xdg/myapp/)
#   - xdg/myapp/hosts/your-hostname.toml (host overrides)
#   - home/myapp/config.toml (user preferences, for ~/.config/myapp/)
#   - home/myapp/config.d/10-override.toml (split overrides)
#   - .env.example (environment variables)
```
**Explanation:** Perfect for generating example configurations to include in your documentation or repository. Users can copy these examples to get started quickly.

**Example 2: Generate Windows examples for cross-platform project**
```python
from lib_layered_config import generate_examples
from pathlib import Path

# Generate Windows-specific examples even on Linux/macOS
windows_examples = Path("./docs/examples-windows")
created_files = generate_examples(
    destination=windows_examples,
    slug="myapp",
    vendor="Acme",
    app="MyApp",
    platform="windows",  # Force Windows layout
)

print("Windows configuration examples:")
for file_path in created_files:
    print(f"  {file_path.relative_to(windows_examples)}")

# Output shows Windows paths:
#   - ProgramData/Acme/MyApp/config.toml
#   - ProgramData/Acme/MyApp/hosts/your-hostname.toml
#   - AppData/Roaming/Acme/MyApp/config.toml
#   - AppData/Roaming/Acme/MyApp/config.d/10-override.toml
#   - .env.example
```
**Explanation:** Generate platform-specific examples regardless of your current OS. Great for maintaining documentation for all supported platforms.

**Example 3: Onboarding script - Generate and customize examples**
```python
from lib_layered_config import generate_examples
from pathlib import Path


def onboard_user(username: str):
    """Generate personalized configuration examples for a new user."""

    # Create user-specific examples directory
    user_examples = Path(f"/tmp/{username}-config-examples")
    user_examples.mkdir(exist_ok=True)

    # Generate example files
    created = generate_examples(destination=user_examples, slug="myapp", vendor="Acme", app="MyApp")

    print(f"Generated {len(created)} example files for {username}:")

    # Customize the examples with user-specific values
    user_config = user_examples / "home/myapp/config.toml"
    if user_config.exists():
        content = user_config.read_text()
        # Add user-specific comment
        content = f"# Configuration for {username}\n" + content
        user_config.write_text(content)

    print(f"\nExamples generated in: {user_examples}")
    print("Copy these files to get started:")
    for f in created:
        print(f"  {f.relative_to(user_examples)}")


# Run onboarding
onboard_user("alice")
```
**Explanation:** Generate examples as part of an onboarding workflow. You can then customize the generated files programmatically before presenting them to users.

**Example 4: Update examples (force overwrite)**
```python
from lib_layered_config import generate_examples
from pathlib import Path

# Regenerate examples, overwriting existing ones
examples_dir = Path("./examples")
created = generate_examples(
    destination=examples_dir,
    slug="myapp",
    vendor="Acme",
    app="MyApp",
    force=True,  # Overwrite existing examples
)

print(f"Regenerated {len(created)} example files")

# This is useful when you update your configuration schema
# and need to refresh the documentation examples
```
**Explanation:** Use `force=True` when updating examples after schema changes. This ensures all example files reflect your latest configuration structure.

**Example 5: Generate both POSIX and Windows examples**
```python
from lib_layered_config import generate_examples
from pathlib import Path


def generate_all_examples():
    """Generate examples for all platforms."""

    base_dir = Path("./docs/config-examples")

    # Generate POSIX examples
    posix_files = generate_examples(
        destination=base_dir / "linux-macos", slug="myapp", vendor="Acme", app="MyApp", platform="posix"
    )
    print(f"Generated {len(posix_files)} POSIX examples")

    # Generate Windows examples
    windows_files = generate_examples(
        destination=base_dir / "windows", slug="myapp", vendor="Acme", app="MyApp", platform="windows"
    )
    print(f"Generated {len(windows_files)} Windows examples")

    print(f"\nTotal: {len(posix_files) + len(windows_files)} example files")
    print(f"Location: {base_dir}")


generate_all_examples()
```
**Explanation:** Generate complete documentation showing users how to configure your app on any platform. This is essential for cross-platform applications.

---

### `display_config` and `OutputFormat`

Print a loaded `Config` the way the CLI's `read` command does.

```python
display_config(
    config: Config,
    *,
    output_format: OutputFormat = OutputFormat.HUMAN,
    section: str | None = None,
    console: Console | None = None,
    profile: str | None = None,
) -> None
```

**Parameters:**
- `config` (Config, required): The configuration to print, as `read_config` returns it.
- `output_format` (OutputFormat, optional): `OutputFormat.HUMAN` (`"human"`) prints TOML-style tables with a
  `# layer:<layer> profile:<profile> (<path>)` comment above each value; `OutputFormat.JSON` (`"json"`) prints
  the data as indented JSON. Default: `OutputFormat.HUMAN`.
- `section` (str | None, optional): Print only this top-level section. Default: `None` (everything).
- `console` (rich `Console` | None, optional): Where the human format is written. A console you pass writes
  to its own file as it is, so it raises where that file cannot encode a value. Default: `None` (stdout).
- `profile` (str | None, optional): Profile name shown in the provenance comments. Default: `None`
  (`profile:none`).

Both formats replace sensitive values with `***REDACTED***`.

A character stdout cannot encode (CJK or an emoji on a Windows pipe, which uses the cp1252 code page) is
written as an escape instead of raising `UnicodeEncodeError`, the way the CLI's `read` writes it: `\uXXXX`
in JSON, which parses back to the same value, and a Python backslash escape (`\u6f22`, `\U0001f600`) in
the human format. Characters stdout can encode, umlauts on cp1252 included, print as they are.

**Raises:** `ValueError` for a `section` the configuration does not have (`"Section 'nope' not found"`) or an
`output_format` that is not an `OutputFormat`.

```python
from lib_layered_config import OutputFormat, display_config, read_config

config = read_config(vendor="Acme", app="MyApp", slug="myapp", default_file="defaults.toml")
display_config(config)
# # Note: Nested dictionaries are displayed as [section.subsection] headers and might not match the actual TOML [section]
#
#
# [database]
#     # layer:defaults profile:none (defaults.toml)
#     host = "db.local"
#
#     # layer:defaults profile:none (defaults.toml)
#     password = "***REDACTED***"

display_config(config, output_format=OutputFormat.JSON, section="database")
# {
#   "database": {
#     "host": "db.local",
#     "password": "***REDACTED***"
#   }
# }
```

---

### Logging: `get_logger` and `bind_trace_id`

The library logs through the standard `logging` module and attaches no handler, so it is silent until your
application adds one.

- `get_logger()` returns the `lib_layered_config` logger. Each record carries a `context` attribute, a dict with
  the event's fields (`layer`, `path`, ...) and `trace_id`. Warnings such as `dotenv_skipped_foreign_owner`,
  `type_conflict` and `deploy_setting_ignored` are logged at `WARNING`; the load steps at `DEBUG` and `INFO`.
- `bind_trace_id(trace_id)` sets the trace id that every later record in the current context (a
  `contextvars` variable, so per thread and per asyncio task) carries; `bind_trace_id(None)` clears it.

```python
import logging

from lib_layered_config import bind_trace_id, get_logger, read_config


class PrintTrace(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        context = getattr(record, "context", {})
        print(record.levelname, record.getMessage(), context.get("trace_id"), context.get("layer"))


logger = get_logger()  # the "lib_layered_config" logger; silent until you attach a handler
logger.addHandler(PrintTrace())
logger.setLevel(logging.DEBUG)

bind_trace_id("req-42")  # every event logged in this context carries it
read_config(vendor="Acme", app="MyApp", slug="myapp", default_file="defaults.toml")
bind_trace_id(None)
# DEBUG config_file_read req-42 file
# DEBUG config_file_loaded req-42 file
# DEBUG layer_loaded req-42 defaults
# DEBUG dotenv_not_found req-42 dotenv
# DEBUG env_variables_loaded req-42 env
# INFO configuration_merged req-42 final
```

---

### Errors

Every exception the library defines derives from `ConfigError`, so one `except ConfigError` catches them all.
`ValidationError` and its subclasses are also `ValueError`s.

```text
Exception
+-- ConfigError
    +-- LayerLoadError          a layer file, .env or environment value cannot be read or parsed
    +-- InvalidFormatError      the loaders' parse error (see below)
    +-- NotFoundError           the loaders' missing-file signal (see below)
    +-- ValidationError         (also a ValueError) a refused identifier, platform, target or argument
        +-- DeployModeError         a refused dir_mode / file_mode
        +-- DeployPermissionsError  unusable permission settings
        +-- DeployDestinationError  a deploy destination is a symbolic link or not a regular file
        +-- GenerateDestinationError  an example path generate would write through is a link or not a regular file
        +-- LayerRootNotAbsoluteError  a layer root that is not absolute (a Windows root, or an empty or relative
                                       LIB_LAYERED_CONFIG_ETC / _MAC_APP_ROOT / _MAC_HOME_ROOT)
```

- When the home directory cannot be determined (HOME unset and the uid has no passwd entry), the read
  functions skip the user layer and its `.env` fallback, log the warning `user_layer_skipped_no_home`, and load
  every other layer. A deploy to the `user` target raises `RuntimeError` naming the variables that fix it. A
  set `XDG_CONFIG_HOME`, `LIB_LAYERED_CONFIG_MAC_HOME_ROOT` or `APPDATA` needs no home directory.
- A refusal that names a vendor, app, slug or hostname, or a layer root that is not absolute, writes each
  control character in it as `\uXXXX` (`slug contains invalid characters: demo\u000a`); a backslash is
  kept as it is. The profile refusal names its value with `repr`, as before.
- `LayerLoadError` is what the read functions and `read_deploy_config` raise for a file that does not decode or
  parse; its `__cause__` is the loader's `InvalidFormatError`. `deploy_config` raises it for its own source
  file. A broken file in one of the layers deploy reads its modes from makes it raise `DeployPermissionsError`
  instead (the configured modes are unknown), whose message names that file and which has no `__cause__`;
  with `set_permissions=False` that read does not happen.
- `InvalidFormatError` is raised by the file and environment loaders; the public functions re-raise it as
  `LayerLoadError`, so you meet it as that `__cause__`, when calling a loader yourself, or from
  `Config.as_dict(redact=True)` and `Config.to_json(redact=True)` on a `Config` you built yourself with values
  nested more than 300 levels deep (a read refuses tables past 100 levels and any value past 253, so a loaded
  one never is).
- `NotFoundError` is raised by the file loaders for a file that is not there; the read functions treat that
  as an empty layer (a missing `default_file` loads nothing) and do not raise it.

Errors from the operating system and the standard library pass through as they are: `FileNotFoundError` for a
deploy source that does not exist or is not a regular file, `PermissionError` behind a permission wall,
`FileExistsError` or `NotADirectoryError` when a directory deploy must create is a regular file, `TypeError` for
an argument of the wrong type, and a plain `ValueError` (not a `ConfigError`) for a `not_sensitive` entry with an
empty segment (`"a..b"`).

```python
from lib_layered_config import ConfigError, LayerLoadError, read_config

try:
    read_config(vendor="Acme", app="MyApp", slug="myapp", default_file="broken.toml")
except LayerLoadError as exc:
    print(f"cannot load configuration: {exc}")
except ConfigError as exc:  # any other library error, ValidationError included
    print(f"configuration error: {exc}")
# cannot load configuration: broken.toml is not valid TOML (line 2, column 1)
```

---

### `i_should_fail`

Intentionally raise a `RuntimeError` for testing error handling.

**Parameters:** None

**Raises:** `RuntimeError` with message `"i should fail"`.

**Example:**
```python
from lib_layered_config import i_should_fail

try:
    i_should_fail()
except RuntimeError as e:
    print(f"Caught expected error: {e}")
```

---

### Profile Validation

The library exports functions and constants for validating profile names before use. This is useful for pre-flight checks in configuration deployment or validating user input.

#### `DEFAULT_MAX_PROFILE_LENGTH`

Constant defining the default maximum length for profile names.

**Value:** `64` (characters)

**Example:**
```python
from lib_layered_config import DEFAULT_MAX_PROFILE_LENGTH

print(f"Profile names are limited to {DEFAULT_MAX_PROFILE_LENGTH} characters by default")
# Output: Profile names are limited to 64 characters by default
```

#### `validate_profile_name`

Validate a profile name for safe use in filesystem paths.

**Parameters:**
- `value` (str, required): The profile name to validate.
- `max_length` (int, optional): Maximum allowed length. Default: `64` characters. Set to `0` or negative to use the absolute maximum (255 chars).

**Returns:** The validated profile name (unchanged if valid).

**Raises:** `ValueError` when the profile name fails validation.

**Security Checks:**
- Length limit (default 64 chars, absolute max 255 chars for filesystem safety)
- No control characters (null bytes, newlines, tabs, etc.)
- No path traversal sequences (`../`, `..\\`)
- No path separators (`/`, `\\`)
- ASCII-only characters
- No Windows reserved names (CON, PRN, NUL, COM1-9, LPT1-9)
- Must start with alphanumeric character
- No trailing dots or spaces

**Note:** The `max_length` parameter is clamped to 255 characters for filesystem safety. Setting `max_length=1000` will effectively use 255 as the limit.

**Examples:**

**Example 1: Basic validation**
```python
from lib_layered_config import validate_profile_name

# Valid profile names
profile = validate_profile_name("production")  # Returns "production"
profile = validate_profile_name("test-v2")  # Returns "test-v2"
profile = validate_profile_name("dev_local")  # Returns "dev_local"
```

**Example 2: Handling invalid input**
```python
from lib_layered_config import validate_profile_name

try:
    validate_profile_name("")  # Empty string
except ValueError as e:
    print(f"Error: {e}")  # "profile cannot be empty"

try:
    validate_profile_name("../etc/passwd")  # Path traversal
except ValueError as e:
    print(f"Error: {e}")  # "profile contains invalid characters: ../etc/passwd"

try:
    validate_profile_name("a" * 100)  # Too long
except ValueError as e:
    print(f"Error: {e}")  # "profile exceeds maximum length of 64: 100 characters"
```

**Example 3: Custom length limits**
```python
from lib_layered_config import validate_profile_name

# Allow longer profiles (up to 255 chars absolute max)
profile = validate_profile_name("a" * 100, max_length=200)  # OK

# Even with max_length=1000, the absolute max of 255 applies
try:
    validate_profile_name("a" * 256, max_length=1000)
except ValueError as e:
    print(f"Error: {e}")  # "profile exceeds maximum length of 255: 256 characters"
```

---

#### `is_valid_profile_name`

Check if a profile name is valid without raising an exception.

**Parameters:**
- `value` (object, required): The profile name to check. `None` is considered valid (no profile); any other value that is not a `str` is not a valid name.
- `max_length` (int, optional): Maximum allowed length. Default: `64` characters. Set to `0` or negative to use the absolute maximum (255 chars).

**Returns:** `True` if the profile name is valid or `None`, `False` otherwise.

**Note:** The `max_length` parameter is clamped to 255 characters for filesystem safety, same as `validate_profile_name`.

**Examples:**

**Example 1: Pre-flight validation**
```python
from lib_layered_config import is_valid_profile_name, read_config


def load_config_with_profile(profile: str | None):
    """Load configuration, validating the profile name first."""
    if not is_valid_profile_name(profile):
        print(f"Invalid profile name: {profile}")
        return None

    return read_config(vendor="Acme", app="MyApp", slug="myapp", profile=profile)


# Usage
config = load_config_with_profile("production")  # Valid
config = load_config_with_profile("../etc")  # Invalid, returns None
config = load_config_with_profile(None)  # Valid (no profile)
```

**Example 2: User input validation**
```python
from lib_layered_config import is_valid_profile_name


def get_valid_profile():
    """Prompt user for a valid profile name."""
    while True:
        profile = input("Enter profile name (or 'none'): ").strip()
        if profile.lower() == "none":
            return None
        if is_valid_profile_name(profile):
            return profile
        print("Invalid profile name. Use lowercase letters, numbers, hyphens, underscores.")
        print("Cannot contain spaces, path separators, or special characters.")
```

**Example 3: Batch validation**
```python
from lib_layered_config import is_valid_profile_name

profiles = ["production", "test", "../hack", "staging-v2", "my profile"]
valid_profiles = [p for p in profiles if is_valid_profile_name(p)]
invalid_profiles = [p for p in profiles if not is_valid_profile_name(p)]

print(f"Valid: {valid_profiles}")  # ['production', 'test', 'staging-v2']
print(f"Invalid: {invalid_profiles}")  # ['../hack', 'my profile']
```

---

### Permission Constants

The library exports constants for Unix file permissions used during deployment. These constants define sensible defaults for different configuration layers.

#### `DEFAULT_APP_DIR_MODE`

Directory permission mode for app/host layers (system-wide configs).

**Value:** `0o755` (rwxr-xr-x)

#### `DEFAULT_APP_FILE_MODE`

File permission mode for app/host layers (system-wide configs).

**Value:** `0o644` (rw-r--r--)

#### `DEFAULT_USER_DIR_MODE`

Directory permission mode for user layer (private configs).

**Value:** `0o700` (rwx------)

#### `DEFAULT_USER_FILE_MODE`

File permission mode for user layer (private configs).

**Value:** `0o600` (rw-------)

**Example:**
```python
from lib_layered_config import (
    DEFAULT_APP_DIR_MODE,
    DEFAULT_APP_FILE_MODE,
    DEFAULT_USER_DIR_MODE,
    DEFAULT_USER_FILE_MODE,
)

print(f"App dir mode: {oct(DEFAULT_APP_DIR_MODE)}")  # 0o755
print(f"App file mode: {oct(DEFAULT_APP_FILE_MODE)}")  # 0o644
print(f"User dir mode: {oct(DEFAULT_USER_DIR_MODE)}")  # 0o700
print(f"User file mode: {oct(DEFAULT_USER_FILE_MODE)}")  # 0o600
```

**Explanation:** App/host layers use world-readable permissions since system-wide configuration should be accessible by all processes. User layer uses private permissions since personal configuration should not be accessible by other users. On Windows, permissions are skipped (Windows uses ACLs instead).

---

### Deploy permission types

Exported from the package root, used to configure or override `deploy_config`'s permission handling.

- `DeployMode`: An immutable, validated Unix permission mode; an unsafe one cannot be constructed. `kind` must
  be a `ModeKind` member (`ModeKind.FILE`, `ModeKind.DIRECTORY`); a str such as `"file"` raises `DeployModeError`.
- `ModeKind`: Whether a mode applies to a directory or a file (`DIRECTORY`, `FILE`).
- `LayerModes`: The directory mode and the file mode one layer is deployed with.
- `DeployPermissions`: Directory and file modes per deployment layer, plus whether to set them at all;
  `.defaults()` returns the built-in layer modes, `.for_layer(layer)` returns one layer's `LayerModes`
  (`layer` is a `Layer`, such as `Layer.APP`).
- `deploy_permissions_from_config`: Reads `[lib_layered_config.default_permissions]` from a merged
  configuration, with an `overrides=` mapping laid over the configured values for building a
  `DeployPermissions` yourself. It reads the `Config` as it is, so a user file's `app_*`/`host_*` in a
  `read_config(...)` result decides there, unlike in `deploy_config`'s own read. For `deploy_config` itself,
  pass runtime overrides through its own `permission_overrides=` parameter instead - see the `deploy_config`
  section above.
  Anything but a `Config` (a plain dict included) raises `TypeError`.
- `DeployModeError`: A permission setting was refused; the message names the reason or every offending bit.
- `DeployDestinationError`: A file deploy would write is a symbolic link or not a regular file; one line each,
  nothing written.
- `GenerateDestinationError`: An example path `generate_examples` would write through is a symbolic link or not a
  regular file (without `force`, only a link resolving to nothing); one line each, nothing written.
- `DeployPermissionsError`: The permission settings cannot be used; `.problems` lists one `PermissionProblem`
  per bad value, and `.hint` (optional) suggests a way to deploy anyway.
- `PermissionProblem`: One refused setting: its dotted key, why, and (`.source`) where it was set, when known.

