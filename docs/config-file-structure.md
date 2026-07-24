# Configuration File Structure

The full annotated configuration file: top-level keys, sections, nested subtables and
arrays, and how each maps to Python access and environment-variable overrides. For the
overview see the [README](../README.md).

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
        "pool": {"size": 10, "timeout": 30},
        "ssl": {"enabled": true, "verify": true},
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

# Complex types (JSON): a value opening with [ or { is parsed as JSON.
# A whole array or object replaces the value at that key (to override a single
# array element instead, see "Overriding one element of an array" below).
MYAPP___DATABASE__REPLICAS='["replica1", "replica2"]'
MYAPP___DATABASE__POOL='{"size": 20, "timeout": 5}'
```

**Key Pattern:**
- Prefix: `SLUG` in uppercase followed by `___`
- Separator: Triple underscore (`___`) after prefix to distinguish from nesting
- Nesting: Double underscores (`__`) for each level
- Format: `PREFIX___SECTION__SUBSECTION__KEY=value`

**Overriding one element of an array:**

When a lower layer defines an array (for example an array-of-tables in TOML), a
higher-precedence env var overrides a single element by its numeric index, leaving the
other elements untouched:

```bash
# app.toml defines:
#   [[dataset]]
#   name = "primary"
#   dsn  = "postgres://old-host/db"
#   [[dataset]]
#   name = "secondary"

# Override only element 0's dsn. Element 1, and element 0's name, are kept.
MYAPP___DATASET__0__DSN=postgres://new-host/db
```

- The numeric segment (`0`, `1`, ...) is the list position.
- An index equal to the current length appends a new element. An index past that is
  ignored with a `type_conflict` warning, so the array is never silently replaced.
- This only kicks in when the target is already an array. With no underlying array the
  numeric segments stay ordinary string keys (`{"0": ...}`), same as normal nesting.
- Read the merged element back through the list, e.g. `config.get("dataset")[0]["dsn"]`.

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
