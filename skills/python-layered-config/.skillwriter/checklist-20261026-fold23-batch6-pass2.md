# skill-writer checklist - coding-python-layered-config (memory rules folded in)

- [x] Rule: Know that an unquoted digit-only .env or environment value (the sensitive-key rule
      does not protect numbers) arrives as an int and makes a pydantic str field fail with
      string_type; put ConfigDict(coerce_numbers_to_str=True) on one shared base for all section
      models rather than quoting single values, and pin it with a test that loads a real .env
      through the loader and asserts the raw value is an int before parsing.
      Where: SKILL.md, ## Environment-variable overrides (the trap), value-coercion bullets: new bullet
      after 'A number converts only when it reads back as the same text', plus a clause on the
      sensitive-key bullet
- [x] Receipt held (the coordinator ran skill_receipt.py start meta-skill-writer); every editing
      agent loaded the skill through the Skill tool before its first edit.
- [x] RED as a text check: an opus quote-back against a pre-edit snapshot of the skill. The rules
      under test are recorded in this machine's memory store, so a behavioural arm would be
      contaminated; only a verbatim quote from the snapshot counts.
- [x] GREEN quote-back on haiku and opus against the edited files (5 questions), again after the
      review fixes for every question, and a third time for the 3 questions the fix-delta fixes
      touched: every answer quoted the edited text, no NONE. Quotes were substring-checked against
      the files; the pre-edit snapshots fail the same check.
- [x] GREEN diffed against RED both ways: every partial RED quote is still in the edited text.
- [x] Tiers haiku and opus, one cell per question per tier per round.
- [x] Independent review of the full diff, then of the fix delta alone; every finding fixed or
      declined with evidence by the fixer, and the fix delta re-reviewed.
- [x] Each GREEN Skill gaps list triaged: 5 closed in the text, 10 declined with a reason (covered
      elsewhere with file:line, out of scope, owned by another skill, or a judgement the skill
      leaves open).
- [x] Description measured: unchanged (frontmatter not edited).
- [x] ASCII only, present tense, tables canonical (reformat_tables.py --check --strict), added
      prose wrapped like the surrounding text, no code span split across lines.
- [x] Security scan: prose only; no secrets, hostnames, private paths or PII; addresses are
      documentation ranges or placeholders.
