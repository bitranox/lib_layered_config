# skill-writer checklist - python-layered-config (docs and skill audit fixes)

- [x] Change: destination_for takes a layer name (ValidationError for env/unknown); --json envelope;
      flag rows --default-file, --start-dir (read, read-json), --format/--provenance (read); a
      declared not_sensitive table still masks sensitive keys below it; provenance entries need
      exactly layer/path/key with key = own dotted key; redact_mapping takes any Mapping;
      display_config never wraps; deploy directory modes; relative root override scoped to the
      platform whose layout uses it; SourceInfo exported.
- [x] Code checked against the working tree (scripts in this directory: probe_code*.py):
      premises 1, 3, 4, 5, 6, 7, 9, 10 hold. "app"/"User" resolve, Layer.ENV and "nope" raise
      ValidationError "Unsupported deployment target: ..."; provenance key "host" for "db.host"
      raises "key must be 'db.host', its own key in the provenance", a missing or extra field
      raises "must have exactly the keys layer, path and key"; not_sensitive=["features"] still
      masks pass_through, token and inner.password; redact_mapping accepts a Config and a
      MappingProxyType; read --format human at COLUMNS=40 printed a 158-column line, and
      display_config output parsed with tomllib (longest line 209); a relative
      LIB_LAYERED_CONFIG_ETC raises for platform linux and is ignored for darwin, a relative
      MAC_APP_ROOT or MAC_HOME_ROOT raises for darwin and is ignored for linux;
      `from lib_layered_config import SourceInfo` works.
- [x] Premise 8 was WRONG as written ("a directory that already existed keeps its mode"):
      a pre-existing ~/.config/demo and config.d at 0775 both became 0700 after a user deploy,
      while ~/.config above them kept 0775 (deploy.py _prepare_directory docstring; docs/
      cli-reference.md:774-776). CORRECTED IN THE SKILL BY MAIN: the directory a file goes into
      gets the mode even when it existed, created parents get it, existing parents keep theirs,
      a symlinked directory is skipped.
- [x] Premise 2 was imprecise: the failure envelope is {ok, command, error}, with no skipped
      (cli/envelope.py:5-6; a real `read --bogus --json` run). CORRECTED IN THE SKILL BY MAIN.
- [x] Further finding: redact_mapping(config) does NOT read the Config's own declaration; a
      Config built with NotSensitiveKeys.of(["f.pass_through"]) came back masked from
      redact_mapping(config), while config.as_dict(redact=True) showed it. Fix F3 below.
- [x] Decisions ledger: not read (probe ran outside the marketplace repo).
- [x] RED, opus and haiku, pre-edit text excerpt, 10 user-task questions: 0 of 20 cells correct
      for the new behaviour (Q1 KeyError, Q2 failure shape not stated, Q3 no flags, Q4 "both
      shown", Q5 key field not stated, Q6 "plain dict", Q7 not stated, Q8 not stated / 0775,
      Q9 "raises", Q10 NONE). opus Q10 guessed SourceInfo from the commit subject in its injected
      git status (marked GUESS, not counted).
- [x] GREEN, opus and haiku, new text excerpt: 16 of 20 cells correct with direct quotes, e.g. Q1
      "from 9.0.2 the name works too in any case", Q4 "keys below a declared table are still
      judged by name (`token` under it stays masked)", Q5 "`key` being its own dotted key".
      Wrong on both tiers, both caused by the text: Q2 kept skipped on failure (quoting "on
      failure `error` replaces `data`"), Q8 answered "keeps 0775" (quoting "a directory that
      already existed keeps its mode"). Both premises are now corrected by main (above).
- [x] Quote-back on haiku of the proposed F1-F3 wording: 3 of 3 correct with quotes (failure keys
      ok, command, error; redact_mapping(cfg) masks the declared path, use not_sensitive= or
      as_dict(redact=True); ~/.config 0775, ~/.config/demo 0700, config.d 0700). Not re-probed
      on main's applied wording.
- [x] Gaps settled: ValidationError's module declined as covered elsewhere (SKILL.md:242
      "lib_layered_config.ValidationError", SKILL.md:412). Declined: strict-clean string to Layer
      conversion (both tiers answered Q1 correctly without it); which platform each root variable
      belongs to (both tiers answered Q9 correctly; optional F6). Excerpt-only gaps from the
      quote-back (table header, sensitive name list, user layer root) declined as covered in the
      full skill.
- [x] Width and fence check over the added lines: no prose line over 100 columns, no split code
      span, ASCII only; the re-padded table rows are 167 columns (table rows exempt).
- [x] Version-history finder: 3 hits in the new text, 0 in the old (lines 81, 550, 568: "from
      9.0.2", "8.1.0 to 9.0.1", "up to 9.0.1"), against "Describe the latest release only";
      9.0.2 is unreleased (pyproject 9.0.1, last tag v9.0.1). Fix F5.
- [x] Stale count: "Three details decide whether that lands" (line 103) now introduces 4 bullets.
      Fix F4.

- [x] Fixes applied by main after the probe: F3 (redact_mapping does not read a Config's own
      declaration; pass not_sensitive again or use as_dict(redact=True), checked with a Config
      built with NotSensitiveKeys.of(["f.pass_through"])), F4 ("Four details"), F5 (no version
      numbers left in the skill: grep for 9.0.x and 8.1.0 finds none). F6 declined: Q9 was
      answered correctly on both tiers without it. Two added lines over 100 columns re-wrapped.
- [x] Quote-back on haiku of main's applied wording (failure envelope, directory modes,
      redact_mapping on a Config): 3 of 3 correct with quotes - failure keys ok, command,
      error; ~/.config/demo 0o700, config.d 0o700, ~/.config keeps 0775; redact_mapping(cfg)
      does not apply the declaration, pass not_sensitive again or use cfg.as_dict(redact=True).

Decisions: none - the sentences document existing library behaviour; no skill rule was chosen or
declined, so no ledger entry is added.
