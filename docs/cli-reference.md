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

---

### `read`

Load configuration and print either human-readable prose or JSON.

**Usage:**
```bash
lib_layered_config read --vendor Acme --app ConfigKit --slug config-kit \
  [--prefer toml] [--prefer json] \
  [--start-dir /path/to/project] \
  [--default-file ./config.defaults.toml] \
  [--env-file /path/to/.env] \
  [--format human|json] \
  [--indent | --no-indent] \
  [--provenance | --no-provenance]
```

**Parameters:**

| Parameter                          | Type   | Required | Default        | Description                                                                                                                                         |
|------------------------------------|--------|----------|----------------|-----------------------------------------------------------------------------------------------------------------------------------------------------|
| `--vendor`                         | string | Yes      | -              | Vendor namespace used to compute filesystem paths                                                                                                   |
| `--app`                            | string | Yes      | -              | Application name used to compute filesystem paths                                                                                                   |
| `--slug`                           | string | Yes      | -              | Configuration slug for file paths and environment prefix                                                                                            |
| `--prefer`                         | string | No       | None           | Preferred file suffix (repeatable flag: `--prefer toml --prefer json`). Earlier values take precedence. Valid values: `toml`, `json`, `yaml`, `yml` |
| `--start-dir`                      | path   | No       | current dir    | Starting directory for upward `.env` file search. Must be an existing directory                                                                     |
| `--default-file`                   | path   | No       | None           | Path to lowest-precedence defaults file. Must be an existing file                                                                                   |
| `--env-file`                       | path   | No       | None           | Explicit `.env` file path. Skips upward directory search when set. Must be an existing file                                                         |
| `--format`                         | choice | No       | `human`        | Output format. Valid values: `human` (annotated prose), `json` (structured JSON)                                                                    |
| `--indent` / `--no-indent`         | flag   | No       | `--indent`     | Pretty-print JSON output with indentation. Only applies when `--format json`                                                                        |
| `--provenance` / `--no-provenance` | flag   | No       | `--provenance` | Include provenance metadata in JSON output. Only applies when `--format json`                                                                       |

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

**Example 6: Explicit .env file (skip directory search)**
```bash
# Load a specific .env file instead of searching upward
lib_layered_config read \
  --vendor Acme --app MyApp --slug myapp \
  --env-file /opt/myapp/secrets/.env.production
```

**Explanation:** Use `--env-file` to load a specific `.env` file directly. This bypasses the upward directory search entirely, which is useful in CI/CD pipelines or containers where the `.env` file lives in a known location.

**Example 7: Debugging configuration issues**
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
  [--env-file /path/to/.env] \
  [--indent | --no-indent]
```

**Parameters:**

| Parameter                  | Type   | Required | Default     | Description                          |
|----------------------------|--------|----------|-------------|--------------------------------------|
| `--vendor`                 | string | Yes      | -           | Vendor namespace                     |
| `--app`                    | string | Yes      | -           | Application name                     |
| `--slug`                   | string | Yes      | -           | Configuration slug                   |
| `--prefer`                 | string | No       | None        | Preferred file suffix (repeatable)   |
| `--start-dir`              | path   | No       | current dir | Starting directory for `.env` search |
| `--default-file`           | path   | No       | None        | Path to defaults file                |
| `--env-file`               | path   | No       | None        | Explicit `.env` file (skips search)  |
| `--indent` / `--no-indent` | flag   | No       | `--indent`  | Pretty-print JSON output             |

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
  [--permissions | --no-permissions]
```

**Parameters:**

