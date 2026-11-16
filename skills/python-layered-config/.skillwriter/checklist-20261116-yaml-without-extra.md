# skill-writer checklist - python-layered-config (a .yaml file without the yaml extra)

- [x] Change: the error list and the deploy paragraph. The `NotFoundError` bullet said a `.yaml`
      file without the `yaml` extra is an unavailable source; the loader now refuses it, so every
      read and deploy raises `LayerLoadError` naming the file and `lib_layered_config[yaml]`
      (measured: tests/e2e/test_yaml_without_pyyaml.py). The `LayerLoadError` bullet now lists the
      case and no longer says a deploy refuses every `.d` file that is not TOML; the deploy
      paragraph names the YAML case beside "does not parse". Closes QUALITY-REVIEW R5-F1.
- [x] Receipt held before the edit. The skill has no decision ledger (`skill_decisions.py show
      coding-python-layered-config` printed nothing), so no rejected or removed decision applies.
- [x] RED, haiku, pre-edit text: asked what `read_config` and `deploy_config` do with a
      `config.d/10-log.yaml` on a plain install, it found no deciding line and took the
      `NotFoundError` bullet's "unavailable" as the best reading (the file skipped), now false.
- [x] GREEN, opus and haiku, new text, same questions plus "how does the user fix it": both answer
      `LayerLoadError`, no config returned, nothing deployed, quoting the new sentences.
      2 tiers x 3 questions = 6 cells, all correct.
- [x] Gaps settled. Closed: the `LayerLoadError` bullet listed no missing-extra case, and its
      deploy clause ("a source or `.d` file that is not TOML") contradicted "a file in the
      source's `.d` may be any supported format" (measured: a valid `.d` JSON file and, with
      PyYAML, a valid `.d` YAML file both deploy, action `created`). Declined as covered elsewhere
      in the skill: the install command (SKILL.md lines 30-31), TOML and JSON needing no extra
      (line 30), a layer's `config.d/` being read (lines 164 and 321). Declined: quoting the exact
      message; the sentence names what it contains, and the CHANGELOG quotes it.
- [x] Re-probe on the final text, haiku: read of a `.d` YAML without the extra, deploy with a valid
      `.d` JSON, deploy with a valid `.d` YAML and the extra installed - all three correct, each
      with a quote; no new undecided gap.
- [x] Width and fence check: added lines at most 99 columns, no fence touched; the bullet after
      each insertion (`ValidationError`, "A missing source raises") still reads correctly.
- [x] Security scan: prose only; no secrets, hostnames, private paths or PII.
- [x] Twin: plugins/bitranox/skills/coding-python-layered-config/SKILL.md in bitranox-skills needs
      the same three edits, parked with the [70] marketplace commit.
- [x] Decisions: none - a factual correction to the library's current behaviour, measured above.
