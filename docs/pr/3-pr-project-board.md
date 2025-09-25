here’s a **concrete project board** you can drop into GitHub/Jira/Linear.
It’s organized by **Milestones → Epics → Issues**, with **acceptance criteria, TDD-first tests, estimates, labels, and dependencies**.
Names are short and imperative so they read well on a kanban board.

---

# Milestones

* **M0 – Bootstrap (Week 1)**
* **M1 – Core Config (Weeks 2–3)**
* **M2 – Adapters & Precedence (Weeks 3–4)**
* **M3 – Observability, Docs & Release (Week 5)**

---

# Epics

* **E1:** Scaffolding & Quality Gates
* **E2:** Domain `Config` VO & Error Taxonomy
* **E3:** Ports (PathResolver, FileLoader, DotEnvLoader, EnvLoader, Merger)
* **E4:** Merge Use Case & `read_config`
* **E5:** OS Path Adapters (Linux/macOS/Windows)
* **E6:** File Loaders (TOML/JSON/YAML)
* **E7:** `.env` + `os.environ` Adapters
* **E8:** Example Generators & Docs
* **E9:** Observability & Release

---

# Issues (ready to copy into your tracker)

> **Conventions:**
> Labels: `type:feature`, `type:test`, `type:docs`, `type:infra`, `prio:P1|P2|P3`
> Estimates: **S** ≤ 0.5d, **M** ≤ 1d, **L** ≤ 2d
> Each issue lists a **TDD plan** (tests first), **Tasks**, and **Acceptance Criteria**.

---

## M0 – Bootstrap

### 1) Init repo with src-layout & pyproject

* **Labels:** type\:infra, prio\:P1
* **TDD:** `tests/smoke/test_import.py::test_package_imports` (fails until scaffolding exists)
* **Tasks:**

  * Create `src/<pkg>/__init__.py` with `__all__` stub.
  * Add `pyproject.toml` (ruff, pyright/mypy strict, pytest, coverage config).
  * Setup `pre-commit` (ruff, formatter, pyright/mypy).
* **Acceptance:**

  * `pytest -q` green for smoke test.
  * `ruff`, `pyright/mypy` pass.
* **Estimate:** S

### 2) CI pipeline (lint → type → test → security → build)

* **Labels:** type\:infra, prio\:P1
* **TDD:** CI fails without stages; add minimal dummy test to verify stage wiring.
* **Tasks:** GitHub Actions (or equivalent) with matrix for 3.12 / 3.13.
* **Acceptance:** All stages pass on default branch; artifacts include sdist+wheel.
* **Estimate:** M
* **Depends on:** #1

---

## M1 – Core Config

### 3) Domain VO `Config` (immutable, typed)

* **Labels:** type\:feature, prio\:P1
* **TDD:**

  * `tests/unit/test_config_vo.py::test_get_dot_path`
  * `::test_as_dict_deep_copy`
  * `::test_to_json_roundtrip`
  * `::test_origin_provenance`
  * `::test_with_overrides_immutability`
* **Tasks:** Implement `Config` (frozen dataclass, `MappingProxyType`, `origin`, `with_overrides`).
* **Acceptance:** All unit tests pass; no I/O/logging in VO; public API typed.
* **Estimate:** M

### 4) Error taxonomy

* **Labels:** type\:feature, prio\:P1
* **TDD:** `tests/unit/test_errors.py::test_isinstance_hierarchy`
* **Tasks:** Add `ConfigError`, `InvalidFormat`, `ValidationError`, `NotFound`.
* **Acceptance:** Error hierarchy stable; referenced by later tests.
* **Estimate:** S

### 5) Ports (Protocols) skeleton

* **Labels:** type\:feature, prio\:P1
* **TDD:** `tests/contract/test_ports_signatures.py` checks Protocol existence and method signatures.
* **Ports:** `PathResolver`, `FileLoader`, `DotEnvLoader`, `EnvLoader`, `Merger`
* **Acceptance:** Contracts in place; no adapter yet.
* **Estimate:** M
* **Depends on:** #3, #4

### 6) Deep-merge policy (application service)

