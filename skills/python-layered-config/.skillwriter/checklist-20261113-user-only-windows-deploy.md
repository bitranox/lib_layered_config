# skill-writer checklist - python-layered-config (user-only Windows deploy)

- [x] Change: the isolation bullet in "Probing and testing an app built on it". The sentence saying
      a test on Linux or macOS that forces the Windows layout with neither ProgramData variable set
      raises now names the `app` or `host` target, and a new sentence says a `user`-only deploy
      needs no ProgramData root and no variable at all (the APPDATA and LOCALAPPDATA defaults sit
      under the home directory). Tracks the fix "fix(deploy): a user-only Windows deploy needs no
      ProgramData root again".
- [x] Receipt held (skill_receipt.py start meta-skill-writer) before the edit. Step 0b: the skill
      has no decision ledger, so no rejected or removed decision applies.
- [x] RED, measured: under `env -i` with only `LIB_LAYERED_CONFIG_APPDATA` set,
      `deploy_config(..., targets=["user"], platform="win32")` returns CREATED and writes nothing
      into the cwd, while `targets=["app"]` raises `LayerRootNotAbsoluteError` (a
      `ValidationError`); with only `HOME` set the user-only deploy lands under
      `<home>/AppData/Local/...` (APPDATA directory missing, LOCALAPPDATA fallback). The old
      sentence claimed the user-only call raises.
- [x] RED, behavioural: given the pre-edit paragraph and the user-only question, opus and haiku
      both quoted the old sentence and answered "raises" (wrong).
- [x] GREEN quote-back on the new paragraph, opus and haiku, three questions each (user-only with
      APPDATA set, `app` target as the over-trigger control, user-only with no variable): both
      tiers answered deploys / raises / deploys, each by a direct quote of the new text. 2 tiers x
      3 questions = 6 cells, all correct.
- [x] Gaps settled: "must an APPDATA override exist" is covered by the next bullet ("A Windows
      user-layer deploy whose `%APPDATA%` directory does not exist writes under ..."); "where an
      unset APPDATA writes" and "which override names APPDATA" are covered in the same paragraph
      ("point `HOME`, `XDG_CONFIG_HOME`, `APPDATA`, `LOCALAPPDATA` and the
      `LIB_LAYERED_CONFIG_*` roots above into that temp directory"); `targets=["user", "app"]` is
      decided by "for the `app` or `host` target", measured: `LayerRootNotAbsoluteError`, no file
      written; whether a user-only deploy resolves ProgramData internally is declined (no caller
      effect).
- [x] Width and fence check over the added lines printed nothing; the paragraph after the
      insertion point (the `%APPDATA%`-missing bullet) still reads correctly after it.
- [x] Security scan: prose only; no secrets, hostnames, private paths or PII.
- [x] Twin: plugins/bitranox/skills/coding-python-layered-config/SKILL.md in bitranox-skills holds
      the same body (diffed from line 4 on), committed with the marketplace step.
- [x] Decisions: none - a factual correction to the library's current behaviour, which
      tests/adapters/test_windows_roots_absolute.py pins; no choice about the skill's text is made.
