# skill-writer checklist - python-layered-config (code-quality review batch)

- [x] Change: brings the skill in line with the review fixes since 6183106 (d5fc062, 7674f15,
      b09b3d8, 2347870, 43e6a31, 50b19f1, 313931d, 3a7f9b7) plus a peer session's two notes.
      Where: the description (adds writing a `.env` for a config section); the slug bullet (letters
      of either case, `.`, `-`, `_`, refused never rewritten); `.env` key case and
      `CAL_STORE__HOST=h1`; `--profile` on read/read-json/deploy; `read`/`read-json` mask by
      default, `--no-redact` shows values; the deploy table row (a `.toml` source); the
      `destination_for` paragraph (`DefaultPathResolver` keywords, `Layer` members, `"app"` works
      at runtime but fails pyright strict, `Layer.ENV` raises `KeyError`, never `None`); the Errors
      paragraph; `PermissionProblem` and its `.source`; `--force --batch` exit 2; the `.d` format
      rule; the module line "unless a line names another module"; two history lines removed.
- [x] Receipt held (skill_receipt.py start meta-skill-writer) before the first edit.
- [x] Mechanism claims checked against the code before probing: `destination_for` per layer, the
      string and `Layer.ENV` arms and the `DefaultPathResolver` signature (p33/probe.py);
      `.env` nesting and key case, slug acceptance, `read_config_json` redact default (facts.py);
      pyright strict on `destination_for("app")` and the `None` guard (typed.py);
      `PermissionProblem.source` is `str | None` from `_source` (file path, else layer name) and
      `OVERRIDE_SOURCE = "override"`; `validate_identifier` accepts `My-App`, refuses `_x`.
- [x] Exception chain measured, not read: an unreadable user `config.toml` gives `LayerLoadError`
      -> `__cause__` `InvalidFormatError` -> `__cause__` `PermissionError`; a broken TOML file gives
      `LayerLoadError` -> `InvalidFormatError` with no `OSError` in the chain.
- [x] RED as a text check against the pre-batch text (`git show 6183106:...`): 0 hits for
      `destination_for`, `DEFAULT_USER_FILE_MODE`, `REDACTED_PLACEHOLDER`, `PermissionProblem`, the
      empty-segment rule, the `.toml`-source rule and `no-redact`; 1 hit for the stale "slug is
      normalized" line; description 401 characters without the `.env` trigger.
- [x] GREEN quote-back (opus and haiku), 13 questions on the edited text: answered by quote, with
      four gaps, all closed before the REFACTOR round: what `destination_for("app")` does at
      runtime (it works; only pyright fails it), the letter case of a `.env` key and an underscored
      section (`CAL_STORE__HOST=h1`, case-insensitive), the import line for the exported constants
      ("unless a line names another module"), and which slugs are refused (the character set).
- [x] REFACTOR re-probe (opus and haiku), 12 questions. Both found a contradiction the edit had
      introduced: the Errors paragraph said OS errors reach the caller as themselves, while the
      systemd section says `read_config` raises `LayerLoadError` for an unreadable layer. Fixed:
      `read_config*` wraps it (follow `__cause__` to the `OSError`), `deploy_config` passes
      `FileNotFoundError`/`PermissionError` through.
      Closed in the text: slug "ASCII letters of either case"; `.source` form and type; a broken
      `.d` file raises `LayerLoadError` and blocks the whole deploy (measured in
      tests/examples/test_deploy_source_parse.py); `LayerLoadError` named as a deploy error too.
      Declined: the symlink-destination CLI exit code (ValueError maps to 22 on POSIX, 87 on
      Windows; not worth a platform table here); `--json` against `--format json` (flag detail
      belongs to `--help`); a symlinked parent directory (the user never ruled on it, so the text
      stays silent); yaml extra at deploy time and the CLI exit for a yaml source (unmeasured,
      not added); the table's `--force`/`--batch` slash (they are alternatives, so the slash is
      right); naming vendor/app/slug as required (the signature line already shows them).
- [x] Final re-probe (opus, haiku) on the touched passages, five questions (unreadable file under
      read_config, unreadable deploy source, slug case, broken `.d` file, `.source`): both tiers
      answered all five correctly by quote. Remaining gaps closed: which link holds the
      `PermissionError` (`__cause__`, two links down), the `.d` exception named outright, the
      deploy `LayerLoadError` in the subclass list, `.source` is a `str`. Declined: the ProtectHome
      fix and the slug-to-prefix mapping (both in sections the excerpt left out); the missing-home
      wording (the systemd section's sandbox sentence explains it).
- [x] GREEN diffed against RED both ways: no rule RED quoted was dropped; the "slug is normalized"
      sentence was wrong and is replaced.
- [x] Tiers haiku and opus; four rounds (RED text check, GREEN, REFACTOR, final).
- [x] Width and fence check over the added lines: no prose line over 100 columns (table rows and
      the frontmatter excepted), no fence touched.
- [x] Description measured: 473 characters, under the 500 target; frontmatter parses
      (`['description', 'name']`).
- [x] ASCII only, present tense; the version-history finder found the "Before 5.7.0" lines, now
      removed; the address grep found only `127.0.0.1:1`, a deliberate closed-port example.
- [x] Security scan: prose only; no secrets, hostnames, private paths or PII.
- [x] Twin: plugins/bitranox/skills/coding-python-layered-config/SKILL.md in bitranox-skills holds
      the same body (diffed from line 4 on), committed with the marketplace step.
- [x] Plugin version: 7.7.1 in .claude-plugin/plugin.json, not yet pushed, so this change rides on
      it; the coming major release bump rewrites it.
