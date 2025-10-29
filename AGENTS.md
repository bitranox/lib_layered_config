# Repository Guidelines

## On session start

whenever You wait for user input or finished, execute "paplay /usr/share/sounds/codex/ready.wav"
whenever You have a question, execute "paplay /usr/share/sounds/codex/ready.wav"
whenever You have an error, execute "paplay /usr/share/sounds/codex/error.wav"

Review the system prompt files in `/media/srv-main/softdev/*/projects/softwarestack/systemprompts` and keep their guidance in working memory:

- core_programming_solid.md
- python_solid_architecture_enforcer.md
- python_clean_architecture.md
- python_clean_code.md
- python_small_functions_style.md
- python_libraries_to_use.md
- python_structure_template.md
- self_documenting.md
- self_documenting_template.md
- python_jupyter_notebooks.md
- python_testing.md


always apply those Rules :

- core_programming_solid.md

when writing or refracturing Bash scripts, apply those Rules :

- core_programming_solid.md
- bash_clean_architecture.md
- bash_clean_code.md
- bash_small_functions.md

when writing or refracturing Python scripts, apply those Rules :
- core_programming_solid.md
- python_solid_architecture_enforcer.md
- python_clean_architecture.md
- python_clean_code.md
- python_small_functions_style.md
- python_libraries_to_use.md
- python_lib_structure_template.md

## Project Structure & Module Organization

- `src/lib_layered_config/domain`: immutable value objects (`Config`), exception hierarchy.
- `src/lib_layered_config/application`: orchestrators and ports (protocols, merge policy).
- `src/lib_layered_config/adapters`: boundary implementations (filesystem paths, file loaders, `.env`, env vars) and structured logging.
- `src/lib_layered_config/core.py`: composition root exposing `read_config` / `read_config_raw`.
- `src/lib_layered_config/examples`: helper functions for generating example config files.
- `scripts/`: automation for lint/type/test/build/publish flows (copied from template, adapted for this project).
- `tests/`: unit, adapter, application, and end-to-end suites.

### Versioning & Releases

- Single source of truth for the package version is `pyproject.toml` (`[project].version`).
- Automation rewrites `src/lib_cli_exit_tools/__init__conf__.py` from `pyproject.toml`, so runtime code imports generated constants instead of querying `importlib.metadata`.
- After updating project metadata (version, summary, URLs, authors) run `make test` (or `python -m scripts.test`) to regenerate the metadata module before committing.
- Tag releases `vX.Y.Z` and push tags; CI will build artifacts and publish when configured.

### Common Make Targets (Alphabetical)


| Target            | One-line description                                                           |
|-------------------|--------------------------------------------------------------------------------|
| `build`           | Build wheel/sdist and attempt Conda/Brew/Nix builds (auto-installs tools).     |
| `bump`            | Bump version (VERSION=X.Y.Z or PART=major\|minor\|patch) and update changelog. |
| `bump-major`      | Increment major version ((X+1).0.0).                                           |
| `bump-minor`      | Increment minor version (X.Y.Z → X.(Y+1).0).                                   |
| `bump-patch`      | Increment patch version (X.Y.Z → X.Y.(Z+1)).                                   |
| `clean`           | Remove caches, coverage, and build artifacts (includes `dist/` and `build/`).  |
| `dev`             | Install package with dev extras.                                               |
| `help`            | Show this table.                                                               |
| `install`         | Editable install.                                                              |
| `menu`            | Interactive TUI menu (make menu).                                              |
| `push`            | Commit changes once and push to GitHub (no CI monitoring).                     |
| `release`         | Tag vX.Y.Z, push, run gh release if available.                              |
| `run`             | Run module entry (`python -m ... --help`).                                     |
| `test`            | Lint, format, type-check, run tests with coverage, upload to Codecov.          |
| `version-current` | Print current version from `pyproject.toml`.                                   |


## Coding Style & Naming Conventions
  - apply python_clean_code.md

## Commit & Pull Request Guidelines

## Architecture Overview
  - apply python_clean_architecture.md

## Security & Configuration Tips
- `.env` is only for local tooling (CodeCov tokens, etc.); do not commit secrets.
- Rich logging should sanitize payloads before rendering once implemented.

## Translations (Docs)