| Parameter                            | Type   | Required | Default         | Description                                                                                                                                                  |
|--------------------------------------|--------|----------|-----------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `--source`                           | path   | Yes      | -               | Path to the configuration file to copy. Must be an existing file                                                                                             |
| `--vendor`                           | string | Yes      | -               | Vendor namespace                                                                                                                                             |
| `--app`                              | string | Yes      | -               | Application name                                                                                                                                             |
| `--slug`                             | string | Yes      | -               | Configuration slug                                                                                                                                           |
| `--profile`                          | string | No       | -               | Configuration profile name (e.g., `test`, `production`). Adds `profile/<name>/` segment to deployment paths                                                  |
| `--target`                           | choice | Yes      | -               | Layer targets to deploy to (repeatable flag). Valid values: `app`, `host`, `user`. Can specify multiple: `--target app --target user`                        |
| `--platform`                         | string | No       | auto-detect     | Override platform. Valid values: `linux`, `darwin`, `windows`, or any string starting with `win`                                                             |
| `--force`                            | flag   | No       | `false`         | When file exists with different content: backup existing file to `.bak` and overwrite                                                                        |
| `--batch`                            | flag   | No       | `false`         | Non-interactive mode: keeps existing files and writes new config as `.ucf` for review (CI/CD pipelines). Ignored if `--force` is set                         |
| `--permissions` / `--no-permissions` | flag   | No       | `--permissions` | Set Unix file permissions on deployed files. Uses layer-specific defaults: app/host = 755/644 (world-readable), user = 700/600 (private). Skipped on Windows |

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
  - **[K]eep existing** - Save new config as `.ucf` (Update Configuration File) - **default**
  - **[O]verwrite** - Backup original to `.bak`, then write new file

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

#### Default Permissions by Layer

| Layer  | Directory Mode    | File Mode         | Rationale                                         |
|--------|-------------------|-------------------|---------------------------------------------------|
| `app`  | `755` (rwxr-xr-x) | `644` (rw-r--r--) | System-wide config readable by all processes      |
| `host` | `755` (rwxr-xr-x) | `644` (rw-r--r--) | Machine-specific config readable by all processes |
| `user` | `700` (rwx------) | `600` (rw-------) | Private user config not accessible by others      |

#### CLI Usage

```bash
# Default: permissions enabled with layer-appropriate defaults
lib_layered_config deploy --source ./config.toml \
  --vendor Acme --app MyApp --slug myapp --target user
# Result: ~/.config/myapp/config.toml with mode 600

# Disable automatic permissions (use umask defaults)
lib_layered_config deploy --source ./config.toml \
  --vendor Acme --app MyApp --slug myapp --target user --no-permissions
```

#### Python API Usage

```python
from lib_layered_config import deploy_config

# Default: set_permissions=True with layer defaults
results = deploy_config(
    source="./config.toml",
    vendor="Acme",
    app="MyApp",
    targets=["user"],
    slug="myapp",
)
# User layer files get 700/600 permissions

# Custom permissions override
results = deploy_config(
    source="./config.toml",
    vendor="Acme",
    app="MyApp",
    targets=["app"],
    slug="myapp",
    dir_mode=0o750,   # Override directory mode
    file_mode=0o640,  # Override file mode
)

# Disable permissions entirely
results = deploy_config(
    source="./config.toml",
    vendor="Acme",
    app="MyApp",
    targets=["user"],
    slug="myapp",
    set_permissions=False,
)
```

#### Platform Behavior

| Platform    | Behavior                                                |
|-------------|---------------------------------------------------------|
| **Linux**   | Full permission support via `chmod()`                   |
| **macOS**   | Full permission support via `chmod()`                   |
| **Windows** | Permissions skipped (Windows uses ACLs, not Unix modes) |

> **Note:** On Windows, file access control should be managed through Windows ACLs (Access Control Lists) using native tools like `icacls` or PowerShell's `Set-Acl`. The library does not attempt to set Windows ACLs.

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
   MYAPP___DATABASE__PASSWORD=secret123
   MYAPP___API__TOKEN=tok_abc123
   ```

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
   ```

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

| Parameter                | Type   | Required | Default      | Description                                                                                      |
|--------------------------|--------|----------|--------------|--------------------------------------------------------------------------------------------------|
| `--destination`          | path   | Yes      | -            | Directory that will receive the example tree. Will be created if it doesn't exist                |
| `--slug`                 | string | Yes      | -            | Configuration slug used in generated files                                                       |
| `--vendor`               | string | Yes      | -            | Vendor namespace interpolated into examples                                                      |
| `--app`                  | string | Yes      | -            | Application name interpolated into examples                                                      |
| `--platform`             | choice | No       | auto-detect  | Override platform layout. Valid values: `posix` (Linux/macOS layout), `windows` (Windows layout) |
| `--force` / `--no-force` | flag   | No       | `--no-force` | Overwrite existing example files                                                                 |

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

| Parameter | Type   | Required         | Default | Description                                         |
|-----------|--------|------------------|---------|-----------------------------------------------------|
| `slug`    | string | Yes (positional) | -       | Configuration slug to convert to environment prefix |

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
