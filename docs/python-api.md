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
    default_env_prefix,
    deploy_config,
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

**Returns:** Dictionary with keys `layer` (str), `path` (str | None), and `key` (str), or `None` if the key was never observed.

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

##### `Config.as_dict()`

Return a deep, mutable copy of the configuration tree.

**Parameters:** None

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

##### `Config.to_json(indent=None)`

Serialize the configuration as JSON.

**Parameters:**
- `indent` (int | None, optional): Indentation level for pretty-printing. `None` produces compact output. Default: `None`.

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

Return a new configuration with shallow top-level overrides applied.

**Parameters:**
- `overrides` (Mapping[str, Any], required): Dictionary of top-level keys and values to override.

**Returns:** New `Config` instance with overrides applied, sharing provenance with the original.

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
- `prefer` (Sequence[str] | None, optional): Ordered sequence of preferred file suffixes (e.g., `["toml", "json", "yaml"]`). Files matching earlier suffixes take precedence. Default: `None` (accepts all supported formats with default ordering).
- `start_dir` (str | Path | None, optional): Starting directory for upward `.env` file search. Default: `None` (uses current working directory).
- `default_file` (str | Path | None, optional): Path to a file injected as the lowest-precedence layer (loaded before app/host/user layers). Default: `None` (no defaults layer).
- `dotenv_path` (str | Path | None, optional): Explicit path to a `.env` file. When set, this file is loaded directly instead of searching upward from `start_dir`. Default: `None` (use directory search).

**Returns:** Immutable `Config` object with merged configuration and provenance tracking.

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

**Example 2: Using file format preferences**
```python
from lib_layered_config import read_config

# Prefer TOML files over JSON when both exist
config = read_config(vendor="Acme", app="MyApp", slug="myapp", prefer=["toml", "json", "yaml"])

# If both config.toml and config.json exist in the same directory,
# config.toml will be loaded because it appears first in the prefer list
```
**Explanation:** The `prefer` parameter controls which file format takes precedence when multiple formats exist in the same directory. This is useful when migrating from one format to another.

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
    prefer=["toml", "json"],  # TOML preferred
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
**Explanation:** This complete example shows production-ready configuration loading with defaults, format preferences, and provenance tracking for debugging.

---

### `read_config_json`

Load configuration and return it as JSON with provenance metadata.

**Parameters:**
- `vendor` (str, required): Vendor namespace.
- `app` (str, required): Application name.
- `slug` (str, required): Configuration slug.
- `profile` (str | None, optional): Configuration profile name. Adds `profile/<name>/` to paths. Default: `None`.
- `prefer` (Sequence[str] | None, optional): Ordered sequence of preferred file suffixes. Default: `None`.
- `start_dir` (str | Path | None, optional): Starting directory for `.env` search. Default: `None`.
- `default_file` (str | Path | None, optional): Path to lowest-precedence defaults file. Default: `None`.
- `dotenv_path` (str | Path | None, optional): Explicit `.env` file path (skips upward search). Default: `None`.
- `indent` (int | None, optional): JSON indentation level. `None` for compact output. Default: `None`.

**Returns:** JSON string containing `{"config": {...}, "provenance": {...}}`.

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
- `prefer` (Sequence[str] | None, optional): Ordered sequence of preferred file suffixes. Default: `None`.
- `start_dir` (str | None, optional): Starting directory for `.env` search. Default: `None`.
- `default_file` (str | Path | None, optional): Path to lowest-precedence defaults file. Default: `None`.
- `dotenv_path` (str | Path | None, optional): Explicit `.env` file path (skips upward search). Default: `None`.

**Returns:** Tuple of `(data_dict, provenance_dict)` where both are mutable dictionaries.

**Examples:**

