# skill-writer checklist - python-layered-config (Step 7 re-score text corrections)

- [x] Change: five corrections the [50] Step 7 re-score found stale or missing, each checked against the
      code at master 9df9d0e before writing it (scratchpad probes, not committed):
      1. An empty or relative `LIB_LAYERED_CONFIG_ETC`, `_MAC_APP_ROOT` or `_MAC_HOME_ROOT` raises
         `LayerRootNotAbsoluteError` (a `ValidationError`) on a read and a deploy; a relative
         `XDG_CONFIG_HOME` is ignored. The `ValidationError` bullet now names that subclass.
      2. `DeployDestinationError` also covers an uncreatable destination (a file where a directory
         belongs, no directory above it); `GenerateDestinationError` is the same refusal for examples.
      3. `HomeDirectoryUnknownError` (also a `RuntimeError`) added to the error list: deploy and
         `deploy_config_paths` raise it for the user target, a read skips the user layer.
      4. The `url` example was false: a URL's password in a string value is masked under any key by
         `redact_mapping` and every `redact=True` view. The example is now a bare secret under `conn`.
      5. A part-way generate failure re-raises unchanged; `generated_before_failure(error)` returns the
         files already written as `list[Path]`, for both generate functions.
- [x] Receipt held before the edit. `skill_decisions.py show coding-python-layered-config` (installed
      plugin copy with `--skill-dir`, the twin worktree predates the tool) listed two
      deploy-conflict-precedence entries; neither touches these passages.
- [x] RED, opus, pre-edit text (four questions): Q1 WRONG (quoted "is masked by neither" and said
      `redact=True` leaves hunter2 visible), Q2-Q4 NONE.
- [x] GREEN, opus and haiku, new text, same four questions: 2 tiers x 4 = 8 cells correct, each quoting
      the new sentence.
- [x] Gaps settled. Closed from the GREEN gaps: read and deploy alike for the root rule; which views
      mask a URL password; `LayerRootNotAbsoluteError` in the `ValidationError` bullet; the return type
      of `generated_before_failure` and that it serves both functions. Declined as covered elsewhere in
      the skill: how an app masks its own keys (the paragraph's "Mask by KEY" and the one-arm-per-shape
      test rule), import paths (every name these passages use is in `lib_layered_config.__all__`,
      checked at 9df9d0e). Declined as out of scope: which file was mid-write when the disk filled.
- [x] Re-probe on the final text, opus (effort medium) and haiku, four new questions (to_json view,
      the except clause for an empty ETC, `conn = "hunter2"`, the return type): 8 of 8 correct.
- [x] Width and fence check on the added lines: none over 100 columns, fences balanced, no history
      phrasing, no private path.
- [x] Decisions: d-20261117-a4802b60, d-20261117-57885dcd, d-20261117-55fb1ecc, d-20261117-fa29426e,
      d-20261117-df8571dc (rule, measured).
- [x] Mirror: twin `coding-python-layered-config/SKILL.md` differs from this copy only in `name:`.
