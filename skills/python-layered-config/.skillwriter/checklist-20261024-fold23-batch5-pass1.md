# skill-writer checklist - coding-python-layered-config (memory rules folded in)

- [x] Change: ## Where a setting comes from (provenance) - the 'To label the layer `cli` instead'
      list (now 'Three details') and the 'Assert it end to end' paragraph -
      coding-python-layered-config/SKILL.md. RED on the pre-edit snapshot: partial. Verified: Config
      third field defaults to NONE -> lib_layered_config 7.3.0
      src/lib_layered_config/domain/config.py:92 `_not_sensitive: NotSensitiveKeys =
      field(default=NotSensitiveKeys.NONE, ...)`; Config accepts it positionally as third arg ->
      config.py:102 TypeError text "Config's third argument must be a NotSensitiveKeys ... use
      NotSensitiveKeys.of([...])" and doctest config.py:158 `Config({...}, {},
      NotSensitiveKeys.of([...]))`; redaction uses it -> config.py:164; with_overrides carries it ->
      config.py:290 `return Config(merged, _override_provenance(...), self._not_sensitive)`;
      NotSensitiveKeys.of exists -> domain/redaction.py:139, NONE = empty -> redaction.py:191;
      read_config builds it from not_sensitive -> core.py:133; exported publicly ->
      __init__.py:61,86. Section-plus-key_path and override-layer parts already in skill (lines
      71-96), matching the body. 'value that differs from every file layer' comes from the body's
      How-to-apply (procedural, not a measurement).
- [x] Dropped as stale or unverified: Nothing stale in the body. Did not carry the body's mention of
      the private `_not_sensitive` field (internal detail, the default-NONE fact is what the reader
      needs).
- [x] Review C: the twin under the lib_layered_config repo got the same change by three-way merge;
      repo-gate --mirrors reports the pair in sync.
- [x] Gaps declined: code for rebuilding the provenance map (the rule names the method, the keys and
      the trailing argument; a loop shape is detail the rule does not need).
- [x] Receipt held (the coordinator ran skill_receipt.py start meta-skill-writer); every editing
      agent loaded the skill through the Skill tool before its first edit.
- [x] RED as a text check: an opus quote-back against a pre-edit snapshot of the skill. Only a
      verbatim quote from the snapshot counts, so context inherited from this machine cannot
      satisfy it; redcheck --corpus-cascade was not run.
- [x] GREEN quote-back on haiku and opus against the edited files: every scenario after the edit,
      then the scenarios each review fix touched (6 after the first review, 1 after the second).
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
