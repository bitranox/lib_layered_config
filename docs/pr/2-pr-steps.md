---

# Step-by-Step Plan (TDD + DoD)

## 0) Project Scaffolding & Quality Gates

**Goal:** Initialize repo; set up tooling & CI.
**TDD:** First smoke test (import package, `read_config` signature present).
**Tasks:**

* `src/` layout, `pyproject.toml`, `__all__` in package.
* Tools: Ruff, Pyright/Mypy (strict), pytest (+ pytest-asyncio), coverage gate ≥90%, import-linter (layering), Bandit & pip-audit.
* CI jobs: lint → type-check → test (coverage) → security → build (sdist/wheel).
  **DoD:** All jobs green; minimal smoke test green; no top-level side effects at import.

---

## 1) Domain VO `Config` & Error Taxonomy

**Goal:** Immutable, typed return object instead of `dict`; stable exceptions.
**TDD:** Tests for immutability, `get("a.b")`, `as_dict()`, `to_json()`, `origin()`, `with_overrides()`.
**Tasks:** `Config` (frozen dataclass, MappingProxy), `ConfigError`, `InvalidFormat`, `ValidationError`, `NotFound`.
**DoD:** All VO methods tested; no logs/I/O in domain; types stable & documented.

---

## 2) Define Ports (Application)

**Goal:** Narrow, cohesive interfaces (ISP) for adapters.
**TDD:** Contract test skeleton per port (signature verification + LSP harness).
**Ports:**

* `PathResolver` (OS candidate paths),
* `FileLoader` (TOML/YAML/JSON → dict),
* `DotEnvLoader`,
* `EnvLoader` (prefix + `__` nesting),
* `Merger` (deep merge policy).
  **DoD:** Ports typed, minimal (ISP), contract test harness present.

---

## 3) Merge Use Case (Application)

**Goal:** Deterministic deep merge with key precedence (app → host → user → dotenv → env).
**TDD:** Property-based tests (associativity/idempotency), overwrite rules, list policy.
**DoD:** Merge invariants proven; edge cases (empty files, mixed types) covered.

---

## 4) OS Path Resolution (Adapter: `PathResolver`)

**Goal:** Candidate paths for Linux/macOS/Windows per convention.
**TDD:** Path tests with `tmp_path`/`monkeypatch` for env vars/hostname; order asserted.
**DoD:** Path lists correct per OS; missing files skipped silently; order stable & documented.

---

## 5) `FileLoader` Adapters (TOML/YAML/JSON)

**Goal:** Load & validate individual files.
**TDD:** Format errors → `InvalidFormat`; valid parse → dict; BOM/encoding edge cases.
**DoD:** TOML (core), JSON (core), YAML optional as extra dependency (library mode: minimal runtime deps).

---

## 6) `.env` Adapter (`DotEnvLoader`)

**Goal:** Upward search from CWD; `.env` → nested keys (`A__B`).
**TDD:** Multiple directories, comments, empty lines, quoting; conflicts vs user/env layer.
**DoD:** Parser robust, search strategy tested, no secrets logged.

---

## 7) `EnvLoader` (Process Environment)

**Goal:** `<SLUG>_` prefix, `__` nesting, helper `default_env_prefix(slug)`.
**TDD:** Case sensitivity, numeric/bool values, collisions; prefix helper.
**DoD:** Prefix rule clear; mapping deterministic; no leaks outside central config module.

---

## 8) `read_config` Use Case & Composition Root

**Goal:** End-to-end merge of all layers; return `Config`.
**TDD:**

* Full precedence E2E tests (all layers),
* “missing file” silently skipped,
* Provenance via `Config.origin(key)` correct,
* `vendor`/`app`/`slug` influence paths as specified.
  **DoD:** `read_config` stable & typed; no framework types at public API; domain/application free of I/O/logs.

---

## 9) Example Config Generators

**Goal:** Example files per layer (`config.toml`, `.env.example`).
**TDD:** Generation idempotent; existing files not overwritten (without flag); commented defaults correct.
**DoD:** Examples present in repo; README references them; `.env.example` included.

---

## 10) Observability (Adapter Boundaries)

**Goal:** Structured logs, `trace_id` via `contextvars`; NullHandler for library.
**TDD:** No logs in domain/application; no root logger reconfiguration; trace ID propagated.
**DoD:** Logging hooks documented; import remains lightweight.

---

## 11) Docs & Developer Ergonomics

**Goal:** README (usage, paths, precedence, examples); API overview.
**TDD:** Doc snippets as doctests (at least `Config.get`, `default_env_prefix`).
**DoD:** README complete; examples runnable; public API pinned in `__all__`.

---

## 12) CI Hardening & Release Preparation

**Goal:** Quality gates, packaging, `py.typed`, wheel/sdist.
**TDD:** Release dry-run in CI; import cost test; layer contracts enforced via import-linter.
**DoD:** All gates green (lint/types/tests/coverage/security/build); wheel includes `py.typed`; SemVer & changelog present.

---

# TDD Loop (per step)

* **Red:** write the smallest failing test (unit/contract/property/E2E).
* **Green:** implement minimally until tests pass.
* **Refactor:** remove duplication, unify names, enforce SRP/OCP/ISP.
* **Gates:** lint & type-check run continuously.
* **Contracts:** run the same contract suite across all adapters (LSP).

---

# Definition of Done (DoD)

## DoD per step

A step is **done** when:

* all relevant **unit/contract/property/E2E tests** are green,
* **lint/type-check** passes,
* **acceptance criteria** met, docs/examples updated,
* no broken main branch, no ignored tests, no secrets in code/logs.

## Overall DoD

* **Architecture:** Dependency rule enforced; domain/application free of I/O/logs; ports narrow; adapters only at edges.
* **API/Quality:** Public API small, typed, explicit via `__all__`; coverage ≥90% (core); CI green (lint/types/tests/security/build).
* **Functionality:** `read_config` returns immutable `Config`; precedence & deep-merge correct; `.env` & env prefixes work; provenance available via `origin()`.
* **Ops:** Structured logs at adapters; NullHandler; import lightweight.
* **Docs:** README complete; `.env.example` & examples included; OS paths documented.

---

## Acceptance Criteria (measurable, examples)

* **Layer precedence:** For same key, `env` overrides `dotenv` > `user` > `host` > `app`; golden cases tested.
* **Property tests:** Merge is idempotent & associative (proven with Hypothesis).
* **OS paths:** Candidate order per OS exactly as specified (tests).
* **Error cases:** Invalid format → `InvalidFormat`; missing file → silent skip.
* **Security:** Bandit/pip-audit pass with no critical findings.
* **Imports:** Import time small; no top-level side effects.

---
