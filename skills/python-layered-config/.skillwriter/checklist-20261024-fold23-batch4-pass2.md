# skill-writer checklist - coding-python-layered-config (memory rules folded in)

- [x] Change: Per-OS config paths (Notes paragraph rewritten) + new section '## Probing and testing
      an app built on it' (bullets 2 and 3) + one sentence in 'Python API beyond read_config' /
      Deploying - coding-python-layered-config/SKILL.md. RED on the pre-edit snapshot: partial.
      Verified: Deploy fallback -> lib_layered_config
      src/lib_layered_config/examples/deploy.py:558-563 (`if "LIB_LAYERED_CONFIG_APPDATA" not in
      self.resolver.env and kind_or_raise(appdata_root) is PathKind.MISSING: chosen_root =
      self._localappdata_root()`); LOCALAPPDATA root and LIB_LAYERED_CONFIG_LOCALAPPDATA ->
      deploy.py:536-545. Read-side fallback only when roaming holds no config ->
      adapters/path_resolvers/_windows.py user_paths (`roaming_paths =
      list(collect_layer(roaming_base)); if roaming_paths: ... return`, then local_base). Root env
      vars exist -> grep of src:
      LIB_LAYERED_CONFIG_APPDATA/_ETC/_LOCALAPPDATA/_MAC_APP_ROOT/_MAC_HOME_ROOT/_PROGRAMDATA.
      Configured modes not read on Windows -> domain/permissions.py modes_apply() `return os.name ==
      "posix"`; examples/deploy.py:348 `if request.modes_decided or not modes_apply(): return given
      if given is not None else DeployPermissions.defaults()` (load() never called). Explicit modes
      validated on every platform -> deploy.py:260-272 _explicit_modes raises DeployModeError;
      permission_overrides parsed on every call -> deploy.py _mode_request docstring 'checked here
      on every call and platform' + parse_deploy_permissions(...). CLI --dir-mode refused via
      click.BadParameter -> cli/deploy.py:37-46. The lib's own CLI has no --set (consumer CLIs map
      --set to permission_overrides, matching the skill's existing Common mistakes row), so worded
      as 'what an app's --set passes'. Library version 7.3.0 (pyproject.toml:3).
- [x] Dropped as stale or unverified: Version tag 7.1.9 and the WindowsDeployment._user_path name
      (current class name not cited). 'An unsafe --dir-mode 777 exits 22': UNVERIFIED - the CLI
      raises click.BadParameter (cli/deploy.py:46), whose exit code depends on the consumer's exit
      mapping, so only 'validated on every platform' is kept. Private names (a Windows test VM,
      lsdsk _point_appdata_at, os_posix/os_windows marker names, dated CI measurement) dropped as
      private/history. Reconciled existing line 'Modes are never applied on Windows.' in the API
      section with the new rule (extended, not contradicted).
- [x] Change: Per-OS config paths (new paragraph after Notes) + new section '## Probing and testing
      an app built on it' (bullet 1) - coding-python-layered-config/SKILL.md. RED on the pre-edit
      snapshot: partial. Verified: Upward search from start_dir or cwd -> adapters/dotenv/default.py
      _iter_candidates: `base = Path(start_dir) if start_dir else current_directory()`; `for
      directory in [base, *base.parents]: yield directory / ".env"` (a relative Path('x').parents is
      [Path('.')], i.e. the cwd). Search list = upward candidates then platform extras, first FILE
      wins -> default.py _build_search_list `[*list(_iter_candidates(start_dir)), *extras]` and
      load() returns on first match. dotenv_path loads one file with no search -> default.py load():
      `if dotenv_path is not None: return self._load_explicit(Path(dotenv_path))`. CLI --env-file
      maps to dotenv_path and 'skips upward directory search' -> cli/read.py --env-file option
      ('dotenv_path'). Redact -> domain/config.py:137 `def as_dict(self, *, redact: bool = False)`
      and :167 `def to_json(..., redact: bool = False)`. Root variables -> grep of src for
      LIB_LAYERED_CONFIG_* names.
- [x] Dropped as stale or unverified: Private specifics dropped: CODECOV_TOKEN/PYPI_API_TOKEN names
      (generalised to 'upload tokens, passwords'), the finanzonline-uid incident, the owner's stance
      on token rotation, dates, and the full env -i pytest recipe with private app prefixes
      (condensed to the isolation rule). The 'filter run output to FAILED/passed lines' tip dropped
      as incidental. Noted separately (not edited, outside live_skill_dir): docstring at
      adapters/dotenv/default.py _iter_candidates says 'none when there is no start' while the code
      falls back to the cwd.
- [x] Review A F6 fixed: a RELATIVE start_dir is not resolved, so the .env search ends at the
      current directory (_iter_candidates uses Path(start_dir).parents; reviewer probe).
- [x] Receipt held (the coordinator ran skill_receipt.py start meta-skill-writer); every editing
      agent loaded the skill through the Skill tool before its first edit.
- [x] RED as a text check: an opus quote-back against a pre-edit snapshot of the skill. Only a
      verbatim quote from the snapshot counts, so context inherited from this machine cannot
      satisfy it; redcheck --corpus-cascade was not run.
- [x] GREEN quote-back on haiku and opus against the edited files: every scenario after the edit,
      every scenario again after the first review's fixes, then the scenarios each later fix
      touched. Every answer was a quote from the new text on both tiers in every round; no NONE.
      Quotes were checked against the files (6-word windows; misses traced to line wraps,
      markup and line-number prefixes).
- [x] GREEN diffed against RED both ways: every partial RED quote is still in the edited text.
- [x] Tiers haiku and opus, one cell per scenario per tier per round.
- [x] Independent review of the full diff, then a review of each fix delta alone; every finding
      fixed or declined above. Each GREEN reply's Skill gaps list was read; gaps not listed
      here asked for detail the rule does not need (out of scope) or were answered elsewhere in
      the skill.
- [x] Description measured: unchanged (frontmatter not edited).
- [x] ASCII only, present tense (history finder clean on the added lines), tables canonical
      (reformat_tables.py --check --strict), every fence closes, added prose wrapped at 100
      columns except where the file keeps one line per paragraph or list item.
- [x] Security scan: prose only; no secrets, hostnames, private paths or PII; values added are
      option names, commands, source file paths or reserved examples.
