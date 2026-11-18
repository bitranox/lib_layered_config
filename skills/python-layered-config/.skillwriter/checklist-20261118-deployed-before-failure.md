# skill-writer checklist - python-layered-config (deployed_before_failure)

- [x] Change: the deploy paragraph says targets are written one after another, in the order
      `targets` lists them, so a deploy that fails part-way has written the earlier ones; it raises
      the original exception unchanged, and `deployed_before_failure(error)` (exported from
      `lib_layered_config`) returns the `DeployResult`s already written, in write order (a `.d` copy
      in its main file's `.dot_d_results`), or `[]` for an error that carries none.
- [x] Found by tfbpr step 8b's skill-surface check: `deployed_before_failure` is in `__all__` (since
      8.1.0, `__init__.py:51` at v8.1.0) and was the one exported callable the skill did not name;
      after this edit the check prints `none`.
- [x] Code checked: `deployed_before_failure(ValueError("x"))` returns `[]`; the docstring states write
      order and the `.d` placement; docs/python-api.md "Partial failure" says the same.
- [x] Decisions ledger: only d-20261116-ba9d51da is rejected/removed, unrelated to this edit.
- [x] RED, opus and haiku, the text without the sentence, scenario: a two-target deploy raised
      PermissionError at the app target. Opus answered NONE for both questions; haiku guessed
      `generated_before_failure` (the generate helper) for a deploy and flagged the guess. 0 of 4
      cells answered from the text.
- [x] GREEN, opus and haiku, the new text: both wrote `except PermissionError as error:` with
      `deployed_before_failure(error)` from `lib_layered_config`, and both answered `[]` for an error
      raised before any write. 4 of 4 cells correct.
- [x] Gaps the GREEN probes raised, settled: write order tied to the `targets` list (closed, "in the
      order `targets` lists them"). Declined as covered elsewhere in the skill: the path attribute
      (`.destination` in the same paragraph's `DeployResult` field list), the import of
      `deploy_config` (the paragraph's own `deploy_config(...)` example and the root exports), that
      `slug=` is a `deploy_config` parameter (same example). Declined as out of scope: which error
      types carry results (any exception `deploy_config` raised after a write does; the docstring
      owns that).
- [x] Width check: the new lines are at most 99 columns.

Decisions: none - the sentence documents an existing public function; no skill rule was chosen or
declined, so no ledger entry is added.
