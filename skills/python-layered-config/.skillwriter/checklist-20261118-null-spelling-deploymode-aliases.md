# skill-writer checklist - python-layered-config (null on the stored spelling, DeployMode, platform aliases)

- [x] Change: the coercion bullet says an environment or `.env` `null`/`none` is judged in the
      spelling a lower layer stored for the key, so `MY_APP___DB__DBPASSWORD=null` over a file's
      `dbPassword` stays `"null"`, and a key no lower layer holds is judged on its lowercase name and
      stored under it (`db.dbpassword`, None). The deploy paragraph says `dir_mode`/`file_mode` take an
      int or a `DeployMode` of the matching kind, and a wrong kind raises `DeployModeError` naming both,
      before anything is written. The resolver paragraph names the `platform=` aliases `deploy_config`
      takes (`posix`, `macos`, `mac`, `windows`, `win`, `wine`, any case).
- [x] Code checked against the installed library: `read_config` with `[a] dbPassword` and
      `DEMO___A__DBPASSWORD=null` gives `"null"` (tests/e2e/test_null_judged_on_stored_spelling.py);
      with no file key, `as_dict()["db"]` holds `dbpassword: None` and `get("db.dbPassword")` misses.
      `deploy_config(dir_mode=DeployMode(0o640, ModeKind.FILE))` raises
      `dir_mode: got a file mode (0o640); dir_mode takes a directory mode`;
      `dir_mode=DeployMode(0o750, ModeKind.DIRECTORY)` creates the directory at 0o750.
      `DefaultPathResolver(platform=...)` stores `macos`/`Darwin`/`mac` as `darwin`, `Windows`/`win`/
      `wine`/`WIN32` as `win32`, `posix`/`LINUX` as `linux`.
- [x] Decisions ledger: the marketplace copy has no ledger entries for this skill.
- [x] RED, opus and haiku, the pre-edit text: Q1 (env null over a file's `dbPassword`) answered None on
      both tiers, quoting "reads as the one word `dbpassword`, which is not sensitive, so the key becomes
      None" (now wrong); Q2 (`DeployMode` as `dir_mode`) NONE on both; Q3 (`platform="macos"`) "only
      `darwin` is named" on both. 0 of 6 cells answered correctly from the text.
- [x] GREEN, opus and haiku, the new text: Q1 `"null"` (and None with no stored key), Q2 the object is
      accepted and a wrong kind raises the quoted `DeployModeError`, Q3 `macos` and `Darwin` accepted;
      each with a direct quote. 6 of 6 cells correct.
- [x] Gaps the GREEN probes raised, settled: the stored spelling of a key no lower layer holds (closed:
      "judged on its lowercase name and stored under it: `db.dbpassword`"; re-probed on opus and haiku,
      both answered `db.dbpassword` = None with the quote). Declined as covered elsewhere in the skill:
      the full sensitive stem list and the word split (SKILL.md:423-425, "matched per word after
      splitting at `_`, `-`, `.`, whitespace and a change of case"); an unsafe int mode's refusal
      (SKILL.md:406, `DeployModeError` "an unsafe or malformed mode"); the Windows ProgramData root
      (the "Probing and testing an app built on it" section, SKILL.md:236-241); a `.env` key below an
      environment variable (the same "a lower layer stored" sentence covers it). Left unstated: what an
      unknown `platform=` value does (it is stored as given and not refused; the layout it then gets is
      not measured here).
- [x] Gaps the Q1 re-probe raised (opus and haiku, both correct with quotes), settled: how a
      `not_sensitive` path matches case (closed: "a path matches in any case, so `"db.dbPassword"`
      covers `db.dbpassword`", checked with `NotSensitiveKeys.of(["db.dbPassword"]).covers(["db",
      "dbpassword"])` -> True and the e2e test
      `test_a_declared_not_sensitive_camel_case_key_reads_null_as_none`). Declined: two stored
      spellings of one key in one table (exotic; the merge places the key as it came and logs
      `case_folded_key_ambiguous` naming both, application/merge.py:328-334); the slug-to-prefix rule
      (stated just above the bullet, SKILL.md:134-137); a warning that adding a file key changes how a
      variable reads (the two sentences state both cases side by side).
- [x] Quote-back of the closed `not_sensitive` gap, haiku: a declared `"db.dbPassword"` plus
      `MY_APP___DB__DBPASSWORD=null` answered None (correct, pinned by the e2e test above), quoting the
      any-case clause and the stored-spelling sentence. Its remaining gap, the combined case not
      spelled out in one sentence, is declined: it follows from the two quoted rules, as the probe
      showed.
- [x] Width and fence check over the added lines: no line over 100 columns, no split code span.
- [x] Version-history finder over the added lines: no hit.

Decisions: none - the sentences document existing library behaviour; no skill rule was chosen or
declined, so no ledger entry is added.
