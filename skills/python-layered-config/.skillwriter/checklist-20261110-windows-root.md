# skill-writer checklist - python-layered-config (Windows ProgramData root)

- [x] Change: the isolation bullet in "Probing and testing an app built on it". The sentence
      "Setting the OS variable `PROGRAMDATA` instead does nothing ... the lookup misses" is false
      since the case-insensitive Windows variable lookup; it now says the OS `ProgramData` (any
      case) moves the Windows app root, `LIB_LAYERED_CONFIG_PROGRAMDATA` wins over it, and every
      Windows root must be absolute (a relative one, or the built-in `C:\ProgramData` under a
      forced Windows layout on Linux/macOS, raises `lib_layered_config.ValidationError` before
      anything is read or written).
- [x] Receipt held (skill_receipt.py start meta-skill-writer) before the first edit.
- [x] RED as a text check and a probe: both copies held the stale sentence (1 hit each) and no
      absolute-root rule (0 hits). A subprocess `deploy_config(..., platform="win32")` under
      `env -i` with only `PROGRAMDATA`, `ProgramData` or `programdata` set wrote under that
      directory each time, refuting the sentence.
- [x] Claims measured: the override beats `PROGRAMDATA` (deploy_config_paths lands under the
      override); a relative `LIB_LAYERED_CONFIG_APPDATA` makes `read_deploy_config(...,
      platform="win32")` raise a bare `ValidationError` (no cause); with neither variable set the
      deploy raises and the working directory stays empty. `read_config` wraps only
      `InvalidFormatError` (core.py), so a Windows read passes the `ValidationError` through too:
      argued from the code, not run on Windows.
- [x] GREEN quote-back (opus and haiku), five questions on the edited paragraph: both answered the
      three questions the paragraph is for (any-case OS variable, override precedence, the forced
      Windows layout is refused and writes nothing) by quote. Gaps closed: which API forces the
      layout (now `deploy_config(..., platform="win32")`, `deploy --platform windows`) and where
      `ValidationError` comes from (now `lib_layered_config.ValidationError`). Declined: the
      `LIB_LAYERED_CONFIG_APPDATA` question (the excerpt omitted the root list a few lines above,
      which names it); the CLI exit code (22 on POSIX, 87 on Windows; left to cli-reference, as in
      the review-batch round).
- [x] Width and fence check over the added lines: no line over 100 columns, ASCII only, no fence
      touched.
- [x] Security scan: prose only; no secrets, hostnames, private paths or PII.
- [x] Twin: plugins/bitranox/skills/coding-python-layered-config/SKILL.md in bitranox-skills holds
      the same body (diffed from line 4 on), committed with the marketplace step.
- [x] Plugin version: 7.7.1 in .claude-plugin/plugin.json, not yet pushed, so this change rides on
      it.
