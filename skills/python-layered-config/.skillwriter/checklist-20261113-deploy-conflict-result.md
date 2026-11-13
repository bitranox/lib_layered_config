# skill-writer checklist - python-layered-config (deploy CONFLICT result)

- [x] Change: the "Deploying and scaffolding" paragraph. The `.action.value` list gains
      `"conflict"`; new sentences say `"skipped"` means already byte-identical, `"conflict"` means
      the file differs and was left unchanged because no `force`, `batch` or `conflict_resolver=`
      decided, and that a resolver must return `DeployAction.OVERWRITTEN` or `DeployAction.KEPT`
      (anything else raises `ValidationError`). Tracks the fix "fix(deploy): report an undecided
      conflict as CONFLICT, refuse an unknown resolver answer".
- [x] Receipt held (skill_receipt.py start meta-skill-writer) before the edit. The skill has no
      decision ledger, so no rejected or removed decision applies.
- [x] RED, measured: tests/examples/test_deploy.py
      test_deploy_without_a_policy_reports_a_conflict_and_leaves_the_file and
      test_a_resolver_answer_other_than_overwritten_or_kept_is_refused (5 cases) pin the behaviour;
      mutation arms returning SKIPPED for the undecided case, and dropping the resolver check, are
      killed on the owed assertions.
- [x] RED, behavioural: given the pre-edit paragraph and a "print UPDATE NOT APPLIED only for a
      differing file" task, haiku keyed on `"skipped"` (also fires for an identical file), opus
      byte-compared the file itself and named the missing default outcome as a gap.
- [x] GREEN quote-back on the new paragraph, opus and haiku, two questions each (the missed-update
      check, and a resolver answering `DeployAction.SKIPPED`): both tiers keyed on `"conflict"` and
      answered that SKIPPED raises `ValidationError`, each by a direct quote. 2 tiers x 2 questions
      = 4 cells, all correct.
- [x] Gaps settled: the import path is shown elsewhere in the skill (`from lib_layered_config
      import ...`, and `DeployAction` is exported from the package root); "were earlier destinations
      written before a resolver raises" is declined: the resolver is consulted per destination, so
      an answer it gets wrong stops the deploy at that destination like any other per-destination
      error, and the skill does not promise more.
- [x] Width and fence check: added lines 86-100 characters, no fence touched; the sentence after
      the insertion (`Permission keywords: ...`) still reads correctly.
- [x] Security scan: prose only; no secrets, hostnames, private paths or PII.
- [x] Twin: plugins/bitranox/skills/coding-python-layered-config/SKILL.md in bitranox-skills holds
      the same body (diffed from line 4 on), committed with the marketplace step.
- [x] Decisions: none - a factual update to the library's current behaviour, pinned by the tests
      above; no choice about the skill's text is made.
