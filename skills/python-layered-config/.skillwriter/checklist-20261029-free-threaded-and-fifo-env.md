# skill-writer checklist - python-layered-config (free-threaded install, FIFO .env)

- [x] Change: the Install section says rtoml/orjson are installed and used below Python 3.14, are
      the extras `rtoml`/`orjson` from 3.14, are never imported on a free-threaded interpreter, and
      that stdlib tomllib/json take over with one stated parity gap (TOML nested 81 or 82 levels).
      The dotenv section says `dotenv_path=` / `--env-file` reads a regular file, FIFO or device
      under the shared 10 MiB cap, a missing path is an empty layer, a directory is refused.
      Where: SKILL.md, ## Install; ## Where config files live, the dotenv paragraph.
- [x] Receipt held (skill_receipt.py start meta-skill-writer) before the first edit.
- [x] RED as a text check: a quote-back against the pre-edit text (`git show HEAD:...`), opus and
      haiku. Both quoted the old install comment "(via rtoml / orjson)" for the 3.14 question and
      answered NONE for free-threaded support, the extras, the FIFO and the missing path.
- [x] Mechanism claims checked against the code before probing: `select_codec` / `select_parser`
      never call the importer when free-threaded; `_load_explicit` refuses a directory and returns
      an empty layer for a missing path; `ensure_within_size_cap` refuses only `size > 10 MiB`, and
      both the structured loaders and the dotenv reader go through it.
- [x] GREEN quote-back, opus and haiku, against the edited text: all four questions answered with
      quotes, no NONE.
- [x] GREEN Skill gaps triaged. Closed in the text: "never imports them" stated outright; a plain
      3.14+ install leaves both out; the user's own `import orjson` re-enables the GIL too; the
      parity gap given as 81 or 82 levels; the cap boundary (10 MiB loads, more is refused) and
      that every config file shares it; the install comment names the version split. Declined:
      where `KEY` lands in the merged config (covered by the skill's `.env` key rule, "A `.env` key
      is the key path WITHOUT the prefix"); whether pip can build the extras on 3.14t (packaging,
      out of scope); how to force or detect the backend (no public API exists); reading a FIFO
      twice (read-time detail, out of scope).
- [x] Re-probe of the same questions plus the ones the fixes touched (own import, parity depth,
      cap boundary) on the revised text, opus and haiku: all seven answered by quote, no NONE.
      Gaps closed from it: a GIL build with the extras uses them; depths past 82 are refused by
      both; the cap boundary given in bytes. Declined: an extras-only-one mix (each backend is
      chosen independently, rare); the refusal type (covered by the skill's loader-refusal rule).
- [x] Final re-probe of the three questions those fixes touched on the final text, opus (effort
      medium) and haiku; output summarised below. No new undecided gap.
- [x] Quotes substring-checked with quotecheck against the skill dir (6 of 6 OK); a planted
      sentence absent from the text came back MISMATCH, so the check can fail.
- [x] GREEN diffed against RED both ways: RED's only quote (the install line and "loads that one
      file with no search") is still in the edited text, extended rather than replaced.
- [x] Tiers haiku and opus; three rounds (RED, GREEN, final), one cell per tier per round.
- [x] Description measured: unchanged (frontmatter not edited).
- [x] ASCII only, present tense; the version-history finder over the added lines found nothing.
- [x] Security scan: prose only; no secrets, hostnames, private paths or PII.
- [x] Plugin version bumped to 7.4.0 in .claude-plugin/plugin.json.

## Final re-probe

Both tiers, final text:

- Q1, 3.14 with the GIL plus `[rtoml,orjson]`: rtoml and orjson, quoting "(installed on a GIL
  build, they are used)".
- Q2, 81 and 90 levels: 81 is refused by rtoml and can load on tomllib; 90 is refused by both,
  quoting "deeper than 82, both refuse it".
- Q3, a FIFO of 10485760 and 10485761 bytes: the first loads, the second is refused, quoting
  "exactly 10 MiB (10485760 bytes) loads, one byte more is refused".

Remaining gaps, both declined:

- "can load" is hedged: deliberate, because whether 81 or 82 levels load depends on the nesting
  form (the data depth of 80 syntax levels is 80 to 82).
- How a level is counted: owned by the code's module docstring (`_toml_backend.py`), not the skill.

## Review-fix round (same day)

- [x] Edits: tomli on 3.14/3.14t; the TOML depth gap restated for the new bounds (single construct
      81 to 101 loads without rtoml; tables past 101 refused everywhere); never install the extras
      on a free-threaded build; a FIFO read waits for its writer with no timeout; a missing path is
      an empty layer in Python and a usage error (exit 2, measured) on the CLI.
- [x] Quote-back on the edited text, haiku and opus (effort medium), five questions: all answered
      by quote, no NONE except "is there a timeout" (now stated).
- [x] Gaps closed: tomli on 3.14t named; what installing the extras on a free-threaded build does;
      a writer that never closes blocks forever. Declined: how a level is counted (owned by the
      module docstring); "tables" vs each construct past 101 (the merge refuses every table past
      101); directory refusal detail and cap reach (covered elsewhere in the skill); two gaps that
      cited a stale CLAUDE.md view (the exit code was measured at 2).
- [x] ASCII only; SKILL.md paragraph reflowed at 100 columns.
- [x] Second review round: depth band corrected (header/inline 81-100, dotted up to 101 keys) and
      the array-of-tables direction added; haiku quote-back on the new sentence answered all three
      depth questions by quote. Its "3.14 GIL backend unstated" gap is answered by the rest of the
      paragraph (the excerpt was cut).