* **Labels:** type\:feature, prio\:P1
* **TDD:**

  * `tests/property/test_merge_properties.py::test_associativity`
  * `::test_idempotency`
  * `::test_precedence_overwrites`
  * `tests/unit/test_merge_lists.py::test_list_policy_documented`
* **Tasks:** Implement deterministic deep-merge with documented list rules.
* **Acceptance:** All property tests pass; merge policy documented (docstring).
* **Estimate:** L
* **Depends on:** #5

---

## M2 – Adapters & Precedence

### 7) OS PathResolver – Linux (XDG)

* **Labels:** type\:feature, prio\:P1
* **TDD:**

  * `tests/unit/paths/test_linux_paths.py::test_candidate_order`
  * `::test_hostname_path`
  * `::test_env_xdg_fallbacks`
* **Tasks:** Produce ordered candidates for app/host/user + `.env` search from CWD.
* **Acceptance:** Order exactly as spec; missing files ignored in higher layers.
* **Estimate:** M
* **Depends on:** #5

### 8) OS PathResolver – macOS

* **Labels:** type\:feature, prio\:P2
* **TDD:** `tests/unit/paths/test_macos_paths.py::tests_*`
* **Tasks:** Use `/Library/Application Support/<Vendor>/<App>/...`
* **Acceptance:** Candidate list matches spec (app, hosts, user, dotenv).
* **Estimate:** M
* **Depends on:** #5

### 9) OS PathResolver – Windows

* **Labels:** type\:feature, prio\:P2
* **TDD:** `tests/unit/paths/test_windows_paths.py::tests_*`
* **Tasks:** `%ProgramData%\<Vendor>\<App>\...`, `%APPDATA%` / `%LOCALAPPDATA%`.
* **Acceptance:** Candidate list matches spec; `%COMPUTERNAME%` handled; spaces allowed.
* **Estimate:** M
* **Depends on:** #5

### 10) FileLoader – TOML (core)

* **Labels:** type\:feature, prio\:P1
* **TDD:**

  * `tests/contract/test_file_loader.py::test_toml_valid`
  * `::test_toml_invalid_raises_invalidformat`
  * encoding BOM cases
* **Tasks:** Load TOML → dict; strict errors; no side effects.
* **Acceptance:** Contract tests pass.
* **Estimate:** M
* **Depends on:** #5

### 11) FileLoader – JSON (core)

* **Labels:** type\:feature, prio\:P2
* **TDD:** reuse contract: `::test_json_*`
* **Tasks:** Load JSON; uniform errors.
* **Acceptance:** Contract tests pass; parity with TOML behavior.
* **Estimate:** S
* **Depends on:** #10

### 12) FileLoader – YAML (optional extra)

* **Labels:** type\:feature, prio\:P3
* **TDD:** reuse contract: `::test_yaml_*`
* **Tasks:** Optional dependency (extras), safe loader only.
* **Acceptance:** Contract tests pass; optional extras documented.
* **Estimate:** M
* **Depends on:** #10, #11

### 13) DotEnvLoader – upward search & parsing

* **Labels:** type\:feature, prio\:P1
* **TDD:**

  * `tests/contract/test_dotenv_loader.py::test_upward_search`
  * `::test_nested_keys_A__B`
  * `::test_quotes_and_comments`
* **Tasks:** Parse `.env` to nested dict, respect quoting and comments.
* **Acceptance:** Contract tests pass; search begins at CWD and walks upward.
* **Estimate:** M
* **Depends on:** #5

### 14) EnvLoader – prefix + `__` nesting

* **Labels:** type\:feature, prio\:P1
* **TDD:**

  * `tests/contract/test_env_loader.py::test_prefix_default_env_prefix`
  * `::test_case_and_type_coercion`
  * `::test_collision_resolution`
* **Tasks:** Read from `os.environ`, prefix from `slug` via `default_env_prefix(slug)`.
* **Acceptance:** Contract tests pass; deterministic mapping; no leakage.
* **Estimate:** M
* **Depends on:** #5

### 15) `read_config` composition root & E2E precedence

