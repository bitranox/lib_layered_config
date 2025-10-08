# Test Matrix

This matrix links each test suite to the architectural responsibilities
documented in `module_reference.md`. It should stay in sync with the fixtures in
`tests/support` and with the public API guarantees.

| Suite | Focus | Key Modules | Notes |
|-------|-------|-------------|-------|
| `tests/unit` | Domain and pure functions | `lib_layered_config.domain.*`, `observability` | Validates immutability, provenance helpers, and logging utilities without hitting I/O boundaries. |
| `tests/application` | Merge policy and functional invariants | `lib_layered_config.application.merge` | Uses property tests to ensure associativity, precedence, and metadata stability. |
| `tests/adapters` | Adapter contracts and boundary coercion | `lib_layered_config.adapters.*` | Contract tests rely on `tests.support.layered` to keep platform-specific scaffolding declarative. |
| `tests/examples` | Example helpers and deployment tooling | `lib_layered_config.examples` | Ensures generated artefacts and deployment flows match documented filesystem layouts. |
| `tests/e2e` | Composition root and CLI behaviour | `lib_layered_config.core`, `lib_layered_config.cli` | Exercised via end-to-end scenarios; notebook execution is marked `slow`. |
| `tests/e2e/test_notebooks.py` | Documentation parity | `notebooks/Quickstart.ipynb` | Executes notebook cells (skipped on macOS because of path leakage) to ensure tutorials stay in sync. |

When adding a new feature, update this matrix and the relevant module reference
entry so test intent stays visible to readers and reviewers.