## Translations (App UI Strings)

## Changes in WEB Documentation
- when asked to update documentation - only do that in the english docs under /website/docs because other languages will be translated automatically,
  unless stated otherwise by the user. In doubt - ask the user

## Changes in APP Strings
- when i18 strings are changed, only to that in sources/\_locales/en because other languages will be translated automatically,
  unless stated otherwise by the user. In doubt - ask the user

## commit/push/GitHub policy
- run "make test" before any push to avoid lint/test breakage.
- after push, monitor errors in the github actions and try to correct the errors

--- 

# ONLY ON USER REQEST !!!! : 

# 📘 Documentation Review & Enhancement Prompt

You are a **senior software developer specializing in code documentation and system design clarity**. Your task is to review, correct, and enhance all documentation (external and inline) across the codebase with the following principles and workflow.

---

## **Principles**

* Documentation should emphasize **WHY** and **WHAT**, not just **HOW**.
* All docs must align with the system’s design-level documentation in `docs/systemdesign/*`.
* Every module, function, dataclass, and constant should be documented with clear intent, expected use, and system relevance.
* Documentation must be **authoritative, consistent, and actionable** for developers, maintainers, and system designers.

---

## **Workflow Checklist**

### **Step 1 – System Alignment**

* [ ] For every feature, function, configuration, dataclass, and constant:

  * [ ] Verify alignment with `docs/systemdesign/*`.
  * [ ] Document it in `docs/systemdesign/module_reference.md` using the template in `systemprompts/self_documenting.md`.
  * [ ] Ensure consistent terminology and style with system docs.

---

### **Step 2 – Module-Level Documentation**

* [ ] At the top of each module, create or update a **header block** that:

  * [ ] States the **purpose and intention** of the module.
  * [ ] Outlines its **contents** (functions, classes, constants).
  * [ ] Explains how it connects to the **overall system design**.

---

### **Step 3 – Function Documentation**

For every function:

* [ ] Document **Why** it exists (its role in the system).
* [ ] Document **What** it does (conceptual description).
* [ ] Document **Inputs** (parameters, types, ranges, meaning).
* [ ] Document **Outputs** (return values, meaning, edge cases).
* [ ] Document **Side Effects** (state changes, I/O, mutations).
* [ ] Add or refine **doctests** that:

  * [ ] Demonstrate common use cases.
  * [ ] Cover edge cases.
  * [ ] Illustrate not just mechanics but **intent**.

---

### **Step 4 – Dataclasses & Structures**

* [ ] For each dataclass:

  * [ ] Document each field’s **expected value and type**.
  * [ ] Explain **why the field exists**.
  * [ ] Describe how it interacts with other parts of the system.

---

### **Step 5 – Constants & Magic Numbers**

* [ ] For each constant or magic number:

  * [ ] Explain **what it represents**.
  * [ ] Explain **why this value was chosen**.
  * [ ] Reference relevant standards, business rules, or domain logic.
  * [ ] Replace unexplained “magic numbers” with named constants if possible.

---

### **Step 6 – Corrections & Enhancements**

* [ ] Remove or rewrite **obsolete documentation**.
* [ ] Correct **inaccurate or unclear explanations**.
* [ ] Fill in **missing documentation**.
* [ ] Reframe overly technical notes to emphasize **intent and reasoning**.

---

## ✅ Definition of Done (DoD)

Documentation is considered **complete and high quality** when:

1. **System Consistency**: Every documented element aligns with `docs/systemdesign/*` and is included in `docs/systemdesign/module_reference.md`.
2. **Module Headers**: Each module has a clear header block with purpose, contents, and system role.
3. **Function Docs**: Every function has complete, accurate, and intent-driven documentation, including doctests for clarity and correctness.
4. **Dataclass Docs**: Every dataclass field is fully described with expected type, purpose, and relevance.
5. **Constants**: Every constant or magic number has a clear explanation or has been replaced with a meaningful named constant.
6. **Corrections**: All obsolete, unclear, or incorrect docs have been fixed.
7. **Completeness**: No feature, function, configuration, dataclass, or constant is left undocumented.
8. **Clarity**: Documentation emphasizes **WHY** and **WHAT**, making the codebase understandable without digging into implementation details.

---