* **Labels:** type\:feature, prio\:P1
* **TDD:**

  * `tests/e2e/test_read_config.py::test_full_precedence_order`
  * `::test_missing_files_silently_skipped`
  * `::test_origin_provenance_accurate`
  * `::test_vendor_app_slug_paths_linux_macos_windows` (parametrized)
* **Tasks:** Wire ports to adapters; return `Config`.
* **Acceptance:** E2E passes; API typed; no framework types at surface.
* **Estimate:** L
* **Depends on:** #6–#14

---

## M3 – Observability, Docs & Release

### 16) Example generators (`config.toml` per layer, `.env.example`)

* **Labels:** type\:feature, prio\:P2
* **TDD:**

  * `tests/unit/test_examples.py::test_idempotent_generation`
  * `::test_no_overwrite_without_flag`
  * `::test_commented_defaults_present`
* **Tasks:** Generate example files; respect existing files.
* **Acceptance:** Files generated; README references paths and samples.
* **Estimate:** M
* **Depends on:** #15

### 17) Observability hooks (adapter boundaries)

* **Labels:** type\:feature, prio\:P2
* **TDD:**

  * `tests/unit/test_logging.py::test_no_logs_in_domain_application`
  * `::test_trace_id_propagation`
  * `::test_nullhandler_installed_for_library`
* **Tasks:** Structured logs at adapters; `contextvars` trace\_id; NullHandler at package import.
* **Acceptance:** Tests pass; import remains lightweight.
* **Estimate:** S
* **Depends on:** #15

### 18) README & doctests

* **Labels:** type\:docs, prio\:P1
* **TDD:** Doctests: `Config.get`, `default_env_prefix`, quickstart sample.
* **Tasks:** Usage, precedence diagram, OS paths table, CLI & Python examples.
* **Acceptance:** `pytest --doctest-glob='README.md'` green; examples runnable.
* **Estimate:** M
* **Depends on:** #15–#17

### 19) Packaging: `py.typed`, extras, classifiers

* **Labels:** type\:infra, prio\:P2
* **TDD:** `tests/unit/test_import_cost.py::test_import_is_lightweight` (optional), build in CI.
* **Tasks:** Include `py.typed`, extras for YAML, strict Python requires (>=3.12), wheel/sdist build.
* **Acceptance:** Build artifacts correct; install locally works; typing recognized by IDEs.
* **Estimate:** S
* **Depends on:** #18

### 20) Security audit & release dry-run

* **Labels:** type\:infra, prio\:P2
* **TDD:** CI step fails if Bandit/pip-audit find critical issues.
* **Tasks:** Add SBOM (optional), audit deps, tag-based publish dry-run.
* **Acceptance:** CI green; changelog updated; version bumped (SemVer).
* **Estimate:** S
* **Depends on:** #19

---

## Global Definitions

### TDD Flow (for every issue)

1. **Red:** Write the smallest failing test (unit/contract/property/E2E).
2. **Green:** Implement the minimal code to pass.
3. **Refactor:** Remove duplication; enforce SRP/ISP/OCP; keep types strict.

### Definition of Done (per issue)

* All new tests green; coverage on changed code ≥ 90% (core).
* Lint/type/security checks pass.
* Public API changes documented; examples updated.

### Definition of Done (project)

* Clean Architecture dependency rule enforced (domain/app free of I/O/logs; adapters only at edges).
* `read_config` returns immutable, typed `Config`; precedence & deep-merge correct; `.env` & env prefix work; provenance via `origin()`.
* Public surface small & explicit via `__all__`.
* CI green across 3.12/3.13; build artifacts ready; `.env.example` & example configs included.

---

## Ready-to-use Commands (put in README/Makefile)

```bash
# install (uv/poetry/pip-tools—pick one; example with uv)
uv sync

# lint + type + test
ruff check .
pyright
pytest -q --maxfail=1 --cov=<pkg> --cov-fail-under=90

# security
bandit -q -r src/<pkg>
pip-audit

# build
python -m build
```

---

## Backlog (nice-to-haves after M3)

* CLI adapter (`configctl`) to print effective config / origins.
* JSON Schema export of effective config.
* Pluggable validation via Pydantic (edge-only).
* Watch mode for file changes (dev-only adapter).

---

