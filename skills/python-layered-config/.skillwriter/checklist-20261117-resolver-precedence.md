# skill-writer checklist - python-layered-config (force and batch decide before conflict_resolver)

- [x] Change: the deploy paragraph now says `force` (overwrite) and `batch` (keep) decide a
      differing file first, so with either set the resolver is never called, and that otherwise it
      is asked once per differing destination, each differing `.d` copy included. Code:
      deploy.py `_handle_conflict` checks force, then batch, then the resolver; `.d` copies go
      through `_deploy_single` with the same resolver. Pinned by
      tests/examples/test_deploy.py::test_force_or_batch_decides_and_the_resolver_is_never_called
      (a mutation that lets the resolver override force fails it). Closes QUALITY-REVIEW R5-F6.
      Two "(N.N.N and later)" history markers in bold leads were removed while editing.
- [x] Receipt held before the edit. `skill_decisions.py show coding-python-layered-config` printed
      no entries, so no rejected or removed decision applied.
- [x] redcheck --corpus-cascade on the scenario: clean (1997 documents); no CLAUDE.md on the chain
      mentions `conflict_resolver`.
- [x] RED, opus and haiku, pre-edit text, scenario `force=True` plus an auditing resolver: both
      quoted NONE. Opus answered "cannot tell" (0, 3 or a refusal all consistent with the text);
      haiku answered 0 and labelled it an inference from the list of deciders.
- [x] GREEN, opus and haiku, new text, same scenario plus `batch=True`: both answered 0 entries and
      quoted "`force` (overwrite) and `batch` (keep) decide first: with either set, the resolver
      is never called". 2 tiers x 3 questions = 6 cells, all correct.
- [x] Gaps settled. Closed: how often the resolver is asked without force or batch, `.d` copies
      included (the sentence added above). Declined as covered elsewhere in the skill: the action a
      `batch` file gets and force plus batch together (SKILL.md "`force=True` backs up and
      overwrites ... both at once raise `ValidationError`"), a byte-identical file under force
      (`"skipped"` means the file was already byte-identical; deploy.py `_execute_action` returns
      SKIPPED), that a deploy copies the `.d` directory ("a non-config file (a `README.md`) is
      copied unparsed"; `deploy_config_paths`). Declined as decided: a warning or refusal for a
      resolver passed with force or batch (ledger, rejected). Declined as out of scope: call order
      across files.
- [x] Re-probe on the final text, opus (effort medium) and haiku: no force, config.toml plus two of
      four `.d` files differ - both answered 3 calls; with force - both answered 0; each quoted the
      governing sentences verbatim. No new undecided gap.
- [x] Width and fence check over the added lines printed nothing; the sentence after the insertion
      ("Permission keywords") still reads correctly.
- [x] Security scan: prose only; no secrets, hostnames, private paths or PII.
- [x] Twin: plugins/bitranox/skills/coding-python-layered-config/SKILL.md in bitranox-skills carries
      the same edits (diff shows only the `name:` line), parked with the [70] marketplace commit.
- [x] Decisions: d-20261116-f5a520ab, d-20261116-ba9d51da