**Example 1: Template rendering with configuration**
```python
from lib_layered_config import read_config_raw
from jinja2 import Template

# Load configuration as raw dictionaries
data, provenance = read_config_raw(vendor="Acme", app="MyApp", slug="myapp")

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
data, provenance = read_config_raw(vendor="Acme", app="MyApp", slug="myapp")

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

# Load base configuration
data, provenance = read_config_raw(vendor="Acme", app="MyApp", slug="myapp")

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

### `default_env_prefix`

Compute the canonical environment variable prefix for a slug.

**Parameters:**
- `slug` (str, required): Configuration slug (e.g., `"config-kit"`).

**Returns:** Uppercase environment prefix with dashes converted to underscores (e.g., `"CONFIG_KIT"`).

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
print(f"Checking environment variables for prefix: {expected_prefix}_")

mismatched = []
for key in os.environ:
    if "DATABASE" in key or "SERVICE" in key:
        if not key.startswith(expected_prefix + "_"):
            mismatched.append(key)

if mismatched:
    print("\nWarning: Found environment variables that won't be loaded:")
    for key in mismatched:
        correct_name = f"{expected_prefix}_{key}"
        print(f"  {key} should be {correct_name}")
else:
    print("All environment variables are correctly prefixed!")
```
**Explanation:** Validate that your environment variables are correctly prefixed so they'll be picked up by the configuration loader.

---

### `deploy_config`

Copy a source configuration file into one or more layer directories with conflict handling.

**Parameters:**
- `source` (str | Path, required): Path to the configuration file to copy.
- `vendor` (str, required): Vendor namespace.
- `app` (str, required): Application name.
- `targets` (Sequence[str], required): Layer targets to deploy to. Valid values: `"app"`, `"host"`, `"user"`.
- `slug` (str | None, optional): Configuration slug. Default: `None` (uses `app` as slug).
- `profile` (str | None, optional): Configuration profile name. Adds `profile/<name>/` to deployment paths. Default: `None`.
- `platform` (str | None, optional): Override auto-detected platform. Valid values: `"linux"`, `"darwin"`, `"windows"`, or any value starting with `"win"`. Default: `None` (auto-detects from current platform).
- `force` (bool, optional): When True and file exists with different content, backup to `.bak` and overwrite. Default: `False`.
- `batch` (bool, optional): Non-interactive mode - keeps existing files and writes new config as `.ucf` for review (CI/CD). Default: `False`.
- `conflict_resolver` (Callable[[Path], DeployAction] | None, optional): Custom callback for conflict resolution. Default: `None`.
- `set_permissions` (bool, optional): Set Unix permissions on deployed files. Uses layer-specific defaults: app/host = 755/644, user = 700/600. Skipped on Windows. Default: `True`.
- `dir_mode` (int | None, optional): Override directory mode for all targets. Default: `None` (use layer defaults).
- `file_mode` (int | None, optional): Override file mode for all targets. Default: `None` (use layer defaults).

**Returns:** `list[DeployResult]` - Each result contains:
- `destination`: Path to the target file
- `action`: `DeployAction` enum (`CREATED`, `OVERWRITTEN`, `KEPT`, `SKIPPED`)
- `backup_path`: Path to `.bak` file (if action was `OVERWRITTEN`)
- `ucf_path`: Path to `.ucf` file (if action was `KEPT`)
- `dot_d_results`: List of `DeployResult` for companion `.d` directory files (if any)

**`.d` Directory Support:** If the source file has a companion `.d` directory (e.g., `defaults.toml` → `defaults.d/`), those files are also deployed to the corresponding `.d` directory at each destination. User-added files in the destination `.d` directory are preserved.

**Smart Skipping:** If the source content is byte-identical to the existing destination file, the file is skipped without creating backups (regardless of `force` or `batch` flags). This applies to both base files and `.d` directory files.

**Permissions:** By default (`set_permissions=True`), Unix file permissions are set automatically based on the target layer:
- **App/Host layers:** `755` for directories, `644` for files (world-readable)
- **User layer:** `700` for directories, `600` for files (private to user)
- **Windows:** Permissions skipped (Windows uses ACLs)

Use `dir_mode` and `file_mode` to override defaults, or `set_permissions=False` to skip entirely.

**Raises:** `FileNotFoundError` if source file does not exist.

**Examples:**

