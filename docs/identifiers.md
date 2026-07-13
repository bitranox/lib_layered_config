# Identifiers and Profiles

How `vendor`, `app`, `slug`, and `profile` decide where configuration lives on each
platform, the naming rules, and identifier validation. For the overview see the
[README](../README.md).

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

**DO:**
- Use lowercase letters: `"myapp"`, `"database-tool"`
- Use hyphens for word separation: `"config-kit"`, `"db-manager"`
- Keep it short and memorable: `"myapp"` not `"my-super-awesome-application"`
- Use ASCII characters only: `"myapp"` not `"my-àpp"`
- Use the same slug everywhere in your application

**DON'T:**
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

**DO:**
- Use lowercase letters: `"test"`, `"production"`
- Use hyphens for word separation: `"staging-v2"`, `"dev-local"`
- Keep it short and descriptive: `"prod"` or `"production"`
- Use consistent profile names across your infrastructure

**DON'T:**
- Use spaces: `"my profile"` → use `"my-profile"`
- Use non-ASCII characters: `"tëst"` → will raise `ValueError`
- Use Windows reserved names: `"CON"`, `"NUL"` → will raise `ValueError`
- Use path separators: `"../etc"` → will raise `ValueError`
- Exceed 256 characters (absolute limit for filesystem safety)

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

| Platform | Path (+ optional config.d/)                                                        |
|----------|------------------------------------------------------------------------------------|
| Linux    | `/etc/xdg/db-manager/profile/production/config.toml`                               |
| macOS    | `/Library/Application Support/Acme/DatabaseManager/profile/production/config.toml` |
| Windows  | `C:\ProgramData\Acme\DatabaseManager\profile\production\config.toml`               |

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

| Identifier  | Format                               | Example                     | Used In                                                |
|-------------|--------------------------------------|-----------------------------|--------------------------------------------------------|
| **vendor**  | ASCII, spaces allowed                | `"Acme"`, `"Acme Corp"`     | macOS, Windows paths                                   |
| **app**     | ASCII, spaces allowed                | `"My App"`, `"Btx Fix Mcp"` | macOS, Windows paths                                   |
| **slug**    | lowercase-with-hyphens (recommended) | `"db-manager"`              | Linux paths, env var prefix (becomes `DB_MANAGER___`)  |
| **profile** | lowercase-with-hyphens (recommended) | `"production"`              | Optional subdirectory for environment-specific configs |

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

| Platform          | Without Profile                             | With `profile="test"`                                  |
|-------------------|---------------------------------------------|--------------------------------------------------------|
| **Linux (app)**   | `/etc/xdg/<slug>/config.toml`               | `/etc/xdg/<slug>/profile/test/config.toml`             |
| **Linux (host)**  | `/etc/xdg/<slug>/hosts/<hostname>.toml`     | `/etc/xdg/<slug>/profile/test/hosts/<hostname>.toml`   |
| **Linux (user)**  | `~/.config/<slug>/config.toml`              | `~/.config/<slug>/profile/test/config.toml`            |
| **macOS (app)**   | `/Library/.../<vendor>/<app>/config.toml`   | `/Library/.../<vendor>/<app>/profile/test/config.toml` |
| **Windows (app)** | `C:\ProgramData\<vendor>\<app>\config.toml` | `C:\ProgramData\...\profile\test\config.toml`          |

#### Profile Naming Rules

Profile names follow the same validation as other identifiers (see below), with an additional length constraint:
- **Default max length:** 64 characters (configurable via `max_profile_length`)
- **Absolute max length:** 256 characters (security hardening, cannot be overridden)

**Valid:** `test`, `production`, `staging-v2`, `dev_local`
**Invalid:** `../etc`, `.hidden`, `my profile`, `CON`, names exceeding 256 characters

---

### Identifier Validation Rules

All identifiers are validated to ensure they are safe for use as filesystem directory names on both Windows and Linux.

#### Validation by Identifier Type

| Identifier   | Spaces Allowed | Used For                                                         |
|--------------|----------------|------------------------------------------------------------------|
| **vendor**   | Yes            | macOS/Windows paths (`/Library/Application Support/Acme Corp/`)  |
| **app**      | Yes            | macOS/Windows paths (`/Library/Application Support/.../My App/`) |
| **slug**     | No             | Linux paths, environment variable prefix                         |
| **profile**  | No             | Profile subdirectory name                                        |
| **hostname** | No             | Host-specific config files                                       |

#### Common Validation Rules (All Identifiers)

| Rule                             | Description                                         | Example Invalid Value             |
|----------------------------------|-----------------------------------------------------|-----------------------------------|
| **ASCII-only**                   | No Unicode/UTF-8 special characters                 | `café`, `日本語`, `app🚀`             |
| **Must start with alphanumeric** | Cannot start with dot, hyphen, underscore, or space | `.hidden`, `-app`, `_private`     |
| **No path separators**           | Prevents path traversal attacks                     | `../etc`, `foo/bar`, `C:\Windows` |
| **No Windows-invalid chars**     | `<`, `>`, `:`, `"`, `\|`, `?`, `*` are forbidden    | `app<test>`, `file:name`          |
| **No Windows reserved names**    | CON, PRN, AUX, NUL, COM1-9, LPT1-9                  | `CON`, `prn`, `NUL.txt`           |
| **Cannot end with dot/space**    | Windows restriction                                 | `app.`, `name `                   |

#### Examples

```python
from lib_layered_config import read_config

# Valid identifiers
config = read_config(
    vendor="Acme Corp",      # OK: spaces allowed in vendor
    app="Btx Fix Mcp",       # OK: spaces allowed in app
    slug="db-manager",       # OK: lowercase with hyphens (no spaces)
    profile="production"     # OK: lowercase (no spaces)
)

# These will raise ValueError
read_config(vendor="../etc", ...)      # Path traversal
read_config(app="café", ...)           # Non-ASCII character
read_config(slug="CON", ...)           # Windows reserved name
read_config(slug="my slug", ...)       # Slug cannot have spaces
read_config(profile="my profile", ...) # Profile cannot have spaces
read_config(vendor=".hidden", ...)     # Starts with dot
read_config(app="app<test>", ...)      # Windows-invalid character
```

---
