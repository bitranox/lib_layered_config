# Implementation Plan: Profile Parameter

## Overview

Add a new optional `profile` parameter to the API and CLI that modifies path resolution to include a `profile/<profile-name>/` subdirectory in all configuration paths.

## Design Decisions

### Path Structure

**Without profile (current behavior):**
```
/etc/xdg/<slug>/config.toml
/etc/xdg/<slug>/config.d/
/etc/xdg/<slug>/hosts/<hostname>.toml
~/.config/<slug>/config.toml
```

**With profile="test":**
```
/etc/xdg/<slug>/profile/test/config.toml
/etc/xdg/<slug>/profile/test/config.d/
/etc/xdg/<slug>/profile/test/hosts/<hostname>.toml
~/.config/<slug>/profile/test/config.toml
```

### Validation

Profile names will use the same validation as other identifiers:
- No path separators (`/`, `\`)
- Cannot start with `.`
- Cannot be empty (but `None` is valid - means no profile)

### API Changes

1. **`read_config()`** - Add optional `profile: str | None = None` parameter
2. **`read_config_json()`** - Add optional `profile: str | None = None` parameter
3. **`read_config_raw()`** - Add optional `profile: str | None = None` parameter
4. **`deploy_config()`** - Add optional `profile: str | None = None` parameter
5. **CLI `read`** - Add `--profile` option
6. **CLI `read-json`** - Add `--profile` option
7. **CLI `deploy`** - Add `--profile` option

---

## Implementation Steps

### Step 1: Add `validate_profile` to domain/identifiers.py

Add a new validation function (or reuse `validate_identifier` with `name="profile"`).

**File:** `src/lib_layered_config/domain/identifiers.py`

```python
def validate_profile(value: str | None) -> str | None:
    """Validate profile name or return None if not provided."""
    if value is None:
        return None
    return validate_identifier(value, "profile")
```

**Tests:** `tests/domain/test_identifiers.py`
- Test valid profile names
- Test rejection of `/`, `\`, `.` prefix, empty string
- Test `None` passes through

---

### Step 2: Add `profile` to `PlatformContext`

**File:** `src/lib_layered_config/adapters/path_resolvers/_base.py`

Update `PlatformContext` dataclass:
```python
@dataclass(frozen=True)
class PlatformContext:
    vendor: str
    app: str
    slug: str
    cwd: Path
    env: dict[str, str]
    hostname: str
    profile: str | None = None  # NEW
```

Add helper method or function:
```python
def profile_segment(self) -> Path:
    """Return 'profile/<name>' path segment or empty path."""
    if self.profile:
        return Path("profile") / self.profile
    return Path()
```

---

### Step 3: Update `DefaultPathResolver.__init__`

**File:** `src/lib_layered_config/adapters/path_resolvers/default.py`

Add `profile` parameter and validate it:
```python
def __init__(
    self,
    *,
    vendor: str,
    app: str,
    slug: str,
    profile: str | None = None,  # NEW
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    platform: str | None = None,
    hostname: str | None = None,
) -> None:
    # ... existing validation ...
    self.profile = validate_profile(profile)  # NEW

    self._ctx = PlatformContext(
        vendor=self.vendor,
        app=self.application,
        slug=self.slug,
        cwd=self.cwd,
        env=self.env,
        hostname=self.hostname,
        profile=self.profile,  # NEW
    )
```

---

### Step 4: Update Linux Strategy

**File:** `src/lib_layered_config/adapters/path_resolvers/_linux.py`

Update `app_paths()`:
```python
def app_paths(self) -> Iterable[str]:
    etc_root = Path(self.ctx.env.get("LIB_LAYERED_CONFIG_ETC", "/etc"))
    profile_seg = self._profile_segment()
    # XDG-compliant location
    yield from collect_layer(etc_root / "xdg" / self.ctx.slug / profile_seg)
    # Legacy fallback
    yield from collect_layer(etc_root / self.ctx.slug / profile_seg)

def _profile_segment(self) -> Path:
    if self.ctx.profile:
        return Path("profile") / self.ctx.profile
    return Path()
```

Update `host_paths()`:
```python
def host_paths(self) -> Iterable[str]:
    etc_root = Path(self.ctx.env.get("LIB_LAYERED_CONFIG_ETC", "/etc"))
    profile_seg = self._profile_segment()
    # XDG location
    xdg_candidate = etc_root / "xdg" / self.ctx.slug / profile_seg / "hosts" / f"{self.ctx.hostname}.toml"
    if xdg_candidate.is_file():
        yield str(xdg_candidate)
    # Legacy
    candidate = etc_root / self.ctx.slug / profile_seg / "hosts" / f"{self.ctx.hostname}.toml"
    if candidate.is_file():
        yield str(candidate)
```

Update `user_paths()`:
```python
def user_paths(self) -> Iterable[str]:
    xdg = self.ctx.env.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    profile_seg = self._profile_segment()
    yield from collect_layer(base / self.ctx.slug / profile_seg)
```

Update `dotenv_path()`:
```python
def dotenv_path(self) -> Path | None:
    base = Path(self.ctx.env.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    profile_seg = self._profile_segment()
    return base / self.ctx.slug / profile_seg / ".env"
```

---

### Step 5: Update macOS Strategy

**File:** `src/lib_layered_config/adapters/path_resolvers/_macos.py`

Similar changes - add `_profile_segment()` helper and inject into all path methods.

---

### Step 6: Update Windows Strategy

**File:** `src/lib_layered_config/adapters/path_resolvers/_windows.py`

Similar changes - add `_profile_segment()` helper and inject into all path methods.

---

### Step 7: Update `core.py` Public API

**File:** `src/lib_layered_config/core.py`

Add `profile` parameter to all three functions:

```python
def read_config(
    *,
    vendor: str,
    app: str,
    slug: str,
    profile: str | None = None,  # NEW
    prefer: Sequence[str] | None = None,
    start_dir: str | None = None,
    default_file: str | Path | None = None,
) -> Config:
    ...

def read_config_json(
    *,
    vendor: str,
    app: str,
    slug: str,
    profile: str | None = None,  # NEW
    prefer: Sequence[str] | None = None,
    start_dir: str | Path | None = None,
    indent: int | None = None,
    default_file: str | Path | None = None,
) -> str:
    ...

def read_config_raw(
    *,
    vendor: str,
    app: str,
    slug: str,
    profile: str | None = None,  # NEW
    prefer: Sequence[str] | None = None,
    start_dir: str | None = None,
    default_file: str | Path | None = None,
) -> MergeResult:
    ...
```

Update `_build_resolver()`:
```python
def _build_resolver(
    *,
    vendor: str,
    app: str,
    slug: str,
    profile: str | None,  # NEW
    start_dir: str | None,
) -> DefaultPathResolver:
    return DefaultPathResolver(
        vendor=vendor,
        app=app,
        slug=slug,
        profile=profile,  # NEW
        cwd=Path(start_dir) if start_dir else None,
    )
```

---

### Step 8: Update Deploy Functions

**File:** `src/lib_layered_config/examples/deploy.py`

Add `profile` to `deploy_config()`:
```python
def deploy_config(
    source: str | Path,
    *,
    vendor: str,
    app: str,
    targets: Sequence[str],
    slug: str | None = None,
    profile: str | None = None,  # NEW
    platform: str | None = None,
    force: bool = False,
) -> list[Path]:
    ...
```

Update `_prepare_resolver()`:
```python
def _prepare_resolver(
    *,
    vendor: str,
    app: str,
    slug: str,
    profile: str | None,  # NEW
    platform: str | None,
) -> DefaultPathResolver:
    ...
```

Update all `DeploymentStrategy` subclasses to use profile from resolver:
- `LinuxDeployment`
- `MacDeployment`
- `WindowsDeployment`

Each `_*_path()` method needs to include the profile segment.

---

### Step 9: Update CLI Commands

**File:** `src/lib_layered_config/cli/read.py`

Add to both `read_command` and `read_json_command`:
```python
@click.option(
    "--profile",
    default=None,
    help="Configuration profile name (e.g., 'test', 'production')",
)
```

Update `build_read_query()` call to pass profile.

**File:** `src/lib_layered_config/cli/deploy.py`

Add to `deploy_command`:
```python
@click.option(
    "--profile",
    default=None,
    help="Configuration profile name (e.g., 'test', 'production')",
)
```

**File:** `src/lib_layered_config/cli/common.py`

Update `build_read_query()` to accept and pass `profile`.

---

### Step 10: Update `__init__.py` Exports

**File:** `src/lib_layered_config/__init__.py`

No changes needed if `validate_profile` stays internal. If we want to expose it:
```python
from .domain.identifiers import Layer, validate_profile
```

---

### Step 11: Write Tests

#### Unit Tests

**File:** `tests/domain/test_identifiers.py`
- Add tests for `validate_profile()`

**File:** `tests/adapters/test_path_resolver.py`
- Test `DefaultPathResolver` with profile parameter
- Test each platform strategy with profile
- Verify paths include `profile/<name>/` segment

**File:** `tests/unit/test_core.py` (or create new)
- Test `read_config()` with profile
- Test `read_config_raw()` with profile

#### Integration/E2E Tests

**File:** `tests/e2e/test_read_config.py`
- Add test case with profile parameter
- Verify config from profiled paths is loaded

**File:** `tests/examples/test_deploy.py`
- Test `deploy_config()` with profile
- Verify files deploy to profiled paths

**File:** `tests/e2e/test_cli.py`
- Test CLI `read --profile test`
- Test CLI `deploy --profile test`

---

### Step 12: Update Documentation

**File:** `README.md`
- Add profile parameter to all API examples
- Add `--profile` to CLI examples
- Add section explaining profiles
- Update path tables to show profile variant

**File:** `CHANGELOG.md`
- Document new feature under `## [3.1.0]` or `## [3.0.2]`

---

## File Change Summary

| File | Change Type |
|------|-------------|
| `src/lib_layered_config/domain/identifiers.py` | Add `validate_profile()` |
| `src/lib_layered_config/adapters/path_resolvers/_base.py` | Add `profile` to `PlatformContext` |
| `src/lib_layered_config/adapters/path_resolvers/default.py` | Add `profile` parameter |
| `src/lib_layered_config/adapters/path_resolvers/_linux.py` | Update all path methods |
| `src/lib_layered_config/adapters/path_resolvers/_macos.py` | Update all path methods |
| `src/lib_layered_config/adapters/path_resolvers/_windows.py` | Update all path methods |
| `src/lib_layered_config/adapters/path_resolvers/_dotenv.py` | No changes (uses strategy) |
| `src/lib_layered_config/core.py` | Add `profile` to public API |
| `src/lib_layered_config/examples/deploy.py` | Add `profile` to deploy |
| `src/lib_layered_config/cli/read.py` | Add `--profile` option |
| `src/lib_layered_config/cli/deploy.py` | Add `--profile` option |
| `src/lib_layered_config/cli/common.py` | Update query builder |
| `tests/domain/test_identifiers.py` | Add profile validation tests |
| `tests/adapters/test_path_resolver.py` | Add profile path tests |
| `tests/e2e/test_read_config.py` | Add profile integration test |
| `tests/examples/test_deploy.py` | Add profile deploy test |
| `tests/e2e/test_cli.py` | Add CLI profile tests |
| `README.md` | Document profile feature |
| `CHANGELOG.md` | Add release notes |

---

## Estimated Test Cases

1. **Validation:**
   - `validate_profile(None)` → `None`
   - `validate_profile("test")` → `"test"`
   - `validate_profile("prod-v1")` → `"prod-v1"`
   - `validate_profile("../etc")` → `ValueError`
   - `validate_profile(".hidden")` → `ValueError`
   - `validate_profile("")` → `ValueError`

2. **Path Resolution (Linux):**
   - `profile=None` → `/etc/xdg/myapp/config.toml`
   - `profile="test"` → `/etc/xdg/myapp/profile/test/config.toml`
   - `profile="test"` → `/etc/xdg/myapp/profile/test/hosts/hostname.toml`
   - `profile="test"` → `~/.config/myapp/profile/test/config.toml`

3. **Deploy:**
   - `deploy_config(..., profile="test")` → deploys to profiled paths

4. **CLI:**
   - `lib_layered_config read --profile test ...` → reads from profiled paths
   - `lib_layered_config deploy --profile test ...` → deploys to profiled paths

---

## Open Questions

1. **Environment variable for profile?** Should we support `LIB_LAYERED_CONFIG_PROFILE` environment variable as an alternative to CLI/API parameter?

2. **Profile in `.env` path?** The current design includes profile in `.env` path. Is this desired, or should `.env` remain profile-agnostic?

3. **Generate examples with profile?** Should `generate_examples()` also support profile parameter?