**Example 1: Deploy system-wide defaults**
```python
from lib_layered_config import deploy_config
from lib_layered_config.examples.deploy import DeployAction

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
from lib_layered_config import deploy_config
from lib_layered_config.examples.deploy import DeployAction

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
from lib_layered_config import deploy_config
from lib_layered_config.examples.deploy import DeployAction

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
from lib_layered_config import deploy_config
from lib_layered_config.examples.deploy import DeployAction

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
from lib_layered_config import deploy_config
from lib_layered_config.examples.deploy import DeployAction
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
from lib_layered_config import deploy_config
from lib_layered_config.examples.deploy import DeployAction

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
from lib_layered_config import deploy_config
from lib_layered_config.examples.deploy import DeployAction
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
from lib_layered_config import deploy_config
from lib_layered_config.examples.deploy import DeployAction

# Deploy with layer defaults (recommended)
# - App layer: 755 dirs, 644 files (world-readable)
# - User layer: 700 dirs, 600 files (private)
results = deploy_config(
    source="./config.toml",
    vendor="Acme",
    app="MyApp",
    targets=["user"],
    slug="myapp",
    set_permissions=True,  # Default - sets 700/600 for user layer
)

# Deploy with custom permissions (e.g., group-readable)
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

for result in results:
    if result.action == DeployAction.CREATED:
        print(f"Created: {result.destination}")
        # Check actual permissions (Linux/macOS)
        import stat

        mode = result.destination.stat().st_mode
        print(f"  Mode: {stat.filemode(mode)}")
```
**Explanation:** Use `set_permissions=True` (default) for automatic layer-aware permissions. Use `dir_mode` and `file_mode` to override defaults for special requirements (e.g., group-readable configs). Use `set_permissions=False` when permissions should be inherited from umask. On Windows, permission setting is automatically skipped.

---

### `generate_examples`

Generate example configuration trees for documentation or onboarding.

**Parameters:**
- `destination` (str | Path, required): Directory that will receive the example tree.
- `slug` (str, required): Configuration slug used in generated files.
- `vendor` (str, required): Vendor namespace.
- `app` (str, required): Application name.
- `force` (bool, optional): Overwrite existing example files. Default: `False`.
- `platform` (str | None, optional): Override platform layout. Valid values: `"posix"`, `"windows"`. Default: `None` (uses current platform).

**Returns:** List of `Path` objects for files created.

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
#   - etc/myapp/config.toml (app defaults)
#   - etc/myapp/hosts/your-hostname.toml (host overrides)
#   - xdg/myapp/config.toml (user preferences)
#   - xdg/myapp/config.d/10-override.toml (split overrides)
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
#   - ProgramData/Acme/MyApp/config.d/10-override.toml
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
    user_config = user_examples / "xdg/myapp/config.toml"
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

#### `validate_profile_name`

Validate a profile name for safe use in filesystem paths.

**Parameters:**
- `value` (str, required): The profile name to validate.
- `max_length` (int, optional): Maximum allowed length. Default: `64` characters. Set to `0` or negative to use the absolute maximum (256 chars).

**Returns:** The validated profile name (unchanged if valid).

**Raises:** `ValueError` when the profile name fails validation.

**Security Checks:**
- Length limit (default 64 chars, absolute max 256 chars for filesystem safety)
- No control characters (null bytes, newlines, tabs, etc.)
- No path traversal sequences (`../`, `..\\`)
- No path separators (`/`, `\\`)
- ASCII-only characters
- No Windows reserved names (CON, PRN, NUL, COM1-9, LPT1-9)
- Must start with alphanumeric character
- No trailing dots or spaces

**Note:** The `max_length` parameter is clamped to 256 characters for filesystem safety. Setting `max_length=1000` will effectively use 256 as the limit.

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

# Allow longer profiles (up to 256 chars absolute max)
profile = validate_profile_name("a" * 100, max_length=200)  # OK

# Even with max_length=1000, the absolute max of 256 applies
try:
    validate_profile_name("a" * 257, max_length=1000)
except ValueError as e:
    print(f"Error: {e}")  # "profile exceeds maximum length of 256: 257 characters"
```

---

#### `is_valid_profile_name`

Check if a profile name is valid without raising an exception.

**Parameters:**
- `value` (str | None, required): The profile name to check. `None` is considered valid (no profile).
- `max_length` (int, optional): Maximum allowed length. Default: `64` characters. Set to `0` or negative to use the absolute maximum (256 chars).

**Returns:** `True` if the profile name is valid or `None`, `False` otherwise.

**Note:** The `max_length` parameter is clamped to 256 characters for filesystem safety, same as `validate_profile_name`.

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
