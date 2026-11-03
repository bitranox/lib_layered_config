# skill-writer checklist - python-layered-config (.env search owner check)

- [x] Change: the dotenv paragraph says every searched `.env` (in `start_dir`, its parents and the
      per-user path) must be owned by the effective user or root on Linux and macOS; any other file
      does not count as found, is passed over with a WARNING record `dotenv_skipped_foreign_owner`
      on the `lib_layered_config` logger (`record.context` holds `path` and `owner_uid`), and the
      search goes on; root passes over a user's own `.env`; only the owner is checked, never the
      mode; a symlink must pass for both the link and the file it points to; Windows has no
      check; `dotenv_path=` / `--env-file` has no owner check. Where: SKILL.md, ## Where config
      files live, the dotenv paragraph (reflowed to 100 columns, wording outside the new sentences
      unchanged).
- [x] Receipt held (skill_receipt.py start meta-skill-writer) before the first edit.
- [x] Mechanism claims checked against the code before probing: `DefaultDotEnvLoader.load` runs
      `_foreign_owner` on every candidate, the upward ones and the platform extras (the per-user
      path); `_foreign_owner` returns None on `sys.platform == "win32"`, reads
      `path.lstat().st_uid` and `path.stat().st_uid` (the link and its target) and trusts
      `owner_uid in {euid, 0}` for both; `_log_dotenv_skipped` calls
      `log_warn` with `path` and `owner_uid`, and `observability._emit` puts fields under
      `record.context`; `_load_explicit` has no owner check. Pinned by
      tests/adapters/test_dotenv_owner_check.py and tests/e2e/test_dotenv_foreign_owner.py.
- [x] RED as a text check: a quote-back against the pre-edit paragraph (`git show HEAD:...`), opus
      and haiku, four questions (foreign-owned /tmp/.env, root under sudo, foreign `dotenv_path`,
      mode 777). opus answered NONE for the owner, root and mode questions; haiku answered
      "loaded" for both owner questions from the text's silence and NONE for the mode. Both listed
      ownership, root and mode as gaps.
- [x] GREEN quote-back, opus and haiku, on the edited text plus Q5 (a foreign file below an own
      file): all five answered by quote, no NONE, all answers match the code.
- [x] GREEN Skill gaps triaged. Closed in the text: "first file it finds" next to "passed over" (a
      skipped file now "does not count as found"); where the warning appears (WARNING record on
      the `lib_layered_config` logger, `record.context` fields); symlinks.
      Declined: the per-user path (named in the table directly above the paragraph); an unreadable
      or malformed `.env` (covered at SKILL.md "A layer path that exists but cannot be read is a
      load error" and the `LayerLoadError` entry); ownership of the containing directory and
      setuid real-vs-effective uid (not checked by the code, `_foreign_owner` reads only the
      file's `st_uid` against `os.geteuid()`; out of scope); a root-owned `/tmp/.env` (decided by
      "or by root"); sudo keeping HOME for the per-user path (owned by the path-resolver rules,
      not this check).
- [x] Final re-probe (opus at effort medium, haiku) on the final text: Q1, Q5, a symlink planted
      by another user pointing at the reader's own file, and how a Python app notices the skip.
      Output summarised below.
- [x] GREEN diffed against RED both ways: RED's only quoted rule for an explicit path ("loads that
      one file with no search") is still in the text, extended with "and no owner check".
- [x] Tiers haiku and opus; three rounds (RED, GREEN, final), one cell per tier per round.
- [x] Width and fence check over the added lines: no line over 100 columns, no fence touched.
- [x] Description measured: unchanged (frontmatter not edited); frontmatter parses
      (`['description', 'name']`).
- [x] ASCII only, present tense; the version-history finder over the added lines found nothing;
      the address grep over the added lines found nothing.
- [x] Security scan: prose only; no secrets, hostnames, private paths or PII.
- [x] Plugin version bumped to 7.7.1 in .claude-plugin/plugin.json.

- [x] The final re-probe's symlink answer exposed a code defect, not a text gap: judged by the
      target alone, a link another user planted in a directory they control, pointing at a file the
      reader owns, was loaded. Fixed in the code (the link's own owner is checked too, RED test:
      a link to root-owned /etc/passwd seen as root was parsed and refused as malformed), and the
      text changed to "for a symlink, both the link and the file it points to".
- [x] Symlink re-probe (opus at effort medium, haiku) on that wording: a planted link to the
      reader's file, an own link to an own file, an own link to a foreign file. Both tiers: not
      loaded, loaded, not loaded, each by quote. Declined: a chain of links (the code checks the
      first link and the final target; intermediate links are an edge case this change does not
      cover); which uid `owner_uid` reports for a symlink (the link's first, then the target's,
      stated in the `_foreign_owner` docstring); creator versus owner (the same on POSIX).

## Final re-probe

Both tiers, text before the symlink change:

- Q1, a foreign-owned /tmp/.env: not loaded, quoting "So a `.env` another user put in `/tmp` is
  never loaded".
- Q5, a foreign /tmp/work/.env below an own /tmp/.env: /tmp/.env loads, quoting "Any other file
  does not count as found ... and the search goes on to the next candidate".
- Q7, how a Python app notices: a handler on the `lib_layered_config` logger, `record.context`
  `path`, quoting the WARNING record sentence. Remaining gap declined: whether the event name is
  the record's message (stated in the skill's logging paragraph, "Each record carries a `context`
  dict").

Symlink re-probe, final text: see the bullet above.
