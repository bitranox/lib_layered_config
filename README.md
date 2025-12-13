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
[![security: bandit](https://img.shields.io/badge/security-bandit-yellow.svg)](https://github.com/PyCQA/bandit)

A cross-platform configuration loader that deep-merges application defaults, host overrides, user profiles, `.env` files, and environment variables into a single immutable object. The core follows Clean Architecture boundaries so adapters (filesystem, dotenv, environment) stay isolated from the domain model while the CLI mirrors the same orchestration.

## Table of Contents

1. [Key Features](#key-features)
2. [Architecture Overview](#architecture-overview)
3. [Installation](#installation)
4. [Quick Start](#quick-start)
5. [Understanding Key Identifiers: Vendor, App, and Slug](#understanding-key-identifiers-vendor-app-and-slug)
   - [Configuration Profiles](#configuration-profiles)
6. [Configuration File Structure](#configuration-file-structure)
7. [Configuration Sources & Precedence](#configuration-sources--precedence)
8. [CLI Usage](#cli-usage)
9. [Python API](#python-api)
10. [Example Generation & Deployment](#example-generation--deployment)
11. [Provenance & Observability](#provenance--observability)
12. [Development](#development)
13. [License](#license)

## Key Features

- **Deterministic layering** — precedence is always `defaults → app → host → user → dotenv → env`.
- **Immutable value object** — returned `Config` prevents accidental mutation and exposes dotted-path helpers.
- **Provenance tracking** — every key reports the layer and path that produced it.
- **Cross-platform path discovery** — Linux (XDG), macOS, and Windows layouts with environment overrides for tests.
- **Configuration profiles** — organize environment-specific configs (test, staging, production) into isolated subdirectories.
- **`.d` directory support** — split configuration into multiple files using the Linux `.d` pattern (e.g., `config.d/10-database.toml`). Supports mixed formats (TOML, YAML, JSON) in the same directory.
- **Easy deployment** — deploy configs to app, host, and user layers with smart conflict handling that protects user customizations through automatic backups (`.bak`) and UCF files (`.ucf`) for safe CI/CD updates.
- **Fast parsing** — uses `rtoml` (Rust-based) for ~5x faster TOML parsing than stdlib `tomllib`.
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

> **Requires Python 3.10+** — uses `rtoml` (Rust-based TOML parser) for ~5x faster parsing than stdlib `tomllib`.
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

Before diving into configuration sources, it's important to understand the four key identifiers used throughout this library:

### Vendor

**What it is:** Your organization or company name (e.g., `"Acme"`, `"Mozilla"`, `"MyCompany"`).

**Where it's used:**
- **macOS:** `/Library/Application Support/Acme/MyApp/` and `~/Library/Application Support/Acme/MyApp/`
- **Windows:** `C:\ProgramData\Acme\MyApp\` and `%APPDATA%\Acme\MyApp\`
- **Linux:** Not used (Linux uses the slug directly)

**Example:**
```python
# Your company is "Acme Corp"
config = read_config(vendor="Acme", app="DatabaseTool", slug="db-tool")
# macOS paths: /Library/Application Support/Acme/DatabaseTool/config.toml
```

---

### App

**What it is:** Your application's full/display name (e.g., `"DatabaseTool"`, `"ConfigKit"`, `"MyService"`).

**Where it's used:**
- **macOS:** Combined with vendor in paths: `/Library/Application Support/Acme/MyApp/`
- **Windows:** Combined with vendor: `C:\ProgramData\Acme\MyApp\`
- **Linux:** Not used (Linux uses the slug directly)
- **Default slug:** If you don't specify a slug, the app name is used as the slug

**Example:**
```python
config = read_config(vendor="Acme", app="ConfigKit", slug="config-kit")
# macOS: /Library/Application Support/Acme/ConfigKit/config.toml
# Windows: C:\ProgramData\Acme\ConfigKit\config.toml
```

---

### Slug (Configuration Slug)

**What it is:** A lowercase, filesystem-friendly identifier for your configuration (e.g., `"myapp"`, `"config-kit"`, `"db-tool"`).

**Why it exists:** The slug serves as a **universal, platform-independent identifier** for your configuration that works consistently across:
1. Linux/UNIX filesystem paths (case-sensitive, prefers hyphens)
2. Environment variable prefixes (converted to uppercase)
3. Cross-platform scripts and automation

**Where it's used:**

#### 1. **Linux/UNIX Paths**
```bash
/etc/xdg/myapp/config.toml                    # System-wide (XDG-compliant)
/etc/xdg/myapp/config.d/10-database.toml      # Optional split config
/etc/xdg/myapp/config.d/20-logging.toml       # Files merged in order
/etc/xdg/myapp/hosts/server-01.toml           # Host-specific (XDG-compliant)
~/.config/myapp/config.toml                   # User-specific
~/.config/myapp/config.d/90-local.toml        # User's split config
~/.config/myapp/.env                          # Environment variables
```

Note: For backwards compatibility, the library also checks `/etc/myapp/` if `/etc/xdg/myapp/` is not found.

#### 2. **Environment Variable Prefix**
The slug is converted to uppercase with underscores, followed by a triple underscore (`___`) separator to clearly distinguish the prefix from section/key separators (which use double underscores `__`):
```bash
# Slug: "myapp" → Environment prefix: "MYAPP___"
MYAPP___DATABASE__HOST=localhost
MYAPP___DATABASE__PORT=5432
MYAPP___SERVICE__TIMEOUT=30

# Slug: "config-kit" → Environment prefix: "CONFIG_KIT___"
CONFIG_KIT___API__KEY=secret
CONFIG_KIT___DEBUG__ENABLED=true
```

#### 3. **Cross-Platform Consistency**
The slug provides a consistent identifier regardless of platform:
```python
# Same slug works on all platforms
config = read_config(vendor="Acme", app="My App", slug="myapp")

# Linux:   /etc/xdg/myapp/config.toml (+ optional config.d/)
# macOS:   /Library/Application Support/Acme/My App/config.toml (+ optional config.d/)
# Windows: C:\ProgramData\Acme\My App\config.toml (+ optional config.d\)
# Env vars: MYAPP___DATABASE__HOST (all platforms)
```

---

### Slug Naming Best Practices

✅ **DO:**
- Use lowercase letters: `"myapp"`, `"database-tool"`
- Use hyphens for word separation: `"config-kit"`, `"db-manager"`
- Keep it short and memorable: `"myapp"` not `"my-super-awesome-application"`
- Use ASCII characters only: `"myapp"` not `"my-àpp"`
- Use the same slug everywhere in your application

❌ **DON'T:**
- Use spaces: `"my app"` → use `"myapp"` or `"my-app"`
- Use uppercase: `"MyApp"` → use `"myapp"` (uppercase works but isn't recommended)
- Use underscores in the slug: `"my_app"` → use `"my-app"` (underscores are added automatically for env vars)
- Use non-ASCII characters: `"café"` → will raise `ValueError`
- Use Windows reserved names: `"CON"`, `"PRN"`, `"NUL"` → will raise `ValueError`
- Mix naming conventions across your codebase
- Use path separators (`/` or `\`): `"../etc"` will raise `ValueError`
- Start with a dot: `".hidden"` will raise `ValueError`

---

### Profile (Optional)

**What it is:** An optional identifier for environment-specific configurations (e.g., `"test"`, `"staging"`, `"production"`).

**Why it exists:** Profiles allow you to organize separate configuration sets for different environments (development, testing, staging, production) without mixing files or relying solely on environment variables.

**Where it's used:**
When a profile is specified, a `profile/<name>/` subdirectory is inserted into all configuration paths:

#### 1. **Linux/UNIX Paths (with profile)**
```bash
# Without profile:
/etc/xdg/myapp/config.toml
/etc/xdg/myapp/config.d/10-database.toml           # Optional split config
/etc/xdg/myapp/config.d/20-logging.toml
~/.config/myapp/config.toml
~/.config/myapp/config.d/90-local.toml             # User overrides

# With profile="production":
/etc/xdg/myapp/profile/production/config.toml
/etc/xdg/myapp/profile/production/config.d/10-database.toml
/etc/xdg/myapp/profile/production/config.d/20-cache.toml
~/.config/myapp/profile/production/config.toml
~/.config/myapp/profile/production/config.d/90-local.toml
```

#### 2. **macOS Paths (with profile)**
```bash
# Without profile:
/Library/Application Support/Acme/MyApp/config.toml
/Library/Application Support/Acme/MyApp/config.d/10-database.toml

# With profile="production":
/Library/Application Support/Acme/MyApp/profile/production/config.toml
/Library/Application Support/Acme/MyApp/profile/production/config.d/10-database.toml
```

#### 3. **Windows Paths (with profile)**
```bash
# Without profile:
C:\ProgramData\Acme\MyApp\config.toml
C:\ProgramData\Acme\MyApp\config.d\10-database.toml

# With profile="production":
C:\ProgramData\Acme\MyApp\profile\production\config.toml
C:\ProgramData\Acme\MyApp\profile\production\config.d\10-database.toml
```

#### 4. **Usage Example**
```python
from lib_layered_config import read_config

# Load production configuration
prod_config = read_config(
    vendor="Acme",
    app="MyApp",
    slug="myapp",
    profile="production"
)

# Load test configuration (different paths, completely isolated)
test_config = read_config(
    vendor="Acme",
    app="MyApp",
    slug="myapp",
    profile="test"
)

# Load default configuration (no profile, original paths)
default_config = read_config(
    vendor="Acme",
    app="MyApp",
    slug="myapp"
    # profile=None (default)
)
```

#### 5. **CLI Usage**
```bash
# Read production profile
lib_layered_config read --vendor Acme --app MyApp --slug myapp --profile production

# Deploy to test profile
lib_layered_config deploy --source config.toml --vendor Acme --app MyApp --slug myapp --profile test --target app
```

---

### Profile Naming Best Practices

✅ **DO:**
- Use lowercase letters: `"test"`, `"production"`
- Use hyphens for word separation: `"staging-v2"`, `"dev-local"`
- Keep it short and descriptive: `"prod"` or `"production"`
- Use consistent profile names across your infrastructure

❌ **DON'T:**
- Use spaces: `"my profile"` → use `"my-profile"`
- Use non-ASCII characters: `"tëst"` → will raise `ValueError`
- Use Windows reserved names: `"CON"`, `"NUL"` → will raise `ValueError`
- Use path separators: `"../etc"` → will raise `ValueError`

---

### Complete Example: How They Work Together

```python
from lib_layered_config import read_config

# Define your application identity (without profile)
config = read_config(
    vendor="Acme",           # Your company name
    app="DatabaseManager",   # Your application's display name
    slug="db-manager"        # Filesystem/environment-friendly identifier
)

# Or with a profile for environment-specific configuration
prod_config = read_config(
    vendor="Acme",
    app="DatabaseManager",
    slug="db-manager",
    profile="production"     # Optional: isolates config in profile subdirectory
)
```

**This creates the following structure (without profile):**

**On Linux:**
```
/etc/xdg/db-manager/config.toml               # System-wide (uses slug, XDG-compliant)
/etc/xdg/db-manager/config.d/10-connection.toml   # Split config (optional)
/etc/xdg/db-manager/config.d/20-pools.toml
~/.config/db-manager/config.toml              # User-specific (uses slug)
~/.config/db-manager/config.d/90-local.toml   # User overrides (optional)
Environment: DB_MANAGER___*                   # Env prefix (slug → uppercase + ___)
```

**On macOS:**
```
/Library/Application Support/Acme/DatabaseManager/config.toml
/Library/Application Support/Acme/DatabaseManager/config.d/10-connection.toml
~/Library/Application Support/Acme/DatabaseManager/config.toml
~/Library/Application Support/Acme/DatabaseManager/config.d/90-local.toml
Environment: DB_MANAGER___*
```

**On Windows:**
```
C:\ProgramData\Acme\DatabaseManager\config.toml
C:\ProgramData\Acme\DatabaseManager\config.d\10-connection.toml
%APPDATA%\Acme\DatabaseManager\config.toml
%APPDATA%\Acme\DatabaseManager\config.d\90-local.toml
Environment: DB_MANAGER___*
```

**With `profile="production"`:**

| Platform | Path (+ optional config.d/) |
|----------|------|
| Linux | `/etc/xdg/db-manager/profile/production/config.toml` |
| macOS | `/Library/Application Support/Acme/DatabaseManager/profile/production/config.toml` |
| Windows | `C:\ProgramData\Acme\DatabaseManager\profile\production\config.toml` |

---

### Why Four Identifiers?

**Different platforms have different conventions:**

- **Windows/macOS:** Prefer human-readable names with spaces and mixed case (`"Acme Corp"`, `"My Application"`)
- **Linux/UNIX:** Prefer lowercase with hyphens (`myapp`, `config-kit`)
- **Environment variables:** Must use uppercase with underscores (`MYAPP_`, `CONFIG_KIT_`)
- **Profiles:** Allow environment-specific configuration isolation (`test`, `staging`, `production`)

This library uses four identifiers so your application can follow **native conventions on each platform** while maintaining a **consistent configuration identity** and supporting **environment-specific configurations**.

---

### Quick Reference Table

| Identifier | Format | Example | Used In |
|------------|--------|---------|---------|
| **vendor** | ASCII, spaces allowed | `"Acme"`, `"Acme Corp"` | macOS, Windows paths |
| **app** | ASCII, spaces allowed | `"My App"`, `"Btx Fix Mcp"` | macOS, Windows paths |
| **slug** | lowercase-with-hyphens (recommended) | `"db-manager"` | Linux paths, env var prefix (becomes `DB_MANAGER___`) |
| **profile** | lowercase-with-hyphens (recommended) | `"production"` | Optional subdirectory for environment-specific configs |

**All identifiers are validated** to ensure cross-platform filesystem safety. See [Identifier Validation Rules](#identifier-validation-rules) below.

---

### Configuration Profiles

Profiles allow you to organize environment-specific configurations (e.g., `test`, `staging`, `production`) into isolated subdirectories. When a profile is specified, all configuration paths include a `profile/<name>/` segment.

#### How Profiles Work

**Without profile:**
```
/etc/xdg/myapp/config.toml
/etc/xdg/myapp/config.d/10-database.toml              # Optional split config
/etc/xdg/myapp/config.d/20-logging.toml
/etc/xdg/myapp/hosts/server-01.toml
~/.config/myapp/config.toml
~/.config/myapp/config.d/90-local.toml                # User overrides
```

**With `profile="production"`:**
```
/etc/xdg/myapp/profile/production/config.toml
/etc/xdg/myapp/profile/production/config.d/10-database.toml
/etc/xdg/myapp/profile/production/config.d/20-cache.toml
/etc/xdg/myapp/profile/production/hosts/server-01.toml
~/.config/myapp/profile/production/config.toml
~/.config/myapp/profile/production/config.d/90-local.toml
```

#### Using Profiles in Python

```python
from lib_layered_config import read_config

# Load production configuration
config = read_config(
    vendor="Acme",
    app="ConfigKit",
    slug="config-kit",
    profile="production"
)

# Load test configuration
test_config = read_config(
    vendor="Acme",
    app="ConfigKit",
    slug="config-kit",
    profile="test"
)
```

#### Using Profiles in CLI

```bash
# Read configuration for production profile
lib_layered_config read --vendor Acme --app ConfigKit --slug config-kit --profile production

# Deploy configuration to production profile paths
lib_layered_config deploy --source config.toml --vendor Acme --app ConfigKit --slug config-kit --profile production --target app
```

#### Profile Path Examples

Each path can have an optional companion `.d` directory (e.g., `config.d/`) for split configuration.

| Platform | Without Profile | With `profile="test"` |
|----------|-----------------|----------------------|
| **Linux (app)** | `/etc/xdg/<slug>/config.toml` | `/etc/xdg/<slug>/profile/test/config.toml` |
| **Linux (host)** | `/etc/xdg/<slug>/hosts/<hostname>.toml` | `/etc/xdg/<slug>/profile/test/hosts/<hostname>.toml` |
| **Linux (user)** | `~/.config/<slug>/config.toml` | `~/.config/<slug>/profile/test/config.toml` |
| **macOS (app)** | `/Library/.../<vendor>/<app>/config.toml` | `/Library/.../<vendor>/<app>/profile/test/config.toml` |
| **Windows (app)** | `C:\ProgramData\<vendor>\<app>\config.toml` | `C:\ProgramData\...\profile\test\config.toml` |

#### Profile Naming Rules

Profile names follow the same validation as other identifiers (see below).

**Valid:** `test`, `production`, `staging-v2`, `dev_local`
**Invalid:** `../etc`, `.hidden`, `my profile`, `CON`

---

### Identifier Validation Rules

All identifiers are validated to ensure they are safe for use as filesystem directory names on both Windows and Linux.

#### Validation by Identifier Type

| Identifier | Spaces Allowed | Used For |
|------------|----------------|----------|
| **vendor** | ✅ Yes | macOS/Windows paths (`/Library/Application Support/Acme Corp/`) |
| **app** | ✅ Yes | macOS/Windows paths (`/Library/Application Support/.../My App/`) |
| **slug** | ❌ No | Linux paths, environment variable prefix |
| **profile** | ❌ No | Profile subdirectory name |
| **hostname** | ❌ No | Host-specific config files |

#### Common Validation Rules (All Identifiers)

| Rule | Description | Example Invalid Value |
|------|-------------|----------------------|
| **ASCII-only** | No Unicode/UTF-8 special characters | `café`, `日本語`, `app🚀` |
| **Must start with alphanumeric** | Cannot start with dot, hyphen, underscore, or space | `.hidden`, `-app`, `_private` |
| **No path separators** | Prevents path traversal attacks | `../etc`, `foo/bar`, `C:\Windows` |
| **No Windows-invalid chars** | `<`, `>`, `:`, `"`, `\|`, `?`, `*` are forbidden | `app<test>`, `file:name` |
| **No Windows reserved names** | CON, PRN, AUX, NUL, COM1-9, LPT1-9 | `CON`, `prn`, `NUL.txt` |
| **Cannot end with dot/space** | Windows restriction | `app.`, `name ` |

#### Examples

```python
from lib_layered_config import read_config

# ✅ Valid identifiers
config = read_config(
    vendor="Acme Corp",      # OK: spaces allowed in vendor
    app="Btx Fix Mcp",       # OK: spaces allowed in app
    slug="db-manager",       # OK: lowercase with hyphens (no spaces)
    profile="production"     # OK: lowercase (no spaces)
)

# ❌ These will raise ValueError
read_config(vendor="../etc", ...)      # Path traversal
read_config(app="café", ...)           # Non-ASCII character
read_config(slug="CON", ...)           # Windows reserved name
read_config(slug="my slug", ...)       # Slug cannot have spaces
read_config(profile="my profile", ...) # Profile cannot have spaces
read_config(vendor=".hidden", ...)     # Starts with dot
read_config(app="app<test>", ...)      # Windows-invalid character
```

---

## Configuration File Structure

Configuration files use TOML, JSON, or YAML format. Here's a comprehensive example showing how to structure your configuration:

### Example Configuration File (TOML)

```toml
# config.toml - Complete example showing all structural features

# ============================================================================
# TOP-LEVEL KEYS (Simple Values)
# ============================================================================
# Access in Python: config.get("debug")
# Access in CLI: config["debug"]
# Environment variable: MYAPP___DEBUG=true

debug = false
environment = "production"
version = "1.0.0"


# ============================================================================
# SECTIONS (Tables in TOML)
# ============================================================================
# Sections group related configuration values
# Access in Python: config.get("database.host")
# Environment variable: MYAPP___DATABASE__HOST=localhost

[database]
host = "localhost"
port = 5432
name = "myapp_db"
username = "admin"
# Passwords should come from environment variables or .env files!
# Set via: MYAPP___DATABASE__PASSWORD=secret


# ============================================================================
# NESTED SECTIONS (Subtables)
# ============================================================================
# Use dot notation for nested sections
# Access in Python: config.get("database.pool.size")
# Environment variable: MYAPP___DATABASE__POOL__SIZE=20

[database.pool]
size = 10
max_overflow = 20
timeout = 30
recycle = 3600  # seconds


[database.ssl]
enabled = true
verify = true
cert_path = "/etc/ssl/certs/db.pem"


# ============================================================================
# ARRAYS (Lists)
# ============================================================================
# Access in Python: config.get("database.replicas")
# Returns: ["replica1.db.local", "replica2.db.local"]

[database]
replicas = [
    "replica1.db.local",
    "replica2.db.local",
    "replica3.db.local"
]


# ============================================================================
# SERVICE CONFIGURATION
# ============================================================================

[service]
name = "MyApp Service"
host = "0.0.0.0"
port = 8080
timeout = 30
base_url = "https://api.example.com"


# Nested retry configuration
[service.retry]
max_attempts = 3
backoff_multiplier = 2
initial_delay = 1.0  # seconds


# Multiple endpoints
[service.endpoints]
api = "/api/v1"
health = "/health"
metrics = "/metrics"


# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

[logging]
level = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL
format = "json"
output = "stdout"


[logging.handlers]
console = true
file = true
syslog = false


[logging.files]
path = "/var/log/myapp/app.log"
max_bytes = 10485760  # 10 MB
backup_count = 5


# ============================================================================
# FEATURE FLAGS
# ============================================================================
# Use sections for grouping related feature flags

[features]
new_ui = false
experimental_api = false
beta_features = false


[features.analytics]
enabled = true
sampling_rate = 0.1  # 10% of requests


# ============================================================================
# API CONFIGURATION
# ============================================================================

[api]
rate_limit = 1000  # requests per minute
timeout = 60


[api.authentication]
type = "jwt"  # jwt, oauth, apikey
token_expiry = 3600  # seconds


[api.cors]
enabled = true
allowed_origins = ["https://example.com", "https://app.example.com"]
allowed_methods = ["GET", "POST", "PUT", "DELETE"]


# ============================================================================
# CACHE CONFIGURATION
# ============================================================================

[cache]
backend = "redis"  # redis, memcached, memory
default_ttl = 300  # seconds


[cache.redis]
host = "localhost"
port = 6379
db = 0
password = ""  # Set via MYAPP___CACHE__REDIS__PASSWORD


# ============================================================================
# EMAIL CONFIGURATION
# ============================================================================

[email]
enabled = true
from_address = "noreply@example.com"
from_name = "MyApp"


[email.smtp]
host = "smtp.gmail.com"
port = 587
use_tls = true
username = "notifications@example.com"
# Password should come from environment: MYAPP___EMAIL__SMTP__PASSWORD


# ============================================================================
# MONITORING & OBSERVABILITY
# ============================================================================

[monitoring]
enabled = true


[monitoring.metrics]
backend = "prometheus"
port = 9090
path = "/metrics"


[monitoring.tracing]
enabled = true
backend = "jaeger"
sample_rate = 0.01  # 1% of requests


[monitoring.healthcheck]
enabled = true
interval = 30  # seconds
```

---

### Understanding the Structure

#### 1. **Top-Level Keys**
Simple key-value pairs at the root level:
```toml
debug = false
environment = "production"
```
**Access:**
- Python: `config.get("debug")` or `config["debug"]`
- CLI: Value appears as `debug: false`
- Environment: `MYAPP___DEBUG=true`

---

#### 2. **Sections (Tables)**
Sections group related configuration:
```toml
[database]
host = "localhost"
port = 5432
```
**Access:**
- Python: `config.get("database.host")` → `"localhost"`
- Python: `config["database"]` → `{"host": "localhost", "port": 5432}`
- Environment: `MYAPP___DATABASE__HOST=postgres.local`

---

#### 3. **Nested Sections (Subtables)**
Use dot notation for deeper nesting:
```toml
[database.pool]
size = 10
timeout = 30

[database.ssl]
enabled = true
verify = true
```
**Access:**
- Python: `config.get("database.pool.size")` → `10`
- Python: `config.get("database.ssl.enabled")` → `true`
- Environment: `MYAPP___DATABASE__POOL__SIZE=20`
- Environment: `MYAPP___DATABASE__SSL__ENABLED=false`

**Structure visualization:**
```python
{
    "database": {
        "host": "localhost",
        "port": 5432,
        "pool": {
            "size": 10,
            "timeout": 30
        },
        "ssl": {
            "enabled": true,
            "verify": true
        }
    }
}
```

---

#### 4. **Arrays (Lists)**
Multiple values in a list:
```toml
[database]
replicas = [
    "replica1.db.local",
    "replica2.db.local"
]

[api.cors]
allowed_origins = ["https://example.com", "https://app.example.com"]
```
**Access:**
- Python: `config.get("database.replicas")` → `["replica1.db.local", "replica2.db.local"]`
- Python: `config.get("database.replicas")[0]` → `"replica1.db.local"`

---

#### 5. **Data Types**

TOML supports multiple data types:

```toml
# Strings
name = "MyApp"
host = "localhost"

# Integers
port = 8080
timeout = 30

# Floats
sample_rate = 0.1
backoff_multiplier = 2.5

# Booleans
debug = false
enabled = true

# Arrays
replicas = ["host1", "host2"]
allowed_methods = ["GET", "POST"]

# Dates/Times (TOML feature)
created_at = 2024-01-15T10:30:00Z
```

---

### Complete Python Access Example

Given the example configuration above, here's how to access values:

```python
from lib_layered_config import read_config

config = read_config(vendor="Acme", app="MyApp", slug="myapp")

# Top-level keys
debug = config.get("debug")  # false
env = config.get("environment")  # "production"

# Section values
db_host = config.get("database.host")  # "localhost"
db_port = config.get("database.port")  # 5432

# Nested section values
pool_size = config.get("database.pool.size")  # 10
ssl_enabled = config.get("database.ssl.enabled")  # true

# Deep nesting
retry_attempts = config.get("service.retry.max_attempts")  # 3
smtp_port = config.get("email.smtp.port")  # 587

# Arrays
replicas = config.get("database.replicas")  # ["replica1.db.local", ...]
first_replica = config.get("database.replicas")[0]  # "replica1.db.local"

# Feature flags
new_ui_enabled = config.get("features.new_ui")  # false
analytics_rate = config.get("features.analytics.sampling_rate")  # 0.1

# With defaults
api_timeout = config.get("api.timeout", default=60)  # 60
cache_ttl = config.get("cache.default_ttl", default=300)  # 300
```

---

### Environment Variable Mapping

The slug is converted to an environment prefix (uppercase with triple underscore `___` separator), and nested keys use double underscores (`__`):

```bash
# Slug: "myapp" → Prefix: "MYAPP___"

# Top-level keys
MYAPP___DEBUG=true
MYAPP___ENVIRONMENT=staging

# Section keys (triple underscore after prefix, double for nesting)
MYAPP___DATABASE__HOST=postgres.production.local
MYAPP___DATABASE__PORT=5433

# Nested sections (each level separated by __)
MYAPP___DATABASE__POOL__SIZE=50
MYAPP___DATABASE__SSL__ENABLED=true

# Deep nesting
MYAPP___SERVICE__RETRY__MAX_ATTEMPTS=5
MYAPP___EMAIL__SMTP__PASSWORD=secret123
MYAPP___FEATURES__ANALYTICS__SAMPLING_RATE=0.5

# Arrays (JSON format for complex types)
MYAPP___DATABASE__REPLICAS='["replica1", "replica2"]'
```

**Key Pattern:**
- Prefix: `SLUG` in uppercase followed by `___`
- Separator: Triple underscore (`___`) after prefix to distinguish from nesting
- Nesting: Double underscores (`__`) for each level
- Format: `PREFIX___SECTION__SUBSECTION__KEY=value`

---

### JSON and YAML Equivalents

The same structure in JSON:

```json
{
  "debug": false,
  "environment": "production",
  "database": {
    "host": "localhost",
    "port": 5432,
    "pool": {
      "size": 10,
      "timeout": 30
    },
    "ssl": {
      "enabled": true,
      "verify": true
    },
    "replicas": ["replica1.db.local", "replica2.db.local"]
  },
  "service": {
    "host": "0.0.0.0",
    "port": 8080,
    "retry": {
      "max_attempts": 3,
      "backoff_multiplier": 2
    }
  }
}
```

And in YAML:

```yaml
debug: false
environment: production

database:
  host: localhost
  port: 5432
  pool:
    size: 10
    timeout: 30
  ssl:
    enabled: true
    verify: true
  replicas:
    - replica1.db.local
    - replica2.db.local

service:
  host: 0.0.0.0
  port: 8080
  retry:
    max_attempts: 3
    backoff_multiplier: 2
```

All three formats produce the same configuration structure and can be accessed identically through the library.

---

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

| Layer | Base File | Companion `.d` Directory |
|-------|-----------|--------------------------|
| **app** | `/etc/xdg/myapp/config.toml` | `/etc/xdg/myapp/config.d/` |
| **host** | `/etc/xdg/myapp/hosts/server-01.toml` | `/etc/xdg/myapp/hosts/server-01.d/` |
| **user** | `~/.config/myapp/config.toml` | `~/.config/myapp/config.d/` |

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
    default_file="./defaults.toml"  # Also checks ./defaults.d/*.{toml,yaml,json}
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

---

### `read`

Load configuration and print either human-readable prose or JSON.

**Usage:**
```bash
lib_layered_config read --vendor Acme --app ConfigKit --slug config-kit \
  [--prefer toml] [--prefer json] \
  [--start-dir /path/to/project] \
  [--default-file ./config.defaults.toml] \
  [--format human|json] \
  [--indent | --no-indent] \
  [--provenance | --no-provenance]
```

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `--vendor` | string | Yes | - | Vendor namespace used to compute filesystem paths |
| `--app` | string | Yes | - | Application name used to compute filesystem paths |
| `--slug` | string | Yes | - | Configuration slug for file paths and environment prefix |
| `--prefer` | string | No | None | Preferred file suffix (repeatable flag: `--prefer toml --prefer json`). Earlier values take precedence. Valid values: `toml`, `json`, `yaml`, `yml` |
| `--start-dir` | path | No | current dir | Starting directory for upward `.env` file search. Must be an existing directory |
| `--default-file` | path | No | None | Path to lowest-precedence defaults file. Must be an existing file |
| `--format` | choice | No | `human` | Output format. Valid values: `human` (annotated prose), `json` (structured JSON) |
| `--indent` / `--no-indent` | flag | No | `--indent` | Pretty-print JSON output with indentation. Only applies when `--format json` |
| `--provenance` / `--no-provenance` | flag | No | `--provenance` | Include provenance metadata in JSON output. Only applies when `--format json` |

**Examples:**

**Example 1: Basic configuration inspection (human-readable)**
```bash
# Load and display configuration in human-readable format
lib_layered_config read --vendor Acme --app MyApp --slug myapp
```

**Output:**
```
service.timeout: 30
  provenance: layer=app, path=/etc/xdg/myapp/config.toml
service.endpoint: https://api.example.com
  provenance: layer=user, path=/home/alice/.config/myapp/config.toml
database.host: localhost
  provenance: layer=env, path=None
database.port: 5432
  provenance: layer=app, path=/etc/xdg/myapp/config.toml
```

**Explanation:** The default format shows each configuration value with its source layer and file path (or "None" for environment variables). Perfect for quick debugging.

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

**Example 4: Using file format preferences**
```bash
# Prefer TOML files, then JSON, then YAML
lib_layered_config read \
  --vendor Acme --app MyApp --slug myapp \
  --prefer toml --prefer json --prefer yaml
```

**Explanation:** When multiple configuration file formats exist in the same directory (e.g., `config.toml` and `config.json`), the `--prefer` flag controls which one takes precedence. Earlier values win.

**Example 5: Load with defaults and specific .env location**
```bash
# Load configuration with shipped defaults and project-specific .env
lib_layered_config read \
  --vendor Acme --app MyApp --slug myapp \
  --default-file ./config/defaults.toml \
  --start-dir /opt/myapp \
  --format human
```

**Explanation:** Use `--default-file` to provide application defaults that ship with your app, and `--start-dir` to specify where to start searching for `.env` files (useful when running from a different directory).

**Example 6: Debugging configuration issues**
```bash
# Check if environment variables are overriding your config
MYAPP___SERVICE__TIMEOUT=5 lib_layered_config read \
  --vendor Acme --app MyApp --slug myapp \
  --format human | grep -A1 "service.timeout"
```

**Output:**
```
service.timeout: 5
  provenance: layer=env, path=None
```

**Explanation:** Set environment variables before the command to test how they override file-based configuration. The provenance shows which layer won.

---

### `read-json`

Always emit combined JSON output (config + provenance). This is a convenience alias for `read --format json --provenance`.

**Usage:**
```bash
lib_layered_config read-json --vendor Acme --app ConfigKit --slug config-kit \
  [--prefer toml] [--prefer json] \
  [--start-dir /path/to/project] \
  [--default-file ./config.defaults.toml] \
  [--indent | --no-indent]
```

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `--vendor` | string | Yes | - | Vendor namespace |
| `--app` | string | Yes | - | Application name |
| `--slug` | string | Yes | - | Configuration slug |
| `--prefer` | string | No | None | Preferred file suffix (repeatable) |
| `--start-dir` | path | No | current dir | Starting directory for `.env` search |
| `--default-file` | path | No | None | Path to defaults file |
| `--indent` / `--no-indent` | flag | No | `--indent` | Pretty-print JSON output |

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
  [--force] [--batch]
```

**Parameters:**

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `--source` | path | Yes | - | Path to the configuration file to copy. Must be an existing file |
| `--vendor` | string | Yes | - | Vendor namespace |
| `--app` | string | Yes | - | Application name |
| `--slug` | string | Yes | - | Configuration slug |
| `--profile` | string | No | - | Configuration profile name (e.g., `test`, `production`). Adds `profile/<name>/` segment to deployment paths |
| `--target` | choice | Yes | - | Layer targets to deploy to (repeatable flag). Valid values: `app`, `host`, `user`. Can specify multiple: `--target app --target user` |
| `--platform` | string | No | auto-detect | Override platform. Valid values: `linux`, `darwin`, `windows`, or any string starting with `win` |
| `--force` | flag | No | `false` | When file exists with different content: backup existing file to `.bak` and overwrite |
| `--batch` | flag | No | `false` | Non-interactive mode: keeps existing files and writes new config as `.ucf` for review (CI/CD pipelines). Ignored if `--force` is set |

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
  - **[K]eep existing** — Save new config as `.ucf` (Update Configuration File) — **default**
  - **[O]verwrite** — Backup original to `.bak`, then write new file

#### **With `--force` Flag:**
- ✅ **Creates new files** if they don't exist
- ✅ **Smart skips** if content is identical (no backup created)
- ✅ **Backs up and overwrites** if content differs — existing file saved to `.bak`
- 📋 Returns JSON with `overwritten` and `backups` arrays

```bash
# Force deploy with different content - creates backup
lib_layered_config deploy --source ./new-config.toml \
  --vendor Acme --app MyApp --slug myapp --target user --force
# Output: {"overwritten": ["/home/alice/.config/myapp/config.toml"],
#          "backups": ["/home/alice/.config/myapp/config.toml.bak"]}
```

#### **With `--batch` Flag:**
- ✅ **Creates new files** if they don't exist
- ✅ **Smart skips** if content is identical
- 📄 **Creates `.ucf` files** when content differs — keeps existing, writes new as `.ucf` for review
- 🛡️ **Safe for CI/CD pipelines** — predictable behavior without user interaction

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

# ✅ Result: File created
# Output: {"created": ["/etc/xdg/myapp/config.toml"]}
```

#### **Scenario 2: Redeploy Same Content (Smart Skip)**
```bash
# Deploy same config again - content identical
lib_layered_config deploy \
  --source ./dist/config.toml \
  --vendor Acme --app MyApp --slug myapp \
  --target app --force

# ✅ Result: Skipped (no backup created - content identical)
# Output: {"skipped": ["/etc/xdg/myapp/config.toml"]}
```

#### **Scenario 3: Update with Backup**
```bash
# Deploy new version with --force - creates automatic backup
lib_layered_config deploy \
  --source ./v2-config.toml \
  --vendor Acme --app MyApp --slug myapp \
  --target user --force

# ✅ Result: Old file backed up, new file written
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

# ✅ Result: Creates new files, keeps existing and writes UCF for review
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

---

### Best Practices

#### ✅ **DO:**

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
     echo "✅ Configuration deployed"
   elif echo "$result" | jq -e '.kept' > /dev/null 2>&1; then
     echo "ℹ️  Configuration already exists, new config at .ucf for review"
   else
     echo "ℹ️  Configuration unchanged (identical content)"
   fi
   ```

#### ❌ **DON'T:**

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

### Python API Equivalent

The Python `deploy_config()` function returns `list[DeployResult]` with rich information:

```python
from lib_layered_config import deploy_config
from lib_layered_config.examples.deploy import DeployAction

# Deploy with batch mode (CI/CD safe)
results = deploy_config(
    source="./config.toml",
    vendor="Acme",
    app="MyApp",
    targets=["user"],
    slug="myapp",
    batch=True  # Keep existing, write new as .ucf for review
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
    force=True  # Creates .bak backup before overwriting
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

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `--destination` | path | Yes | - | Directory that will receive the example tree. Will be created if it doesn't exist |
| `--slug` | string | Yes | - | Configuration slug used in generated files |
| `--vendor` | string | Yes | - | Vendor namespace interpolated into examples |
| `--app` | string | Yes | - | Application name interpolated into examples |
| `--platform` | choice | No | auto-detect | Override platform layout. Valid values: `posix` (Linux/macOS layout), `windows` (Windows layout) |
| `--force` / `--no-force` | flag | No | `--no-force` | Overwrite existing example files |

**Returns:** JSON array of file paths created.

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
  "/path/to/docs/configuration-examples/xdg/myapp/config.d/10-override.toml",
  "/path/to/docs/configuration-examples/home/myapp/config.toml",
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

# View the generated structure
tree ./examples
```

**Output:**
```
./examples/
├── etc/
│   └── myapp/
│       ├── config.toml                    # System-wide defaults
│       └── hosts/
│           └── your-hostname.toml          # Host-specific overrides
├── xdg/
│   └── myapp/
│       ├── config.toml                    # User preferences
│       └── config.d/
│           └── 10-override.toml           # Split configuration
└── .env.example                            # Environment variable template
```

**Explanation:** The generated structure mirrors the actual configuration layout your application will use, making it easy for users to understand where to place their config files.

**Example 5: Use examples as onboarding templates**
```bash
# Generate examples in a temp directory
lib_layered_config generate-examples \
  --destination /tmp/myapp-examples \
  --vendor Acme --app MyApp --slug myapp

# User can copy these to actual locations
echo "To get started, copy these examples:"
echo "  sudo cp /tmp/myapp-examples/etc/myapp/config.toml /etc/myapp/"
echo "  cp /tmp/myapp-examples/xdg/myapp/config.toml ~/.config/myapp/"
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
  "etc/myapp/config.toml"
  "xdg/myapp/config.toml"
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

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `slug` | string | Yes (positional) | - | Configuration slug to convert to environment prefix |

**Returns:** Uppercase environment prefix with dashes converted to underscores.

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

Print package metadata including version, author, and license.

**Usage:**
```bash
lib_layered_config info
```

**Parameters:** None

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

**Parameters:** None

**Raises:** `RuntimeError` with message `"i should fail"`.

**Example:**
```bash
lib_layered_config fail
# Output: RuntimeError: i should fail
# Exit code: 1
```

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
)
```

### `Layer` Enum

The `Layer` enum provides type-safe constants for configuration layer names:

```python
from lib_layered_config import Layer

# Available layers (in precedence order, lowest to highest):
Layer.DEFAULTS  # "defaults" - bundled application defaults
Layer.APP       # "app" - system-wide application config
Layer.HOST      # "host" - machine-specific overrides
Layer.USER      # "user" - per-user preferences
Layer.DOTENV    # "dotenv" - project-local .env file
Layer.ENV       # "env" - environment variables (highest precedence)

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
        layer = origin['layer']
        source = origin['path'] or '(ephemeral)'
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
        if origin['layer'] not in ['env', 'dotenv']:
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
prod_config = config.with_overrides({
    "service": {
        "endpoint": "https://prod-api.example.com",
        "timeout": 60
    },
    "database": {
        "host": "prod-db.example.com",
        "pool_size": 100
    }
})

print(f"Dev endpoint: {config.get('service.endpoint')}")
print(f"Prod endpoint: {prod_config.get('service.endpoint')}")

# Original config is unchanged
```
**Explanation:** This allows you to create environment-specific configurations from a base configuration without mutating the original.

**Example 2: Testing with feature flags**
```python
# Enable feature flags for testing
test_config = config.with_overrides({
    "features": {
        "new_ui": True,
        "experimental_api": True,
        "debug_mode": True
    }
})

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

**Returns:** Immutable `Config` object with merged configuration and provenance tracking.

**Examples:**

**Example 1: Basic usage - Load configuration with defaults**
```python
from lib_layered_config import read_config

# Simplest usage - just specify your app identity
config = read_config(
    vendor="Acme",
    app="MyApp",
    slug="myapp"
)

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
config = read_config(
    vendor="Acme",
    app="MyApp",
    slug="myapp",
    prefer=["toml", "json", "yaml"]
)

# If both config.toml and config.json exist in the same directory,
# config.toml will be loaded because it appears first in the prefer list
```
**Explanation:** The `prefer` parameter controls which file format takes precedence when multiple formats exist in the same directory. This is useful when migrating from one format to another.

**Example 3: Using a defaults file**
```python
from pathlib import Path
from lib_layered_config import read_config

# Start with application defaults before applying environment-specific overrides
config = read_config(
    vendor="Acme",
    app="MyApp",
    slug="myapp",
    default_file=Path("./config/defaults.toml")
)

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
config = read_config(
    vendor="Acme",
    app="MyApp",
    slug="myapp",
    start_dir=str(project_root)
)

# The library will search for .env files starting from project_root
# and moving upward through parent directories
```
**Explanation:** Use `start_dir` to control where `.env` file discovery begins. This ensures your project's `.env` file is found even if your script runs from a subdirectory.

**Example 5: Complete setup with all parameters**
```python
from pathlib import Path
from lib_layered_config import read_config

# Production-ready configuration loading
config = read_config(
    vendor="Acme",
    app="MyApp",
    slug="myapp",
    prefer=["toml", "json"],  # TOML preferred
    start_dir=Path.cwd(),      # Search .env from current directory
    default_file=Path(__file__).parent / "defaults.toml"  # Ship defaults
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
        indent=2  # Pretty-printed for readability
    )
    return json_payload, 200, {'Content-Type': 'application/json'}

# The response includes both config values and their sources
```
**Explanation:** Perfect for exposing configuration through APIs. The JSON includes provenance data so clients can see where each value came from.

**Example 2: Configuration audit tool**
```python
from lib_layered_config import read_config_json
import json

# Load configuration with provenance
payload = read_config_json(
    vendor="Acme",
    app="MyApp",
    slug="myapp",
    indent=2
)

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
    indent=None  # Compact output
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

**Returns:** Tuple of `(data_dict, provenance_dict)` where both are mutable dictionaries.

**Examples:**

**Example 1: Template rendering with configuration**
```python
from lib_layered_config import read_config_raw
from jinja2 import Template

# Load configuration as raw dictionaries
data, provenance = read_config_raw(
    vendor="Acme",
    app="MyApp",
    slug="myapp"
)

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
data, provenance = read_config_raw(
    vendor="Acme",
    app="MyApp",
    slug="myapp"
)

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
data, provenance = read_config_raw(
    vendor="Acme",
    app="MyApp",
    slug="myapp"
)

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

**Returns:** `list[DeployResult]` — Each result contains:
- `destination`: Path to the target file
- `action`: `DeployAction` enum (`CREATED`, `OVERWRITTEN`, `KEPT`, `SKIPPED`)
- `backup_path`: Path to `.bak` file (if action was `OVERWRITTEN`)
- `ucf_path`: Path to `.ucf` file (if action was `KEPT`)
- `dot_d_results`: List of `DeployResult` for companion `.d` directory files (if any)

**`.d` Directory Support:** If the source file has a companion `.d` directory (e.g., `defaults.toml` → `defaults.d/`), those files are also deployed to the corresponding `.d` directory at each destination. User-added files in the destination `.d` directory are preserved.

**Smart Skipping:** If the source content is byte-identical to the existing destination file, the file is skipped without creating backups (regardless of `force` or `batch` flags). This applies to both base files and `.d` directory files.

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
    slug="myapp"
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
    batch=True  # Non-interactive, creates .ucf for review
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
    force=True  # Backup to .bak, then overwrite
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
    force=True
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
        batch=True  # Non-interactive for scripts
    )

    for result in results:
        if result.action == DeployAction.CREATED:
            print(f"✓ Created: {result.destination}")
        elif result.action == DeployAction.KEPT:
            print(f"○ Kept existing, review new config at: {result.ucf_path}")
        elif result.action == DeployAction.SKIPPED:
            print(f"○ Skipped (identical content): {result.destination}")

except FileNotFoundError:
    print(f"✗ Error: Source file '{source_config}' not found")
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
    profile="production"  # Deploy to profile-specific subdirectory
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
    profile="test"  # Completely isolated from production
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
        print(f"⚠ Skipping {env}: config file not found")
        continue

    results = deploy_config(
        source=config_file,
        vendor="Acme",
        app="MyApp",
        targets=["app"],
        slug="myapp",
        profile=env,
        force=True  # Update existing configs (creates backups)
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
    platform="posix"  # Generate Linux/macOS examples
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
    platform="windows"  # Force Windows layout
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
    created = generate_examples(
        destination=user_examples,
        slug="myapp",
        vendor="Acme",
        app="MyApp"
    )

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
    force=True  # Overwrite existing examples
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
        destination=base_dir / "linux-macos",
        slug="myapp",
        vendor="Acme",
        app="MyApp",
        platform="posix"
    )
    print(f"Generated {len(posix_files)} POSIX examples")

    # Generate Windows examples
    windows_files = generate_examples(
        destination=base_dir / "windows",
        slug="myapp",
        vendor="Acme",
        app="MyApp",
        platform="windows"
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

Deployment is **additive** — it only creates or updates files that exist in the source `.d` directory. User-added files in the destination are **never deleted or modified**.

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
