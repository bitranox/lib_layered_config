# skill-writer checklist - coding-python-layered-config (memory rules folded in)

- [x] Change: ## Probing and testing an app built on it - first bullet, appended to the 'To isolate
      a run from every deployed layer' sentence - coding-python-layered-config/SKILL.md. RED on the
      pre-edit snapshot: partial. Verified: lib_layered_config pyproject.toml:3 version = "7.3.0".
      Linux root -> adapters/path_resolvers/_linux.py:44,58
      'self.ctx.env.get("LIB_LAYERED_CONFIG_ETC", "/etc")'. macOS -> _macos.py:40
      'self.ctx.env.get("LIB_LAYERED_CONFIG_MAC_APP_ROOT", default_root)'. Windows ->
      _windows.py:51-52 '"LIB_LAYERED_CONFIG_PROGRAMDATA", self.ctx.env.get("ProgramData",
      r"C:\ProgramData")'. Plain dict copy -> default.py:92 'self.env = {**os.environ, **(env or
      {})}'. Windows key upper-casing -> CPython os._create_environ_mapping on nt: 'def
      encodekey(key): return encode(key).upper()' (python3 inspect probe). `<SLUG>___` env prefix
      notation already used in the skill's per-OS table. Twin identical before edit (diff -r: only
      name field). Existing text already covered HOME/XDG_CONFIG_HOME/APPDATA/LOCALAPPDATA, so only
      the missing part was added.
- [x] Dropped as stale or unverified: Private a private consumer test file names and dated review
      history dropped. The body's exact dict.fromkeys(... tmp_path / 'etc') snippet not carried (the
      skill already says to point the roots into the temp directory); version-history '7.0.1,
      unchanged in 7.3.0' wording dropped.
- [x] GREEN gap fixed: the isolation sentence says to set all six roots and names the three app
      roots as the ones a partial setup misses.
- [x] Receipt held (the coordinator ran skill_receipt.py start meta-skill-writer); every editing
      agent loaded the skill through the Skill tool before its first edit.
- [x] RED as a text check: an opus quote-back against a pre-edit snapshot of the skill. Only a
      verbatim quote from the snapshot counts, so context inherited from this machine cannot
      satisfy it; redcheck --corpus-cascade was not run.
- [x] GREEN quote-back on haiku and opus against the edited files: every scenario after the edit,
      then the scenarios each review fix touched (9 after the first review, 1 after the second).
      Every answer was a quote from the new text on both tiers in every round; no NONE. Quotes
      were checked against the files; misses traced to line wraps and the arm's own commentary.
- [x] GREEN diffed against RED both ways: every partial RED quote is still in the edited text.
- [x] Tiers haiku and opus, one cell per scenario per tier per round.
- [x] Independent review of the full diff in three slices, then a review of each fix delta alone;
      every finding fixed or declined above. Each GREEN reply's Skill gaps list was read; gaps
      not listed here asked for detail the rule does not need or were answered elsewhere in the
      skill.
- [x] Description measured: unchanged (frontmatter not edited).
- [x] ASCII only, present tense (history wording absent from the added lines), tables canonical
      (reformat_tables.py --check --strict), every fence closes, added prose wrapped at 100
      columns, no code span split across lines.
- [x] Security scan: prose only; no secrets, hostnames, private paths or PII; values added are
      option names, commands, source file paths or reserved examples.
