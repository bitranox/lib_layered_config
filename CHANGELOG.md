# Changelog

All notable changes to lib_layered_config

This project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Security
- A deploy into a layer directory that is a symbolic link no longer changes the mode of the directory it
  links to. With `~/.config/myapp` linked to a shared 0755 directory, deploy set that directory to 0700 (and on
  the app and host layers could widen a 0750 one to 0755). The file is still written through the link with
  its mode; the target directory keeps its own, and the skip is logged as `deploy_directory_mode_skipped`.
- Redaction masks more secrets. Keys named `pwd`, `pass`, `privatekey`, `privkey` or `bearer` (`smtp_pass`,
  `db_pwd`, `auth_bearer`, `smtpPass`) came back in clear from `as_dict(redact=True)`, `to_json(redact=True)`,
  `get_redacted` and the display; they are now masked like `password`. A value that is a URL with a password
  (`postgres://alice:hunter2@db/app` under `db.url` or any other key) now shows as
  `postgres://alice:***REDACTED***@db/app`, also when the user name holds an `@` or the password an unencoded
  `/`, `?`, `#` or `@` (`postgresql://app:Ab/9+x@db/prod`); an `@` in the query leaves the host shown. A key
  that only looks secret, such as `pass_through`, is masked too;
  declare it with `read_config(not_sensitive=[...])` to keep it visible.
- On Windows, a deploy that replaces a file keeps the file's access list. A forced or confirmed deploy
  writes a new file and renames it over the old one, and backs the old one up with a copy; on Windows a
  new file takes the access list its directory passes down, so a `config.toml` restricted to its user
  with `icacls /inheritance:r` or `Set-Acl` came back readable by everyone the directory lets in
  (SYSTEM, Administrators, and any group the directory grants), and so did its `.bak`. The replaced
  file's DACL, protected or inherited as it was, now goes onto the new file, the `.bak` and the `.ucf`
  sidecar as soon as each is created, before any content is written into it. The owner is not copied. A file deployed for the first time still takes its directory's
  access list, and a volume without access lists (FAT, exFAT) is unchanged.
- A deploy's `.bak` is never readable more widely than the file it backs up. On Linux and macOS the
  backup was created at the umask's mode (`0o644` under the usual `0o022`) and took the file's mode
  only after its content was copied, so another user could open the backup of an owner-only
  `config.toml` in that moment and keep reading it afterwards. The backup is now written owner-only
  and renamed into place, then takes the file's mode, times and extended attributes.
- `deploy` refuses a destination that is a symbolic link, dangling or not, with
  `DeployDestinationError` (a `ValidationError`): `"<path> is a symbolic link; deploy neither writes
  through nor replaces one"`, one line per link, `.d` copies included, before anything is written. Before,
  `--no-permissions` (and every deploy on Windows, which sets no modes) wrote through the link and
  overwrote the file it pointed at, while with permissions on the link was replaced by a regular file. A
  dangling link at `config.toml.bak` or `.ucf` counted as a free name, so the backup was written through
  it; any existing name now counts as taken.
- `deploy` refuses a destination that is not a regular file (a directory, FIFO, device or socket) the
  same way: `"<path> is not a regular file; deploy writes only regular files"`. A FIFO there made deploy
  block forever while comparing contents.
- Redaction recognises a secret whatever the key's spelling: words are split at `_`, `-`, `.`,
  whitespace and a change of case before the name rule runs, so `dbPassword`, `DBPassword`,
  `clientSecret`, `accessToken`, `client-secret` and `api-key` are masked like `db_password`.
  Before, only underscore-separated names matched, and `to_json(redact=True)`, `read --redact`,
  `read_config_json(redact=True)` and the display view printed camelCase and kebab-case secrets in
  clear. The same rule now masks the camelCase form of every name it already masked, such as
  `primaryKey` or `cacheKey` (like `primary_key`); exempt such a path with `not_sensitive`.
  `key`, `keyBinding`, `hotkey` and `tokenizer` stay visible.
- The `.env` search passes over a file that neither the current user nor root owns, logs the
  warning `dotenv_skipped_foreign_owner` with its path and owner uid, and goes on searching. The
  search climbs every parent directory up to `/`, so a `.env` another user put in a shared directory
  such as `/tmp` was loaded by every program started below it, and as the dotenv layer it outranked
  the app, host and user files. A symlinked `.env` must pass for both the link and the file it
  points to, so a link another user planted is passed over even when it points at a file you own.
  Only ownership is checked, not the mode, so a group- or
  world-writable `.env` you own still loads. A process running as root now passes over a `.env`
  owned by an ordinary user (under `sudo` in a project directory, say); pass it as `dotenv_path`
  (CLI `--env-file`), which loads the named file whoever owns it. Windows is unchanged.

### Changed
- `env-prefix` prints a note on stderr when the prefix is not a name a POSIX shell can `export`, which a dot
  in the slug (`my.app` gives `MY.APP___`) or a leading digit (`2app` gives `2APP___`) causes. The prefix
  itself, stdout and the `--json` data are unchanged, and such variables are still read; the note says to
  set them with env(1) or a container's or service's environment, or to use a slug that starts with a
  letter.
- `deploy_config` called with neither `force`, `batch` nor a `conflict_resolver` now reports a file
  whose content differs as `DeployAction.CONFLICT` (new member, value `"conflict"`) and leaves it
  unchanged, as before. It was reported as `SKIPPED`, which the documentation reserves for a file that is
  already byte-identical to the source, so a caller reading the results could not tell a missed update
  from one that was not needed. A `conflict_resolver` that returns anything other than
  `DeployAction.OVERWRITTEN` or `DeployAction.KEPT` now raises `ValidationError` naming the two, and
  nothing is written for that destination; before, such an answer was also reported as `SKIPPED`. The
  `deploy` command is unaffected: it always resolves a conflict by `--force`, `--batch` or its prompt.
- `lib_layered_config.application.merge.LayerSnapshot` takes a `Layer` member and raises `TypeError` for
  anything else, naming the new `LayerSnapshot.of(name, payload, origin)`, which accepts a member or its
  plain name (the form `Config.origin(...)["layer"]` returns). Before, the constructor converted a string
  although its field was declared `Layer`.
- `deploy --force --batch` is a usage error (exit code 2): "--force overwrites an existing file and
  --batch keeps it; pass one", and `deploy_config(force=True, batch=True)` raises `ValidationError`, both
  before anything is written. Before, `--force` won silently, so a script that added `--batch` to stay
  non-destructive still overwrote (measured with the CLI and the Python API).
- **Breaking:** `lib_layered_config read` (both formats, `--json` included) and `read-json` mask
  sensitive values (`password`, `token`, `secret`, `*_key` and the other redaction patterns) as
  `***REDACTED***` by default; `--no-redact` prints them. Before, they printed in clear unless
  `--redact` was given, so a `read` pasted into a ticket or run in a CI log showed every password, while
  the Python `display_config` already masked them. A script that reads a secret through `read-json`
  must add `--no-redact`; without it the value reads `***REDACTED***` and the command still exits 0.
- An environment or `.env` key with an empty segment - a leading, trailing or doubled `__` - fails the
  load with `LayerLoadError` naming the variable (never its value), and so does a `.env` line whose key
  or value holds a NUL. Before, such a key was placed under an empty name: the typo `APP___A__=1`
  replaced a configured `a = 5` with `{"a": {"": 1}}`, and `APP___DB____PORT=1` left `db.port`
  unchanged while adding `db[""].port`. A `.env` line `=1` (an empty key) is refused too. A variable
  named only the prefix (`APP___`) is still skipped, and control characters other than NUL are kept.
- `deploy` copies and compares every file a chunk at a time, so its memory no longer grows with file
  size: a 200 MiB file in the source's `.d` directory deployed at 231 MB peak RSS and now at 28 MB, the
  same as a small one (measured with the CLI).
- Reading a configuration or `.env` file no longer allocates the whole 10 MiB size cap: a 4-byte `.env`
  took 10.6 MB transiently, now about its own size. The structured loaders read through the same capped
  reader as `.env` files, so a file that grows after its size was checked cannot pass the cap.
- `validate_identifier`, `validate_vendor_app` and `validate_hostname` in
  `lib_layered_config.domain.identifiers` are no longer wrapped in `functools.lru_cache`, so they
  have no `cache_info()` / `cache_clear()`. Measured, the cache saved under 1% of a `read_config`
  call (about 1.6 us of 190 us). Results are unchanged.

### Added
- `deployed_before_failure(error)`, exported, returns the `DeployResult` items a `deploy_config` call
  wrote before it raised `error`, in the order written (`[]` for an error no deploy raised). The deploy
  still raises the same exception; the results ride on it. A `--force` overwrite whose new content
  fails to write (a full disk, a size limit) leaves no unnamed `.bak`: when the destination is still the
  old file, the backup is removed; when a rewrite in place stopped part-way, the backup is the only whole
  copy, so it stays and is listed as an `overwritten` result with its `backup_path`.
- `deploy --json` puts a `written` list into the failure envelope's `error` object when a deploy stops
  after writing something: every path it created, overwrote, backed up (`.bak`) or kept as `.ucf`, in
  write order. The field is absent when nothing was written, so the other envelopes are unchanged.
  An interrupt (Ctrl-C at the conflict prompt, SIGINT) prints no envelope; under `--json` too, the
  files it had written are then named on stderr (`deploy stopped after writing:`), as without it.
- `generated_before_failure(error)`, exported, returns the example paths a `generate_examples` (or
  `generate_examples_report`) call wrote before it raised `error`, in write order (`[]` for an error no
  run raised), as `deployed_before_failure` does for a deploy. `generate-examples` names them on stderr
  (`generate-examples stopped after writing:`) before the error, and `--json` puts them into the
  failure envelope as `error.written`, absent when nothing was written. Before, a run that failed
  part-way named none of the examples it had already written.
- `GenerateDestinationError`, a `ValidationError` raised by `generate_examples` and `generate-examples`
  for an example path it would write through (see Fixed).
- `HomeDirectoryUnknownError` and `LayerRootNotAbsoluteError` can be imported from `lib_layered_config`,
  so a caller can catch the no-home and relative-root refusals the documentation describes.
- Every CLI command accepts `--json`, which prints one JSON document on stdout instead of the normal
  output: `{"ok": true, "command", "data", "skipped"}` on success and
  `{"ok": false, "command", "error": {"type", "message", "exit_code"}}` on failure, with the same exit
  code the command returns without the flag. Before, a failure printed only a message on stderr, and
  `info` and `env-prefix` had no machine-readable output. `deploy --json` lists every result section,
  empty ones included, `generate-examples --json` puts the files it wrote under `created` and the
  existing ones it kept (no `--force`) under `skipped`, and `read --json` / `read-json --json` always put `{"config", "provenance"}` in
  `data`, with `provenance` set to `null` under `--no-provenance`. A usage error in the arguments (a missing option, a path that does not exist,
  an unknown option) prints the envelope too, with exit code 2; only an unknown command keeps Click's
  usage text. Output without `--json` is unchanged.
- `MergeResult` (what `read_config_raw` returns), `DeployResult` and `DeployAction` (what
  `deploy_config` returns) are importable from `lib_layered_config`.
- `lib_layered_config.generate.generate_examples_report` runs `generate_examples` and returns an
  `ExamplesReport` naming the files it wrote (`created`) and the existing ones it kept (`kept`).

### Deprecated
- `lib_layered_config.examples` moved: `deploy_config`, `deploy_config_paths`, `read_deploy_config`,
  `DeployAction`, `DeployResult` and the deployment strategies now live in `lib_layered_config.deploy`,
  and `generate_examples` with its plan and spec types in `lib_layered_config.generate`. The root package
  still exports `deploy_config`, `deploy_config_paths`, `read_deploy_config`, `DeployAction`,
  `DeployResult` and `generate_examples`, as before. The old paths
  (`lib_layered_config.examples`, `.examples.deploy`, `.examples.generate`) still work and re-export the
  same objects, but importing them raises a `DeprecationWarning`; they are removed in the next major
  release.
- `prefer` on `read_config`, `read_config_json` and `read_config_raw`, and `--prefer` on `read` and
  `read-json`, never changed what was loaded: each layer reads only `config.toml` and its `config.d/`
  directory, so there was no second main file for the suffix ranking to choose. Passing `prefer` now
  raises a `DeprecationWarning`, and `--prefer` prints a warning on stderr; JSON and YAML files go in
  `config.d/`. Both are removed in a future major release. The docs no longer describe a format
  preference.

### Removed
- `lib_layered_config.observability.log_error`: nothing in the library called it, and it was never
  exported from the package root. The remaining helpers (`log_debug`, `log_info`, `log_warn`) and
  `make_event` type their structured fields as `object` instead of `Any`; callers pass the same values.
- The `allow_dots` keyword of `lib_layered_config.domain.identifiers.validate_path_segment`. Despite
  its name it skipped the whole character check (`allow_dots=True` accepted `a+b`, `a@b`, `a b`), while
  dots pass without it. Nothing passed it; the function now always applies the strict pattern.
- `lib_layered_config.adapters._nested_keys.ensure_child_mapping`, a private helper nothing called
  since nested-key placement moved to its case index.

### Fixed
- A `Config` is now immutable below its top level too. `config["db"]["host"] = ...`, an `append` to a list
  read with `config.get(...)`, or a change to the mapping the `Config` was built from used to change what
  every later read returned. The `Config` now owns a deep copy and hands out a copy of each nested table,
  list or provenance record, of the same type, so `json.dumps(config["db"])` and `isinstance(..., dict)`
  keep working.
- `"db" in config` answers from the keys instead of reading `config["db"]`, so it no longer copies the
  whole table to say yes or no. `config.get("db.host")` no longer checks every key of each table it
  passes (a lookup in a table of 128 000 keys took about 120 times as long as in one of 1 000). A
  `Config` built by hand from a table holding a non-string key now finds that table's string keys
  through `get`, where it used to return the default.
- `copy.deepcopy`, `copy.copy` and `pickle` of a `Config` used to raise `cannot pickle 'mappingproxy'
  object`; they now work and keep its provenance and declared `not_sensitive` paths.
- A relative home directory (`HOME=rel` on Linux and macOS, a relative `USERPROFILE` on Windows) is refused
  with `LayerRootNotAbsoluteError` naming that variable, as a relative `LIB_LAYERED_CONFIG_ETC` is. Before,
  the Linux and macOS user layer, and a deploy to it, resolved under the current directory.
- A command whose stdout reader went away (`lib_layered_config info | head -0`) exits with 141 and
  prints nothing. It exited 1, or 120 with an "Exception ignored ... BrokenPipeError" line. A command
  that fails on its own keeps its exit code, unless `--json` sends its failure envelope to the gone
  reader, which also exits 141. The
  fix is in `lib_cli_exit_tools` 2.5.0, now the lowest version this package accepts.
- A refused vendor, app, slug or hostname is named with each control character written as `\uXXXX`
  (`slug contains invalid characters: demo\u000a`). It was printed raw, so a trailing newline was
  invisible and an ESC sequence reached the terminal. A value without control characters is named as
  before.
- A deploy that fails partway (a declined or unanswerable conflict prompt, a permission wall on a
  later target or `.d` file) no longer hides the files it already wrote. Targets are written in the
  order given, so `--target user --target app` with a conflict at `app` left the user file deployed
  while the error, and the `--json` envelope, named nothing written. The CLI now prints
  `deploy stopped after writing:` and one path per line on stderr before the error; the exit code and
  the error message are unchanged.
- `generate_examples` and `generate-examples` no longer write through a link or wait on a FIFO at an
  example path. With `force` (`--force`) a FIFO there blocked the run forever, a symbolic link made it
  overwrite the file the link pointed at, outside the destination, and a directory ended it with a bare
  `IsADirectoryError`; without `force` a symbolic link to nothing made it create the file the link
  pointed at. Such paths are now refused with `GenerateDestinationError`, one line per path, before
  anything is written: with `force`, every symbolic link and every path that is not a regular file;
  without it, only a link that resolves to nothing, while anything else already there is kept as
  before. A refusal exits 22 (87 on Windows). An example is now written as `deploy_config` writes with
  permission setting off: through a temporary file renamed into place, so a failed write leaves the
  old file, except that a file with other hard links, another owner or its own extended attributes is
  rewritten in place.
- An environment variable or `.env` key nested deeper than the merge allows (more than 100 `__`
  levels) is refused before it is built. The loader used to build the whole nested table for such a key
  and only then hand it to the merge, which refused it: a 3 MB `.env` holding one key of a million
  segments peaked at about 290 MB in 7.7.0 before the refusal, and now at about 50 MB, the import
  included. The refusal is the `LayerLoadError` described under the nesting-depth entry, and a key of
  101 segments, the deepest the merge accepts, is still loaded.
- `Config.with_overrides` takes time linear in the dots of a key's name (a quoted TOML key such as
  `"a.a.a" = 1`). It cut the name before every dot, so a key with 16,000 dots took 0.5 s; it now takes
  no measurable time.
- `display_config` no longer fails on a stdout that cannot encode a value. A piped stdout on Windows uses
  the cp1252 code page, and a CJK character or an emoji made the JSON view exit with nothing printed and
  the human view stop part-way with `UnicodeEncodeError` (this reached every CLI built from the CLI
  template through its `config` command). It now writes such a character as the CLI's `read` does:
  `\uXXXX` in JSON, which parses back to the same value, and a Python backslash escape in the human
  view; output on a stream that can encode everything is unchanged byte for byte. A `console` passed in
  by the caller is written to as it is.
- JSON output works under a config directory whose name is not valid UTF-8. On Linux a file name is
  bytes, and a path holding a byte that is not UTF-8 (a Latin-1 `x<0xFF>y`) in provenance, a deploy result
  or an error message made `read_config_json`, `Config.to_json` and every CLI `--json` output fail with
  `TypeError: str is not valid UTF-8`: exit 22, often with nothing on stdout, a broken file reported as
  that TypeError instead of its `LayerLoadError`, and `deploy --json` wrote its files and then printed
  nothing. Such a byte is now written as the four characters `\xff` (the byte on disk), on both JSON
  backends; text that is valid UTF-8 is written as before.
- A machine hostname no longer stops an application from reading its configuration. The host layer reads
  `hosts/<hostname>.toml`, and a hostname outside ASCII letters, digits, `-` and `.` (`build_agent_01`, a
  non-ASCII name, a Windows reserved name such as `con`) made every read and every deploy raise
  `ValidationError`, even with no host file anywhere. `_` is now allowed, so `build_agent_01` reads
  `hosts/build_agent_01.toml`. Any other refused machine hostname turns off only the host layer: reads skip
  it and log the warning `host_layer_skipped_invalid_hostname`, and a deploy to the `host` target still
  raises `ValidationError` with the same message, before anything is written; other targets deploy.
- A YAML configuration file on a host without PyYAML (it ships only in the `yaml` extra) is refused:
  every read and deploy raises `LayerLoadError` with `"<path> is YAML, which needs PyYAML: install it
  with pip install 'lib_layered_config[yaml]'"`. It used to be skipped without a word, so a `.yaml`
  `default_file` or a `.yaml` file in a `config.d/` silently did not apply, and `deploy` installed a
  `.d` YAML file nothing had parsed. A YAML file that is not there is still skipped, as before.
- `--traceback` works in the installed `lib_layered_config` and `lib-layered-config` commands. It worked
  only through `python -m lib_layered_config`: the console scripts start the CLI without passing the
  arguments on, so the flag, looked up in those arguments beforehand, was never found. The root command now
  sets it itself.
- `deploy_config` (and `deploy_config_paths`, `read_deploy_config`) says what a source that is not a
  regular file is: `"Configuration source is a directory, not a file: <path>"`, or `"Configuration source is
  not a regular file: <path>"` for a FIFO, device or socket. Both used to read `"Configuration source not
  found"`, as a missing path still does. The exception is still `FileNotFoundError`, so the CLI exit code
  (2) is unchanged.
- On a platform without a layout of its own (a `sys.platform` that is neither Linux, macOS nor
  Windows: FreeBSD, Solaris, Cygwin) the reader now uses the Linux layout, the one `deploy` already
  wrote there. Before, it read no app, host or user file at all, so a file `deploy` had just written was
  never read back. `platform_family` returns `PlatformFamily.LINUX` for such a value instead of `None`.
- A slug, vendor, app or hostname ending in a newline (`"demo\n"`) is refused with `ValidationError`
  (`"slug contains invalid characters: ..."`), as one ending in `\r` already was. Before, a single trailing
  newline passed the check, so `read_config` loaded it and `deploy_config` wrote into a directory named
  `demo` plus a newline. A profile was already refused (control characters).
- `default_env_prefix(slug)` and `lib_layered_config env-prefix` refuse a slug that `read_config`,
  `deploy_config` and `generate_examples` refuse, with the same `ValidationError` message (a usage error,
  exit code 2, in the CLI). In 7.7.0 neither refused any slug, so `env-prefix ../x` printed `../X___`
  with exit 0 while `read --slug ../x` and `deploy --slug ../x` exited 22, and `"a b"`, `"x/y"` and
  `".hidden"` got prefixes no read accepts.
- The CLI prints an error message up to 4000 characters without `--traceback`; it cut every message at
  500 ("... [TRUNCATED at 500 characters]"). A deploy refusing a configured mode names each problem
  with its source and then the hint "to deploy anyway, give both --dir-mode and --file-mode ...", about
  290 characters on its own, so one refused mode with an ordinary home path already lost the hint's
  end, and two lost the second source and the whole hint. The new `--json` envelope carries the whole message.
- Configuration nested more than 100 tables deep - a JSON or YAML file 101 to 253 levels deep, or an
  environment or `.env` key with more than 100 `__` segments - is refused by `read_config`,
  `read_config_json` and `read_config_raw` as `LayerLoadError` naming where:
  `"<path>: configuration nesting exceeds the maximum depth of 100 at a.a.a..."` (`environment:` for an
  environment key), the key path cut after 80 characters. Before, it was a bare `InvalidFormatError`
  ("Configuration nesting exceeds the maximum depth of 100") naming no file, variable or key, and code
  catching `LayerLoadError` for read failures missed it. Both are `ConfigError`, so `except ConfigError`
  is unaffected; the CLI exits 1 as before. The deploy's read already reported it as `LayerLoadError`
  and now names the source too.
- `Config.get_redacted(key)` walks only the key's path and redacts only its value. Before, every call
  built the whole `as_dict(redact=True)` copy first, so one call took 12.6 ms on a 10 000-key
  configuration and 46 ms on a 40 000-key one, and asking for each key in turn grew with the square of
  the configuration's size; a leaf now costs about what `get` does (under 20 us measured), and the
  answer is unchanged. The redaction depth limit (300 levels) now applies to the key's own path and
  value only: on a `Config` built in Python with a value nested deeper than that, another key is
  returned instead of refused (no read can produce such a config; the loaders refuse it first).
  New `lib_layered_config.domain.redaction.redact_value_at(path, value, not_sensitive=...)` does the
  walk.
- Reading configuration (`read_config`, `read_config_json`, `read_config_raw`, and the read a deploy
  makes for its modes) no longer holds every parsed file until the last one is parsed: each file is
  parsed, merged and dropped before the next, so peak memory stays near the merged result plus one file
  however many files the layers hold. Measured with `.d` files of about 2.2 MB setting the same keys:
  1, 10 and 40 files peaked at 21, 88 and 315 MB traced before, and at 21, 37 and 37 MB now. A file that
  does not load is still reported as `LayerLoadError`, naming it; the debug event `layer_loaded` with an
  app, host or user layer's file count is now logged after that layer's files rather than before.
- A `.d` directory's files are read and deployed in the order of their exact names on every OS (digits,
  then upper case, then lower case). Before, Windows ordered them ignoring case while Linux and macOS
  did not, so `Z.toml` and `a-extra.toml` setting the same key gave a different winner per host. On
  Windows, a `.d` directory mixing upper- and lower-case names now merges in the Linux and macOS order.
- A deploy with permission setting off (`--no-permissions`, `set_permissions=False`, or a configured
  `enabled = false`) no longer leaves a torn file when a write fails half-way (a full disk, a size
  limit): it writes a temp file beside the destination and renames it into place, as the default path
  already did, so the destination is the old file or the whole new one. Before, the file was rewritten
  through its own inode, and a failed overwrite cut the live config short. The new file keeps the old
  one's mode; a destination a rename would change - other hard links, another owner or group than a
  new file gets, not writable, or extended attributes (a POSIX ACL, an SELinux label) that differ from
  a new file's - is still rewritten in place. A backup whose copy fails is removed instead of being
  left half-written beside the destination.
- The CLI shows the library's warnings: each one is printed on stderr as one
  `warning: <event> key=value ...` line while a command runs, in every output mode, so stdout and the
  `--json` envelope are unchanged; a control character in a key or path is written as `\uXXXX`, so a
  newline cannot split the line and an ESC sequence cannot reach the terminal (the paths after
  `deploy stopped after writing:` are escaped the same way). Before, the warnings went to a logger with
  only a `NullHandler`, so
  a CLI user never saw a passed-over `.env` another user owns (`dotenv_skipped_foreign_owner`), an
  ignored `app_*` setting in a user file (`deploy_setting_ignored`) or a `type_conflict`, although the
  docs said these were reported. The Python API is unchanged and stays silent until the application
  configures logging. A warning's `layer` field is now the layer's name (`app`) for every event; the
  merge warnings used to carry the enum member, which a text formatter printed as `Layer.APP` on
  Python 3.11+.
- `docs/cli-reference.md` and `read --help` describe the human output as it is: TOML with a
  `# source:` comment above each value (`path=(memory)` for the environment). The examples showed an
  older `key: value` / `provenance:` form, and Example 7's `grep -A1 "service.timeout"` matched
  nothing; it is now `grep -B1 "timeout ="`.
- The `.env` example in `docs/cli-reference.md` (Recommendations for Sensitive Data) wrote its keys with
  the environment prefix, `MYAPP___DATABASE__PASSWORD=...`. A `.env` key takes no prefix, so that line
  set `myapp._database.password` and left `database.password` unset; the example now reads
  `DATABASE__PASSWORD=...`.
- The `.env` search checks each file once. The resolver's search list, which `read_config` hands the
  loader, repeats the loader's own upward walk and holds the per-user `.env` that is already the
  walk's first candidate when `start_dir` is the user config directory, so a passed-over `.env` was
  owner-checked and reported two or three times. Which file loads is unchanged: the first hit still
  wins.
- An environment variable or `.env` key overrides a file key whatever the file's spelling:
  `MYAPP___A__DBPASSWORD` now overrides `[a] dbPassword` and keeps that spelling, with the env (or
  dotenv) layer in its provenance. Before, variable names arrived in lowercase and the merge compared
  keys case-sensitively, so the override landed beside the file key as `dbpassword` and
  `config.get("a.dbPassword")` kept the file's value, silently. File layers still compare keys exactly.
  Where one table holds two spellings that differ only by case, the value lands under its own
  lowercase key as before and the new warning `case_folded_key_ambiguous` names both.
- A `.env` file that starts with a UTF-8 byte-order mark (Notepad's "UTF-8 with BOM", PowerShell 5
  `Out-File -Encoding utf8`) loads its first key. The mark used to become part of that key's name, so
  `DB__HOST=...` on the first line produced an unreachable key and the value silently never applied.
  One leading mark is dropped, as the TOML reader already did.
- The CLI no longer fails when stdout cannot encode a value. On a stream such as a piped Windows
  stdout (the ANSI code page, cp1252 on a German or English install), a CJK character or an emoji
  in the configuration made `read`, `read-json` and their `--json` envelopes exit 22 with nothing on
  stdout. JSON output now writes such a character as a `\uXXXX` escape (valid JSON, the same value
  once parsed) and human output as a backslash escape; every character the stream can encode,
  umlauts on cp1252 included, is written as before. The same holds for `deploy`,
  `generate-examples`, `info` and `env-prefix`.
- A Windows layer root must be an absolute path. `deploy --platform windows` (or
  `deploy_config(..., platform="win32")`) on Linux or macOS without `LIB_LAYERED_CONFIG_PROGRAMDATA`
  used the built-in `C:\ProgramData`, which is relative there, so it wrote
  `./C:\ProgramData/<Vendor>/<App>/config.toml` into the current directory and exited 0. A relative
  `ProgramData`, `APPDATA` or `LOCALAPPDATA` value (or its `LIB_LAYERED_CONFIG_*` override) did the
  same on any platform, and the resolver read from there. Each now raises `ValidationError` naming
  the root and the variable to set (exit code 22 from the CLI), before anything is written. A
  deploy that writes only the user layer still needs no ProgramData root: reading the configured
  modes skips an app or host layer whose root is not absolute, since no file can sit there.
- `deploy` refuses a source that is not a `.toml` file, in every mode and before anything is written:
  `"<source> is not a .toml file, but deploy writes it as config.toml or <hostname>.toml, which are read
  only as TOML"` (a `LayerLoadError`, exit code 1). Every destination is read only as TOML, yet a valid
  `config.json` or `config.yaml` deployed with exit 0 and then broke every read with "is not valid
  TOML"; an invalid `app.conf` did the same under `--no-permissions`. A TOML file named `.conf`, which
  deployed under `--no-permissions` only, must be renamed to `.toml`. Files in the source's `.d`
  directory keep their TOML, YAML or JSON format.
- Arguments that used to give a silently wrong answer are refused. `display_config` with an
  `output_format` that names no format (`"xml"`, `"JSON"`) printed the human view and now raises
  `ValueError`. `read_config`, `read_config_json` and `read_config_raw` read `prefer="toml"` as the
  suffixes t, o, m, l, so it preferred nothing; a single `str` now raises `TypeError` (a type checker
  accepts it, since a `str` is a sequence of strings). `default_env_prefix("")` returned `___` and now
  raises `ValidationError` like `read_config(slug="")`; `lib_layered_config env-prefix ""` is a usage
  error (exit code 2) instead of printing `___`.
- `is_valid_profile_name` answers `False` for a value that is not a `str` instead of raising
  `TypeError`, as its "without raising an exception" promise says; its parameter is typed `object`.
- On Windows, `read_config` finds `%ProgramData%` again. The path resolver works on a copy of the
  environment, and Windows stores the name there as `PROGRAMDATA` (measured: `"ProgramData" in
  os.environ` is true, in `dict(os.environ)` false), so the app and host layers always fell back to
  `C:\ProgramData`, while `deploy` found the real one: on a machine with a relocated ProgramData, deploy
  wrote where read_config did not look. `ProgramData`, `APPDATA` and `LOCALAPPDATA` are now matched
  case-insensitively (the exact spelling first), and deploy uses the same lookup.
- A YAML file whose aliases form a cycle (`a: &x [*x]`) or expand to more than 1,000,000 values (an
  "alias bomb" of a few hundred bytes) is refused with `LayerLoadError`: `"<path> aliases a node into
  itself"` or `"<path> expands its aliases to more than 1,000,000 values"`. A cycle made `read_config`
  and `deploy` spin forever, and a small alias bomb ran for minutes and ended in `MemoryError`. The
  bound counts only what aliases add, so a large file without aliases still loads; shared aliases below
  the bound load as before.
- `notebooks/Quickstart.ipynb` installs the checkout it runs in, so CI's "Execute notebooks" job
  tests the commit under test. It used to install `git+https://github.com/...` every time, which is
  the pushed default branch, so a pull request's notebook run tested the code already there.
  Outside a checkout (a downloaded notebook) it still installs from GitHub.
- Two environment variables or `.env` lines that set a value and a key below it (`APP___DB=flat` and
  `APP___DB__PORT=2`) are refused in either order with `LayerLoadError`, naming both variables and
  the path: `environment: APP___DB sets db to a value, so APP___DB__PORT cannot set a key below it`.
  Before, the result depended on the order the variables arrived in: one order raised a bare
  `ValueError` (not a `ConfigError`), the other silently dropped `DB__PORT`. Keys below a JSON object
  value (`APP___DB='{"host": "h"}'`) now merge into it in either order, the deeper variable winning
  over the same key inside the object; before, they were dropped when the object came second.
- Only ASCII digit keys (`APP___HOSTS__1`) address a list element. A superscript or another script's
  digit (`²`, `١`) used to crash the merge with a bare `ValueError` or silently become an index; it now
  replaces the list like any other non-index key (`label`). An ASCII key of more than 4300 digits no
  longer crashes `int()`: leading zeros are ignored, and an index no list can reach is skipped with
  the usual `list_index_out_of_range` warning.
- `deploy` asks its keep-or-overwrite question on stderr, so stdout holds only the JSON result; with
  the prompt on stdout, a conflict made the output unparseable. When no answer can be read (stdin at
  end of file), it exits 2 with a usage error naming the file, `--batch` and `--force`, instead of a
  bare `Abort:` with exit 1. Answers piped on stdin still work, and Ctrl-C still aborts.
- `deploy_config`, `deploy_config_paths` and `read_deploy_config` read `platform` like the CLI's
  `--platform`: `macos`, `mac` and `Darwin` give the macOS layout, and an unknown name raises
  `ValidationError` listing the accepted ones. Before, any name the layouts did not recognise,
  `macos` included, silently deployed the Linux layout. Leaving `platform` out still auto-detects.
- `docs/python-api.md` shows `read_config_raw` returning a `MergeResult` (`.data`, `.provenance`); its
  examples unpacked a tuple and raised `TypeError`. Its imports use the package itself instead of
  internal module paths, and a test runs the documented calls and checks every import resolves.
- The `generate-examples` / `generate_examples` docs name the files really written: `xdg/` holds the
  app and host files, `home/` the user file and its `config.d/`. They described an `etc/` tree that is
  never written (so the documented CI check always exited 1), put `config.d/` under `xdg/`, and listed
  a `ProgramData/.../config.d/` file on Windows. A test compares every documented path with the
  command's output.
- The `deploy_config` docs say that `force` and `batch` decide a differing file before a
  `conflict_resolver` does: with either set, the resolver is never called. They said the resolver is
  called for each differing file, so a resolver used to log or audit a forced deploy recorded
  nothing without warning. The behaviour is unchanged; a test pins it.
- `deploy_config` and `deploy_config_paths` refuse `targets` given as a single str with
  `ValidationError: targets takes a sequence of layer names, not a single str: write ['user']`.
  `targets="user"` was read as the targets u, s, e, r and refused naming `u`; `targets=""` deployed
  nothing and returned an empty list without a word. A str that is not a layer name (`""`, `"x"`) is told
  to `write a list of app, host and user` instead. An empty list still deploys nothing and returns `[]`.
- `deploy_permissions_from_config` refuses anything but a `Config` with `TypeError:
  deploy_permissions_from_config takes a Config (from read_config), not dict`. A plain mapping has no
  dotted-key lookup, so a configured `[lib_layered_config.default_permissions]` in it was ignored
  without a word and the built-in modes came back.
- `DeployMode` refuses a `kind` that is not a `ModeKind` member with `DeployModeError: a mode kind must be
  a ModeKind, got str`. A str kind skipped every kind-specific safety rule, so `DeployMode(0o755, "file")`
  was accepted with its execute bits, and `DeployMode(0o666, "file")` crashed with `AttributeError`.
- No Linux or macOS layer resolves under the current directory any more. An empty or relative
  `LIB_LAYERED_CONFIG_ETC`, `LIB_LAYERED_CONFIG_MAC_APP_ROOT` or `LIB_LAYERED_CONFIG_MAC_HOME_ROOT` raises
  `LayerRootNotAbsoluteError`, as the Windows overrides already did; before, `LIB_LAYERED_CONFIG_ETC=""`
  loaded `./xdg/<slug>/config.toml` as the app layer and a deploy wrote there. An empty or relative
  `XDG_CONFIG_HOME` is ignored, as the XDG Base Directory specification says, and `~/.config` is used; before,
  a relative value read and deployed the user layer under the current directory, and an empty one put the
  `.env` fallback there.
- A process with no home directory (HOME unset and a uid without a passwd entry, as a container running an
  arbitrary uid) reads every layer but the user layer, and logs `user_layer_skipped_no_home`; before,
  `read_config` raised `RuntimeError` and loaded nothing. On Windows a set `APPDATA` or `LOCALAPPDATA` no
  longer asks for the home directory at all. A deploy to the `user` target raises
  `HomeDirectoryUnknownError`, a `ConfigError` that is still a `RuntimeError`, naming `HOME`
  (`USERPROFILE` on Windows, where Python ignores `HOME`) and the user-root variables.
- `deploy` / `deploy_config` raise `PermissionError` for a source, or a file in its `.d` directory, that
  cannot be read, in every mode and before anything is written, as documented. With permissions set (the
  default) it raised `DeployPermissionsError` saying the configured modes were unknown and to give both
  modes, which could not help; with a `.d` file unreadable and `set_permissions=False` the main file was
  written before the error.
- `vendor`, `app` and `slug` longer than 255 characters, and an explicit `hostname` longer than 250 (its file
  is `<hostname>.toml`), raise `ValidationError` on read and deploy alike; the absolute profile limit drops
  from 256 to 255. Such names never fit a file name: a 300-character slug raised `LayerLoadError` on read
  and `OSError` (file name too long) on deploy, and a 256-character profile read fine but failed to deploy.
- On Windows, a forced deploy (permissions off) onto a read-only destination no longer leaves a read-only
  `.config.toml.<hex>.tmp` beside it: the refusal now names the destination, and the temp file is removed.
- `deploy` / `deploy_config` refuse a source, or a TOML/YAML/JSON file in its `.d` directory, that
  does not parse, in every mode and before anything is written, with `LayerLoadError` and the
  loader's message. Before, the source was parsed only while reading the configured permission
  modes: that refusal suggested giving both modes, and explicit modes or `--no-permissions` then
  installed the broken file.
- Many keys in one `.env` file or environment, and many tables or lists a later layer replaces, are
  handled in time linear in their number. Each new key used to be compared with every key already in
  its table, and each replaced container scanned every provenance entry, so the cost grew with the
  square: a `.env` file of 20,000 lines took about 4 seconds to load (now 0.04 s), and 16,000 tables
  replaced by a later layer took about 4 seconds to merge (now 0.13 s). Results are unchanged; a key
  given in several cases still keeps its first spelling.
- `generate_examples` / `generate-examples` check `slug`, `vendor` and `app` the way `read_config`
  and `deploy` do, and refuse an unsafe one with `ValidationError` before writing anything. They
  became directory names unchecked, so `--slug ../../x` wrote the example files outside
  `--destination` and exited 0, an absolute slug aimed at the filesystem root, and a NUL character
  raised a bare `ValueError`.
- `generate_examples` refuses an unknown `platform` with `ValidationError`, like `deploy_config` and
  the CLI. It re-raised the same message as a bare `ValueError`, which `except ConfigError` did not
  catch; `except ValueError` still does, since `ValidationError` is a `ValueError`.
- `read_config` and `read_config_raw` annotate `start_dir` as `str | Path | None`, like
  `read_config_json` and the docs. A `Path` already worked at runtime, but a type checker refused it.
- The sdist holds only `src/`, `tests/`, `docs/`, `notebooks/`, the README, CHANGELOG, LICENSE,
  CONTRIBUTING and DEVELOPMENT files, `pyproject.toml` and `.gitignore`. hatchling honours only the
  root `.gitignore`, so an sdist built from a working checkout also shipped files kept out of git
  through `.git/info/exclude` (local notes, session archives) and tooling files; the sdists on PyPI,
  built by CI from a clean clone, were not affected. A test builds the sdist and checks its members,
  and the unpacked sdist runs its own test suite.

## [7.7.0] - 2026-11-01

### Changed
- A refused configuration file is reported by its exception alone. The library logged each refusal
  at ERROR and then raised it, so a caller that caught the `ConfigError` and carried on still printed
  an error line for a run that succeeded. The events `config_file_invalid`, `config_path_is_directory`,
  `config_path_is_special_file`, `config_path_unsupported_format`, `config_path_unreadable` and
  `dotenv_invalid_line` are now logged at DEBUG, with the same fields.

## [7.6.1] - 2026-10-30

### Docs

- The `python-layered-config` skill: a profile replaces the base paths, `ProtectHome` in a systemd
  unit, and writing a value into one layer.

## [7.6.0] - 2026-10-30

### Changed
- A JSON or YAML config file that names the same key twice in one table is refused with
  `LayerLoadError`: `"<path> repeats a key, and only its last value would load: db.host"`, a YAML
  position adding its line and column. Both parsers kept the last value without a word, so a
  copy-pasted block silently replaced the setting above it; TOML already refused such a file. A YAML
  merge key (`<<`) may still appear more than once, and a JSON value in an environment variable or `.env`
  still keeps the last of a repeated key.
- Every module states its public names in `__all__`, and a test keeps it that way. Each name that was
  public before stays public; only `adapters.file_loaders.structured.yaml`, the lazily imported PyYAML
  module object, is no longer a public name to a type checker.

### Fixed
- `LayerSnapshot` named by the plain layer string (`LayerSnapshot("user", {...}, None)`) merges
  again: 7.5.0 raised `AttributeError: 'str' object has no attribute 'value'` from `merge_layers`,
  which bit a caller rebuilding snapshots from `Config.origin(key)["layer"]`, a plain string. The
  name is parsed into its `Layer` member when the snapshot is built, and an unknown name raises
  `ValueError` there.

## [7.5.0] - 2026-10-29

### Fixed
- The `layer` field of the `layer_loaded`, `layer_error` and `deploy_setting_ignored` log events holds the
  layer's plain name (`"defaults"`), as the other events already did. It held the `Layer` member, which a
  text formatter printed as `Layer.DEFAULTS` on Python 3.11 and later.

### Changed
- `DeployPermissions.for_layer` is typed `layer: Layer`. A plain `"app"`, `"host"` or `"user"` still
  works at runtime, since `Layer` is a string enum; a strictly type-checked caller passes `Layer.APP`.
- `lib_layered_config.domain.permissions.LAYER_PERMISSIONS` is a read-only mapping keyed by `Layer`,
  each entry a `DefaultLayerModes` record: read `.directory` and `.file` where it read `["dir"]` and
  `["file"]`.

## [7.4.2] - 2026-10-29

### Fixed
- A config nested more than 253 levels deep (counted from its top-level table) no longer loads and then
  crashes every JSON view (`to_json`, `read_config_json`, `read-json`) with `TypeError: Recursion limit
  reached`. A TOML, JSON or YAML file that deep is refused, naming the file, the key it nests under and
  the depth; an environment or `.env` JSON value that deep stays the text it was written as. Both follow
  the rule an integer outside JSON's range already follows.
- An environment variable under the app's prefix whose value or name is not valid UTF-8 (on POSIX,
  `MYAPP___DB__NAME=$'a\xffb'`) is refused with `LayerLoadError`: `"environment variable
  MYAPP___DB__NAME is not valid UTF-8 (byte offset 1)"`, never naming the value. It loaded, then every
  JSON view and the CLI `read` crashed with `TypeError: str is not valid UTF-8`. A `.env` file with the
  same bytes was already refused this way. Variables outside the prefix are not looked at.

## [7.4.1] - 2026-10-29

### Fixed
- `read_config*(default_file=...)` refuses a FIFO, character or block device, or socket, naming the
  kind (`"/dev/fd/63 is a FIFO, not a configuration file"`). Such a path, a shell's `<(...)` among
  them, was passed over as if absent, so the defaults layer vanished without a word. A
  `default_file` that does not exist is still no defaults layer.
- `read_config*(default_file=...)` refuses a file whose suffix no loader reads (`defaults.conf`, or no
  suffix at all): `"defaults.conf has no supported format (.toml, .json, .yaml, .yml)"`. It loaded
  nothing and raised nothing before. The layers found on disk and the files in a `.d` directory are
  unchanged: those still skip any other suffix.

### Changed
- The `python-layered-config` skill (plugin 7.4.1) says a redactor that masks only strings leaks a
  secret the loader delivered as a list or table: mask by key whatever the value's shape, name a
  secret-bearing key no built-in pattern matches, and refuse a non-text value for a text setting.

## [7.4.0] - 2026-10-29

### Added
- Free-threaded Python: the package installs and runs on 3.14t and 3.15t with the GIL off, and
  declares `Free Threading :: 3 - Stable`. CI runs free-threaded cells for 3.14 and 3.15.
- The extras `rtoml` and `orjson` (`pip install "lib_layered_config[rtoml,orjson]"`) bring the
  Rust-based parsers back on Python 3.14+ with the GIL. Do not install them on a free-threaded
  build: neither has a free-threaded wheel, and the package never imports them there.
- `tomli>=2.5.0` is a dependency on Python 3.14, where stdlib `tomllib` reads only TOML 1.0, so a
  TOML 1.1 file loads on 3.14 and 3.14t as it does with `rtoml`.

### Changed
- `rtoml` and `orjson` are required only below Python 3.14; neither ships a free-threaded build,
  and importing one would turn the GIL back on. Without them, and on every free-threaded
  interpreter, TOML is read with `tomli` (Python 3.14) or stdlib `tomllib` (3.15+) and JSON with
  stdlib `json`. These backends give the same results and refuse the same files: JSON nested past
  1024 levels, `NaN`/`Infinity`, numbers past the float range and lone surrogates on read; TOML
  with a float past the float range or nested too deep. Writing JSON refuses the same values
  orjson does: nesting past 254 levels, integers outside `-2**63 .. 2**64-1`, and text holding a
  lone surrogate. A JSON integer past 64 bits reads as a float on both. The difference left is
  TOML depth: `rtoml` allows 80 levels per table header, dotted key and value, which the parsed
  data cannot tell apart, so `tomli`/`tomllib` refuse tables nested past 101 levels (the depth the
  merge refuses for tables outside arrays) and arrays nested in arrays past 80. A single header or
  inline table 81 to 100 levels deep (a dotted key up to 101 keys) therefore loads there and is
  refused by `rtoml`, while tables nested past 101 levels inside an array of tables load with
  `rtoml` and are refused there.
- The `python-layered-config` skill (plugin 7.4.0) says where rtoml and orjson are used (below
  Python 3.14, or from the `rtoml`/`orjson` extras on a GIL build, never to be installed on a
  free-threaded one), that a free-threaded interpreter never imports them and parses with `tomli`
  or `tomllib`, and that `dotenv_path=` / `--env-file` reads a FIFO or device under the shared
  10 MiB cap, while a missing path is an empty layer in Python and a usage error on the CLI.
- The `python-layered-config` skill (plugin 7.3.1) says to write an integer outside `-2**63` to
  `2**64-1` as a string, and that a file the loader refuses surfaces as `LayerLoadError`.
- The `python-layered-config` skill (plugin 7.3.2) adds "Probing and testing an app built on it": a
  config probe run from inside a repository loads that repository's `.env`, so probe from an empty
  directory with `start_dir=` set and anchor tests under `tmp_path`; a relative `start_dir` ends its
  `.env` search at the current directory; on Windows a deploy falls back to `%LOCALAPPDATA%` when
  the roaming directory is missing and never applies the configured modes.
- The `python-layered-config` skill (plugin 7.3.3) says how to label the keys a
  `Config.with_overrides` supplies as the CLI's in provenance: rebuild provenance for exactly those
  keys and pass the not-sensitive set as the rebuilt `Config`'s third argument.
- The `python-layered-config` skill (plugin 7.3.4) says which roots isolate a test from every
  deployed layer: strip inherited `LIB_LAYERED_CONFIG*` and `<SLUG>___` variables, then set all six
  roots, the three app roots (`LIB_LAYERED_CONFIG_ETC`, `LIB_LAYERED_CONFIG_MAC_APP_ROOT`,
  `LIB_LAYERED_CONFIG_PROGRAMDATA`) included; setting the OS variable `PROGRAMDATA` instead does
  nothing.
- The `python-layered-config` skill (plugin 7.3.5) says an unquoted digit-only value with no
  leading zero arrives as an `int` from `.env` and the environment alike, so a pydantic `str` field
  fails startup; set `coerce_numbers_to_str=True` on one shared base model.

### Fixed
- `read_config(dotenv_path=...)` and `--env-file` read a FIFO or a device, so a shell process
  substitution (`--env-file <(printf 'KEY=value')`) works. It used to load nothing, silently. The
  read stops one byte past the 10 MiB cap, so an endless source such as `/dev/zero` is refused
  instead of read forever. Like `cat`, the read waits for a FIFO's writer and for it to close. A
  path that does not exist still loads nothing in the Python API (`--env-file` refuses it as a
  usage error, as before); a socket, which used to load nothing too, is now an unreadable-file
  error.
- An environment or `.env` integer below `-2**63` (such as `-9999999999999999999`) stays a
  string, as one of more than 19 digits already did. As an int it loaded and then made `Config.to_json()` and every other JSON view
  raise `TypeError: Integer exceeds 64-bit range`.
- The docstring of the `.env` upward search said it searches nowhere without a start directory;
  it starts in the current directory.

## [7.3.0] - 2026-10-19

### Changed
- **A TOML or YAML integer outside JSON's range refuses the file.** orjson writes an integer only
  from -2**63 to 2**64-1, while rtoml reads up to 128 bits and a YAML hex literal any width, so
  such a config loaded and then crashed every JSON view (`Config.to_json`, `read_config_json`,
  `display_config` in JSON) with `TypeError: Integer exceeds 64-bit range`. The loader now refuses
  the file, naming it and each integer's position and width, never its digits, the same rule a
  YAML `!!set` or `!!binary` value follows. Write such a number as a string.

### Fixed
- `display_config` and the `read` command no longer raise `ValueError: Exceeds the limit (4300
  digits)` on an int too long for Python to write as decimal text, which a `Config` the caller
  builds can hold. Such an int is shown as `<int, N bits>`; every other int prints as before.
- `.gitignore` no longer carries an inline comment on four patterns (`*$py.class`, `*.egg-info/`,
  `*.manifest`, `*.spec`): gitignore read the comment as part of the pattern, so each ignored nothing.

## [7.2.0] - 2026-10-19

### Added
- `deploy_config_paths(source, *, vendor, app, targets, ...)` returns every file a `deploy_config` of
  those targets writes, resolved, and `read_deploy_config(source, *, vendor, app, skip, ...)` returns the
  configuration the deploy reads for its permission modes (no `.env`, a user file keeping only its
  `user_*` and `enabled` settings) with the `skip` files left out. Both are exported from the package root
  and run the code `deploy_config` itself runs, so an application can report the modes a deploy will use,
  or read its configuration past a broken file a forced deploy is about to replace, without importing
  the library's internals.

## [7.1.9] - 2026-10-12

### Added
- Python 3.15 is a supported version: declared in the classifiers, so CI and `make test-all` run it.
- `uv.lock` is committed, and `[tool.uv] exclude-newer` sets a cooldown that keeps releases younger
  than it out of the lock. CI installs exactly the locked tree on push and pull request; the nightly
  scheduled run still resolves afresh to catch upstream breakage early.

### Changed
- The install section explains why installing with uv protects against supply-chain attacks and why
  a plain `pip install` from PyPI does not.

## [7.1.8] - 2026-10-12

### Fixed

- **A directory where a layer's config file belongs now refuses the load, as 7.0.0 said.** 7.0.0
  refused a directory at `default_file` and an explicit `dotenv_path`, but the path resolver handed
  a discovered app, host or user path (`config.toml`, `hosts/<hostname>.toml`) to the loader only
  when it was a file, so a directory there was skipped without a word and the configuration fell
  back to the layers below. It now refuses with "`<path>` is a directory, not a configuration
  file" on every platform. The upward `.env` search still passes over a directory named `.env`.

## [7.1.7] - 2026-10-12

### Fixed

- **Provenance names only keys the merged config still holds.** A table declared empty in one
  layer and filled by a later one (defaults `console_styles = {}`, a `.env` setting
  `..._CONSOLE_STYLES={"DEBUG": "dim"}`) kept the empty declaration's origin, so
  `origin("...console_styles")` reported the defaults file for a table whose every value came
  from the `.env`. A value later replaced by a table kept its entry the same way, and a table
  later replaced by a value kept the entries of the values it held, so `origin()` answered for
  keys that no longer exist. A table that holds values now has no entry of its own, as one that
  was never empty already had; an empty table still reports where it was last declared.

### Internal

- Added a Windows test that a `%APPDATA%` which cannot be checked makes deploy raise
  `PermissionError` rather than fall back to `%LOCALAPPDATA%`. Windows `os.stat` reads a denied
  directory's entry from its parent, so the wall (`tests/support/windows_acl.py`) denies both the
  directory's attributes and the parent's listing, and switches off the backup privileges an
  elevated session would use to see through it.

## [7.1.6] - 2026-10-12

### Fixed

- **A YAML `!!set` or `!!binary` value refuses the file.** PyYAML's safe loader builds them as a
  Python `set` and `bytes`, neither of which has a JSON form, so such a config loaded and then
  crashed every JSON view (`Config.to_json`, with or without `redact`, `read_config_json`,
  `display_config` in JSON) with an uncaught `TypeError`. The loader now
  raises `InvalidFormatError` (`LayerLoadError` from `read_config`) naming the file and each such
  value's dotted position and type, never the value. Write a list or a base64 string instead.
  Timestamps and dates still load and serialise.

- **A deploy source behind a permission wall raises `PermissionError` on every Python.** Deploy
  asked pathlib whether its source and the source's `.d` files existed, and pathlib raises before
  Python 3.14 but answers `False` from 3.14: a walled source was "Configuration source not found"
  on 3.14, and a `.d` directory that can be listed but not entered lost its files there without a
  word (with `set_permissions=False`, which skips deploy's own read of the configuration). Deploy,
  backup naming and `generate_examples` now ask the path probe, which raises the `stat` error
  itself, and nothing is written. A missing source still raises `FileNotFoundError`.

- **The `read` command prints TOML that reads back as what it shows.** Its renderer wrote every
  key bare and every string between plain double quotes, so `"a.b" = 3` under `[probe]` printed as
  `a.b = 3` (the nested key `probe.a.b`), a table named `sec tion` printed as `[sec tion]` (not
  TOML), and a string holding a quote broke the line. It now quotes keys, headers and strings the
  way `display_config` does, through one shared module; plain keys and values print as before, and
  a list prints with a space after each comma (`["a", "b"]`).

## [7.1.5] - 2026-10-12

### Fixed

- **`read_config`, `read_config_json` and `read_config_raw` keep the caller's trace id.** Each call
  reset the binding to `None` on entry, so `bind_trace_id("abc123")` before a read tagged none of its
  log events and also cleared the id for the caller's own events afterwards. The reads now leave the
  binding alone, as `deploy_config` already did: their events carry the bound id, and with nothing
  bound they carry `None` as before.

### Documentation

- The shipped skill names the two provenance formats (`display_config` prints
  `# layer:<layer> profile:<profile> (<path>)`, the `read` command `# source: layer=..., path=...`)
  instead of calling them the same, and says a plain YAML mapping keeps the file's key order.

## [7.1.4] - 2026-10-12

### Fixed

- **A YAML `!!omap` or `!!pairs` value with entries refuses the file.** PyYAML's safe loader builds both tags as a
  list of `(key, value)` tuples, so a key such as `password` inside one was never seen as a key: every
  redacted view (`as_dict(redact=True)`, `to_json(redact=True)`, `get_redacted`,
  `read_config_json(redact=True)`, both `display_config` formats, `read --redact`) printed its value,
  and dotted lookup could not reach it. The loader now raises `InvalidFormatError` (`LayerLoadError`
  from `read_config`) naming the file and the dotted position of each such value, never a key or value
  from inside it. Write a plain mapping instead; it keeps its order. An empty `!!omap []` holds nothing
  and still loads, and a merge key (`<<: !!omap [...]`) already arrives as a plain mapping.

- **A configuration path that cannot be checked keeps its `OSError` in the error chain.** An
  unenterable layer directory, a `default_file` or `dotenv_path` behind a permission wall, a file in a
  `.d` directory that can be listed but not entered, or a path with a NUL byte raised `LayerLoadError`
  with no `PermissionError` (or `ValueError`) under `__cause__`, so a caller could not tell
  "permission denied" from "malformed file". Every "cannot be read" refusal now carries the error
  behind it.

### Changed

- **Requires `rtoml>=0.14.0`.** rtoml 0.14.0 refuses TOML nested deeper than 80 levels (arrays, inline
  tables, table headers and dotted keys alike), which 0.13.0 accepted. A table 81 to 100 levels deep,
  which the merge's 100-level limit allowed, no longer loads.
- **A file nested deeper than its parser allows says so.** It was reported as `<path> is not valid
  TOML` (or JSON, YAML), calling a well-formed file broken. It now reads `<path> nests deeper than the
  TOML parser allows`, with `(line N, column M)` when the parser gives a position: TOML stops at 80
  levels, JSON at 1024, YAML at Python's recursion limit. A malformed file keeps `is not valid`.

## [7.1.3] - 2026-10-12

### Fixed

- **Redaction reaches a secret in any nesting of mappings, lists and tuples.** It recursed only into a
  dict under a key and a dict directly inside a list, so `s = [[{password = "x"}]]` in a TOML file, a
  dict inside a tuple, or a mapping that is not a `dict` (a `MappingProxyType` handed to
  `redact_mapping`) came back in clear from `as_dict(redact=True)`, `to_json(redact=True)`,
  `read_config_json(redact=True)` and both `display_config` formats. A tuple stays a tuple, a declared
  not-sensitive path still addresses list items at any list depth. The redaction depth limit now
  counts every mapping, list and tuple level and is 300 (was 100 mapping levels), so a redacted view
  never refuses a configuration that reading accepted.

## [7.1.2] - 2026-10-11

### Fixed

- **`display_config` shows every key.** Its human format serialised the configuration to TOML and
  re-parsed that text line by line. A key TOML must quote (a space, a dot, a non-ASCII letter, the empty
  name, a leading digit) silently vanished from the output - the `config` command of an application built
  on it - an array of tables lost its header and showed its keys as top-level keys, and a key under a
  quoted section name lost its provenance comment. It now walks the configuration itself: such keys are
  shown quoted with their source, and a list is one value (`tables = [{n = 1}, {n = 2}]`).
- **`display_config` names every layer that set part of a list.** An element a higher layer replaced by
  index (`APP___HOSTS__0__NAME=x`) gets its own comment, `# layer:env profile:none for hosts.0.name`,
  below the list's own source, which no longer takes the credit for it.
- `display_config` shows the source of an empty table above its header, and a key whose value is `None`
  can be shown on its own with `section=` (it was refused as not found); `None` prints as `null`, no
  longer as the string `"null"`.
- `display_config` escapes C1 control characters (U+0080-U+009F; U+009B starts a terminal escape
  sequence) in keys and values, and quotes a `section=` name like any other key.
- The `section=` view now writes a value exactly as the full view does: a string is escaped (`"C:\\Users"`,
  `"a\"b"`), a datetime is ISO with a `T`, and a list has a space after each comma. A set prints as a
  sorted array in both views.

## [7.1.1] - 2026-10-11

### Fixed

- **A configuration path behind a permission wall behaves the same on every Python.** Before 3.14,
  pathlib raised `PermissionError` when a directory on a path could not be entered, and 3.14 returns
  `False`. So running from a directory the user cannot enter crashed `read_config` on 3.10-3.13, while
  an unreadable `/etc/xdg/<slug>/`, `default_file` or `dotenv_path` was silently dropped on 3.14. Now the
  upward `.env` search skips a directory it cannot enter, and a layer's config location, the platform
  `.env` location or a named file it cannot check or read raises `LayerLoadError`: `"<path> cannot be
  read: <reason>"`. An unreadable config file, or a path with a NUL byte, also raises `LayerLoadError`
  instead of a bare `PermissionError` or `ValueError`. With `dotenv_path` set, the `.env` search and its
  platform location are no longer probed at all.
- **`read_config` no longer crashes when the operating system cannot name the working directory.** On
  macOS, `os.getcwd()` fails in a directory the user cannot enter, and on any POSIX system in one that was
  removed; `read_config` without `start_dir` raised that bare `OSError`. The `.env` search now has no
  starting point there and finds no project `.env`, the same answer as for a directory it cannot enter.

### Changed

- The dev dependency on hypothesis is split by Python version: 6.169 requires 3.11, so 3.10 stays below it.

## [7.1.0] - 2026-10-09

### Added

- **An application can declare keys that are not secrets.** `read_config`, `read_config_json` and
  `read_config_raw` take `not_sensitive=["performance.max_token_bytes"]`: dotted paths whose name
  looks sensitive (here `token`) but whose value is not a secret. `redact=True` and `display_config`
  show them, and an unquoted `null`/`none` in the environment or `.env` reads as None for them like
  for any other key. The returned `Config` carries the declaration, also through `with_overrides`,
  so output calls need no extra argument; `redact_mapping(data, not_sensitive=...)` takes it directly.
  Paths match case-insensitively, a list item is addressed by the list's path with no index, and
  declaring a key below a masked section does not unmask the section. A bare string is refused.
  New exports: `NotSensitiveKeys`, `is_sensitive_at`; new method `Config.get_redacted(key)`.

### Changed

- Dependency floors raised: `lib_cli_exit_tools>=2.4.0`, `orjson>=3.13.0`; dev `hypothesis>=6.168.5`.
- The pip-audit exclusion for CVE-2026-7246 is gone: click resolves to 8.5.0, past the fix, so
  the audit passes without it.
- The `python-layered-config` skill now names every public export and CLI command: the error
  classes, redaction and profile helpers, `deploy_config` and its `DeployResult.action` enum,
  `generate_examples`, `display_config`, the logging hooks, and the `fail` command.

### Fixed

- **The section view no longer shows what the full view masks.** `display_config(section=...)`
  (the basis of an application's `--section` view) printed the value of a key below a section
  whose own name is sensitive - `credentials.user` showed `alice` - while the full view showed
  the whole section as `***REDACTED***`. A key below a masked section is now masked too.
- The `DotEnvLoader` port declares the `dotenv_path` parameter its adapter already took.

## [7.0.1] - 2026-10-02

### Fixed

- **The human display shows a source path as written.** A path containing square brackets
  (`XDG_CONFIG_HOME=/tmp/cfg[red]x[/red]`) was read as Rich markup: the brackets vanished from
  the path shown, and an unmatched closing tag (`[/bad]`) raised `MarkupError` out of
  `display_config`. The provenance comment is now printed as plain text.
- The `python-layered-config` skill describes 7.0.0: an unquoted `.env` value converts like the
  environment, a sensitive key keeps `null`/`none` as text, and an unquoted YAML key that is not a
  string refuses the file. It also states that a `.env` key carries no `<SLUG>___` prefix, and that
  Linux reads both `/etc/xdg/<slug>/` and `/etc/<slug>/` for the app and host layers, the latter
  winning, rather than using `/etc/<slug>/` as a fallback.

## [7.0.0] - 2026-10-02

Breaking release. Each change below turns a case that loaded silently, or with only a warning, into
either the documented value or a refusal at load time.

### Changed

- **An unquoted `.env` value is converted exactly like the same value in the environment.** A JSON
  array or object is parsed, `true`/`false` become a bool, `null`/`none` become None, and a number
  becomes an int or float only when it reads back as the same text (`5432` and `3.5` convert, `007`
  stays text); anything else stays the text it is. A quoted value is the literal text, so
  `PORT="5432"` keeps a string. Until now only a JSON array or object was converted and every other
  `.env` value arrived as a string, so the same setting changed type when it moved between `.env`
  and the environment. A consumer model that declares a `str` field fed an unquoted all-digit value
  (an ID, a PIN, an all-digit user name) now receives an int: quote the value in `.env`, or accept a
  number in the model.
- **A sensitive key keeps an unquoted `null` or `none` as text**, in the environment and in `.env`.
  A sensitive key is one `redact=True` masks (`smtp_password`, `api_token`, any `_key` suffix), judged
  by its last segment. Such a secret was read as None, which a consumer treats as "no credential"
  and proceeds without one; it is now the text, so the login fails visibly. The
  `env_secret_became_none` warning is removed. Every other key still reads `null`/`none` as None.

### Removed

- **`lib_layered_config.domain.permissions.set_permissions` and `set_custom_permissions`.** Use
  `apply_mode(path, DeployMode(mode, kind))`. The `set_permissions=` parameter of `deploy_config` is
  unchanged.

### Fixed

- **A YAML key that is not a string refuses the file.** `1:` reads as an int key and `true:` as a
  bool key, which made the whole mapping one opaque value: none of its keys reachable by dotted
  lookup, no per-key provenance, replaced whole by a higher layer. The loader raises
  `InvalidFormatError` (wrapped in `LayerLoadError` by `read_config`) naming the file, where each key
  sits and the key, never a value; quote such a key (`'1':`). The `config_key_not_string` warning is
  removed.
- **A configured file path that is a directory refuses the load** with "`<path>` is a directory, not
  a configuration file", for a defaults, app, host or user file path and for an explicit
  `dotenv_path`. It was skipped, so the configuration silently fell back to lower layers. The
  `<name>.d/` companion directory is unaffected, and the upward `.env` search still passes over a
  directory named `.env`, such as a virtualenv. The `config_directory_skipped` warning is removed.

## [6.1.1] - 2026-10-01

### Security

- The environment layer logs an `env_secret_became_none` warning when a sensitive key (a name `redact=True`
  masks, such as `smtp_password` or `api_token`) is set to an unquoted `null` or `none` and therefore read as
  None. A consumer reads that None as "no credential" and proceeds without one, which nothing reported until
  now. The warning names the dotted key, never the value. The conversion itself is unchanged; the next major
  release keeps such a value as text.

### Fixed

- A YAML key that is not a string (`1:` reads as an int, `true:` as a bool) is now reported: the YAML loader
  logs one `config_key_not_string` warning per key, naming the file, the key's parent position and the key,
  never the value. Such a key made its whole mapping one opaque value - none of its keys reachable by dotted
  lookup, no per-key provenance, replaced whole by a higher layer - with no sign of why. The file still loads
  as before; the next major release refuses such keys.

## [6.1.0] - 2026-10-01

### Security

- **A `.env` file is capped at the same 10 MiB (`MAX_CONFIG_FILE_BYTES`) as the structured configuration
  files**, checked before the file is read, and refused with the same `InvalidFormatError` message.
- **`deploy_config` and `lib_layered_config deploy` no longer take `app_*`/`host_*` modes from a user-layer
  file.** This changes which layers decide the modes of system files: `app_directory`, `app_file`,
  `host_directory` and `host_file` in `[lib_layered_config.default_permissions]` now come only from the
  deployed source, the app and host files and the environment, so a root `deploy --target app` that runs with
  the invoking account's `HOME` or `XDG_CONFIG_HOME` (`sudo -E`, or sudoers keeping `HOME`) can no longer have
  that account's user file widen the read access of the files it writes. A user-layer value is ignored rather
  than refused: it no longer hides a lower layer's value, a malformed one no longer stops the deploy, and each
  ignored key is logged as a `deploy_setting_ignored` warning (key and file, never the value). `user_*` and
  `enabled` keep every source. `deploy_permissions_from_config(read_config(...))` reads the merged `Config` as
  it is and does not apply this rule; pass runtime values through `permission_overrides` instead.

### Fixed

- **A configured file path that is a directory is no longer skipped without a trace.** A defaults, app, host
  or user file path, or an explicit `dotenv_path`, that is a directory logs a `config_directory_skipped`
  warning naming the path; the `<name>.d/` companion directory is unaffected. It is still skipped rather than
  refused, which would be a breaking change.
- **`display_config()` builds its Rich console per call instead of once at import**, so `FORCE_COLOR` and
  `NO_COLOR` as they are when the output is written decide its colour, not the values at import time.

### Deprecated

- **`lib_layered_config.domain.permissions.set_permissions` and `set_custom_permissions`** emit a
  `DeprecationWarning`: nothing in the library calls them since `deploy_config` decides modes from
  `DeployPermissions`. Use `apply_mode(path, DeployMode(mode, kind))`; they are removed in the next major version.

### Documentation

- **A root `deploy --target app` that keeps the invoking account's environment** reads that account's
  `app_*`/`host_*` variables, which can widen the read access of the files it writes (never write or execute).
  The File Permissions section of the CLI reference says so and names the two ways to avoid it.
- **`DeployModeError`** lists the refusal of a `dir_mode`/`file_mode` given together with `set_permissions=False`.

## [6.0.0] - 2026-09-29

### Added

- **`deploy_config(permission_overrides=...)` for runtime overrides** (such as a `--set` option): keys are
  the section's own setting names (`permission_overrides={"user_file": "0o640"}`), laid over the deploy's own
  read, validated like configured values and reported as `(source: override)`; `{"enabled": False}` turns
  permission setting off without reading the configuration only when `set_permissions` is `None` and no
  `dir_mode`/`file_mode` is given (an explicit mode or `set_permissions=True` sets modes whatever `enabled` says).
  `permissions=` still takes a complete `DeployPermissions`, but cannot be combined with `permission_overrides`,
  and one built from an application's normal `read_config` includes `.env` and the deployed files, which the
  deploy's own read leaves out on purpose: use `permission_overrides` for runtime overrides.
- **Public deploy permission types:** `DeployMode`, `ModeKind`, `DeployModeError`, `LayerModes`,
  `DeployPermissions`, `DeployPermissionsError` (`problems`, `hint`), `PermissionProblem` and
  `deploy_permissions_from_config`, exported from the package root.
- **`lib_layered_config deploy --dir-mode MODE --file-mode MODE`**, each an octal string (`750` or `0o750`).
- **The YAML loader also decodes a UTF-32 file that starts with a UTF-32 byte-order mark.** UTF-16 with a BOM
  keeps working as before; every other YAML/TOML/JSON/`.env` file stays strict UTF-8.

### Security

- **`deploy_config` and `lib_layered_config deploy` refuse an unsafe or malformed permission mode instead of
  applying it.** A mode must be an integer in 0..0o7777 without the setuid, setgid or sticky bit and without
  group or world write; a directory mode must keep owner rwx, a file mode owner rw and no execute bit.
  `dir_mode=-1` used to leave the directory at 0o7777, and the decimal integer 444 (meant as octal) applied
  0o674 to a file that can hold credentials. A refused `dir_mode`/`file_mode` or `set_custom_permissions` mode
  raises `DeployModeError` naming the reason or each offending bit, raised before anything is written. A
  refused configured or override value raises `DeployPermissionsError`, one line per problem. The CLI reports
  a refused `--dir-mode`/`--file-mode` as a usage error.
- **A configuration file that cannot be decoded or parsed is reported without its content.** The error names
  the file, the format and the line and column (or byte offset), when the parser reports one; the parser's own
  text, which for YAML echoed the offending source line, is no longer in the message, the exception chain or
  the `config_file_invalid` log event.

### Fixed

- **The configured `[lib_layered_config.default_permissions]` modes are applied.** Whenever a configured value
  can change a mode, `deploy_config` reads the section from the deployed source (the defaults layer), the app,
  host and user files this call does not write, and the environment, and resolves every target layer on its
  own. It never reads `.env`, and the file being replaced never decides its replacement's mode. Modes are
  applied to each file the deploy writes; a file whose content is unchanged is skipped and keeps its mode.
- **A deployed copy's own section is not consulted by the deploy that writes or keeps it.** With `--batch` a
  kept file stays live, but the directory and the `.ucf` beside it get their modes from the other layers; and
  with `--target app --target user` the app `config.toml` is a destination, so its `user_*` settings are not
  read (`--target user` alone reads them). Put local settings in a file the package does not ship, such as
  `config.d/99-local.toml`, which deploy never writes, so it is read whenever the configured modes are.

### Changed (breaking)

- `deploy_config(set_permissions=...)` defaults to `None`: follow the configured `enabled` (true when unset).
  `--permissions/--no-permissions` defaults the same way. An explicit `dir_mode` or `file_mode` means modes are
  set; one given together with `set_permissions=False` (CLI: `--no-permissions`) is refused.
- **File mode change for a partial override.** With only `dir_mode` (or only `file_mode`), the other side now
  gets the configured or built-in layer mode, as the parameters were documented. An app- or host-layer file
  deployed with only `dir_mode` used to keep the temporary file's 0o600; it now gets 0o644 unless `app_file` /
  `host_file` is configured.
- The permission section is validated in one pass. A bare integer is refused with a hint to write it as an
  octal string, `"0o640"` (quoted) in a file and `0o640` in the environment or a `--set`: a TOML integer is
  decimal, the TOML literal `0o640` also arrives as an integer, and so does `--set ...user_file=640`. `enabled`
  must be a boolean; an unknown key is refused, its name shown shortened. Each problem is one line
  `<dotted key>: <reason> (source: <file, layer or override>)` in a `DeployPermissionsError`.
- **An explicit `dir_mode`/`file_mode` (or `set_custom_permissions`) is now checked, with no opt-out.** Before,
  any integer was accepted and applied as-is; now the same safety rule above applies to it too (`DeployModeError`
  refuses group or world write, a setuid/setgid/sticky bit, a directory without owner `rwx`, or a file with an
  execute bit or without owner `rw`). There is no override for an explicit mode. `dir_mode=-1` used to leave the
  directory at `0o7777`, and the decimal integer `444` (meant as octal) used to apply `0o674` to a file that can
  hold credentials. `set_custom_permissions` now validates on every platform, including Windows, where an unsafe
  mode used to be silently accepted and simply never applied.
- **`deploy_config` now reads the configuration and refuses when it cannot.** Any unreadable or broken
  non-destination app/host/user file (a decode or parse failure, a `PermissionError` reading it, or an
  environment scalar/table collision) blocks a default POSIX deploy with a `DeployPermissionsError` naming the
  file and reason, instead of falling back to the built-in modes. This does not apply
  when both `dir_mode` and `file_mode` are given, when `set_permissions=False`, when a complete `permissions=`
  object is passed (the configuration is never read), or on Windows (modes are not applied there).
- An unknown `targets` entry is refused before anything is written; it used to fail after the targets before it
  had been deployed.
- **Type change, environment layer:** a value becomes an int or float only when the number reads back as the
  same text. `007123`, `0640`, `-007`, `1.50`, `+5`, `1_000`, `1e5`, `nan`, `Infinity`, non-ASCII digits and
  integers of 20 or more digits now arrive as the string that was set; `5`, `-7`, `3.5`, `true` and `null`
  convert as before. A 5000-digit value no longer raises a bare `ValueError`.
- **Type change, `.env`:** an UNQUOTED value that is a JSON array or object now becomes a list or table, as in
  the environment. A quoted value stays the literal text, and scalars in `.env` stay strings.
- **Exception type change:** a `.env` that is not valid UTF-8 raised `UnicodeDecodeError` (a `ValueError`); it
  now raises `InvalidFormatError`, surfacing from `read_config` as `LayerLoadError`, which is a `ConfigError`
  and NOT a `ValueError`. TOML/JSON/YAML parse errors used to read `Invalid <FORMAT> in <path>: <parser text>`
  (the `<parser text>` came straight from the parser and could echo the offending source line); they now read
  `<path> is not valid <FORMAT>`, plus ` (line N, column M)` when a position is known; an undecodable file reads
  `<path> is not valid UTF-8 (line N, byte offset M)`, or for a BOM-marked YAML file `<path> is not valid
  UTF-16|UTF-32 (byte offset M)`. The `.env` malformed-line message (`Malformed line N in <path>`) is unchanged.
  A YAML value that PyYAML's own constructor refuses (for example `a: 2020-13-01`, an out-of-range calendar
  date) used to raise a bare `ValueError` straight out of `read_config`; it now raises `InvalidFormatError`,
  surfacing as `LayerLoadError`, a `ConfigError` and NOT a `ValueError`. A deeply nested YAML document that made
  PyYAML raise a bare `RecursionError` is handled the same way, now raising `InvalidFormatError` /
  `LayerLoadError` instead of `RecursionError`.

Migration: write configured modes as quoted strings (`user_file = "0o640"`; in the environment
`<PREFIX>___LIB_LAYERED_CONFIG__DEFAULT_PERMISSIONS__USER_FILE=0o640`, since a bare `640` there is a number,
while `0640` now stays the string "0640" and is read as 0o640). A broken file at the destination no longer
blocks `deploy --force`; a broken file elsewhere does, and then give both mode options (`--no-permissions` also
works but leaves the modes to the umask). Code that caught `ValueError` for an undecodable `.env` or for a
YAML constructor error (an out-of-range date and the like) or `RecursionError` for a deeply nested YAML document
catches `ConfigError` instead. Code that relied on
the environment turning `0640`-style text into a number converts it itself.
A caller that passed an explicit `dir_mode`, `file_mode` or a mode to `set_custom_permissions` with group or
world write, a special bit, or (for a file) an execute bit must pick a safe mode instead; there is no flag to
keep the old permissive behaviour. This includes a read-only mode that locks the owner out: a file mode such
as `0o444`, `0o440` or `0o400` (no owner write) and a directory mode without owner `rwx` are refused the same
way. Code that grepped the old loader message form (`Invalid <FORMAT> in <path>:
<parser text>`) must match the new one instead (see the exception-type-change bullet above).

## [5.7.0] - 2026-09-27

### Changed

- **`Config.with_overrides()` names the override as the source of every key it supplies.**
  `origin()` for such a key now returns layer `"override"` (exported as `OVERRIDE_LAYER`), path
  `None`, instead of the provenance of the value it replaced, which named a file that no longer
  held the value shown. Keys the override did not touch keep their source exactly as loaded,
  including list elements and empty tables, and keys it removed (a table replaced by a scalar)
  have none. A caller that rebuilt provenance itself keeps working; it can drop that code if
  `override` is the label it wants.
- **The shipped skill describes the new provenance behaviour**, keeping the rebuild recipe for
  callers on an older floor or wanting the layer named `cli`.
- **`docs/python-api.md` describes `with_overrides` as the deep merge it has been since 5.3.0**, not
  a shallow top-level one.

## [5.6.2] - 2026-07-30

### Changed

- **The shipped skill's plugin version now tracks the package version.** bmk 3.14.0 raises
  `.claude-plugin/plugin.json` to the package version on bump, push and release, and never lowers
  it. An install re-fetches a skill only when that version changes, so the two numbers drifting
  apart meant a skill edit could ship to nobody.
- **The shipped skill documents `read_config(default_file=...)`.** That parameter, and the note that
  it is the only way to seed the `defaults` layer, existed only in the bitranox-skills mirror; this
  copy has been behind since. No functional change to the library.

## [5.6.1] - 2026-07-24

### Fixed

- Latest ruff (0.16) widened its default rule set to ~920 rules; the project had no explicit
  `[tool.ruff.lint].select`, so CI went red on hundreds of newly-enforced, previously-unpoliced
  rules. Pinned the curated bitranox rule policy instead of chasing the default set.

### Changed

- Added an explicit `[tool.ruff.lint].select` (pycodestyle/pyflakes/isort/pep8-naming/pyupgrade/
  bugbear/builtins/comprehensions/simplify/type-checking-imports/ruff-specific/logging/print/
  pathlib/pylint/bandit/perf/eradicate/boolean-trap) plus per-file-ignores for tests and for the
  composition/orchestration modules that genuinely need more than five named parameters
  (`core.py`, `_layers.py`, `application/merge.py`, `adapters/path_resolvers/default.py`,
  `cli/*.py`, `examples/*.py`).
- Converted CLI command callbacks and internal helpers (`application/merge.py` recursion
  helpers, `cli/common.py` query builders, `domain/identifiers._check_strict_pattern`,
  `examples/deploy.py`/`examples/generate.py` private helpers) to keyword-only parameters where
  every caller already passes by keyword; updated the few positional call sites and doctests to
  match.
- Moved several first-party/typing-only imports into `TYPE_CHECKING` blocks and sorted imports;
  made one doctest (`tests/support/layered.py::LayeredSandbox.apply_env`) self-contained with its
  own `from pathlib import Path` after the type-only import move.
- Replaced a magic `2` in `_is_quoted` with a named `_MIN_QUOTED_LENGTH` constant, `os.replace()`
  with `Path.replace()` in `examples/deploy.py`, and a non-raw regex anchor pattern in
  `tests/unit/test_testing.py` with a raw string.

## [5.6.0] - 2026-07-13

### Added

- Environment variables can now override a single element of a file-defined array by numeric index (e.g. `MYAPP___DATASET__0__DSN`), deep-merging that element while leaving the rest of the array intact; nested arrays and end-of-array appends are supported.
- Environment-variable values that open with `[` or `{` are parsed as JSON (arrays / objects).
- `read` and `read-json` gain `--redact/--no-redact` (default off) to mask secret-shaped values in output.
- A maximum config-file-size guard (10 MiB) raises `InvalidFormatError` on oversized structured files.
- Recursion-depth guards in merge and redaction raise `InvalidFormatError` instead of an opaque `RecursionError` on pathologically nested config.
- Ships a Claude Code skill and single-plugin marketplace (`skills/python-layered-config/`) that teaches an AI agent to install, use, and design configuration with the library across Linux, macOS, and Windows.
- `ai-stance.md` and `ai-transparency.md` (how the project is built and who answers for it), linked from the README.

### Changed

- `ValidationError` now subclasses both `ConfigError` and `ValueError` and is raised by identifier / platform / deploy-target validation, so failures are catchable as `ConfigError` (the documented boundary type) while remaining backward compatible with `except ValueError`.
- Redaction masks a broader set of secret-shaped keys (`apikey`, `aws_access_key_id`, `cookie`, `jwt`, any `_key` suffix, and more) while leaving a plain `key` field alone.
- Deploy targets and layer-permission lookups are consolidated on the `Layer` enum.
- README restructured: a concise overview, with the full CLI and Python API references moved to `docs/cli-reference.md` / `docs/python-api.md` and identifiers / file-structure to `docs/`. `docs/systemdesign/module_reference.md` slimmed to an architecture map.

### Fixed

- Deploying a kept-config `.ucf` sidecar now applies the same layer-appropriate permission hardening as the primary file (previously left at the umask default, which could expose secrets).
- Deploy writes go through an owner-only temp file plus atomic rename, closing a TOCTOU window in which a secret could be briefly world-readable.
- A numeric-key environment mapping over a nested array no longer flattens the inner array into a dict.
- Two YAML error-path tests that were silently always-skipped now run.

### Security

- Pruned all stale `pip-audit` exclusions; documented the single remaining one (`PYSEC-2026-2132` / `CVE-2026-7246`, the `click.edit()` CVE present only in the dev/CI toolchain).

## [5.5.2] - 2026-06-14

### Changed
- Added a `cli/typed_click.py` facade wrapping rich-click's `option` / `version_option` / `argument` decorators behind explicit, fully-known signatures, keeping the CLI strict-clean under pyright 1.1.410 (`reportUnknownMemberType`) without disabling the rule (ignore isolated to the facade).
- Bumped `lib_cli_exit_tools` floor to `>=2.3.2`.

## [5.5.1] - 2026-03-26

### Fixed

- Fixed TOML syntax error in `pyproject.toml` (missing comma in `ignore-vulns` array)

### Changed

- Updated CI/CD workflow: bumped upload/download artifact actions
- Added new CVE exclusions for transitive dependencies (`CVE-2026-1703`, `CVE-2026-25990`, `CVE-2026-26007`, `CVE-2026-4539`, `CVE-2026-25645`)

## [5.5.0] - 2026-02-24

### Added

- **Explicit dotenv file path**  -  New `dotenv_path` parameter for `read_config()`, `read_config_json()`, and `read_config_raw()` loads a specific `.env` file directly instead of searching upward from `start_dir`. CLI equivalent: `--env-file` flag on `read` and `read-json` commands.
- Added `__all__` exports to `domain/config.py`, `domain/permissions.py`, `domain/redaction.py`, and `cli/common.py`

### Changed

- Bumped dependency versions: `hypothesis>=6.151.9`, `ruff>=0.15.2`, `textual>=8.0.0`, `hatchling>=1.29.0`
- Updated Makefile to BMK 2.7.1 (adds `test-human` / `th` and `testintegration-human` / `tih` targets)
- Updated documentation: README (CLI + Python API for `--env-file`/`dotenv_path`), CLAUDE.md, module reference

### Fixed

- Fixed CI/CD runner configuration and bandit pyproject.toml reading
- Removed stale `scripts/` directory from CLAUDE.md project structure
- Fixed `orjson` version in CLAUDE.md to match pyproject.toml (`>=3.11.7`)

## [5.4.1] - 2026-02-13

### Changed

- Migrated build automation from `scripts/` Python modules to `bmk` CLI tool via `Makefile`
- Removed `scripts/` directory (~5,500 lines of internal build tooling no longer needed)
- Refactored GitHub Actions CI/CD workflow with extracted metadata action
- Updated Makefile to use `uvx bmk@latest` for all build, test, and release targets

### Fixed

- Fixed coverage measurement conflict between pytest-cov and bmk's external `coverage run` wrapper (replaced `--cov` addopts with `--no-cov` to let bmk manage coverage)
- Added CVE ignore entries for CVE-2026-26007, CVE-2026-25990, CVE-2026-1703

### Added

- DevContainer configuration for containerized development
- Bash 4+ compatibility for macOS CI environments

## [5.4.0] - 2026-01-31

### Added

- **Unix file permissions for deployed configuration files**  -  The `deploy_config()` function now automatically sets appropriate Unix file permissions based on the target layer. This ensures configuration files have the right access controls without manual `chmod` commands.

  **Default permissions by layer:**
| Layer  | Directory Mode      | File Mode           | Rationale                               |
|--------|---------------------|---------------------|-----------------------------------------|
| `app`  | `0o755` (rwxr-xr-x) | `0o644` (rw-r--r--) | System-wide config readable by all      |
| `host` | `0o755` (rwxr-xr-x) | `0o644` (rw-r--r--) | Machine-specific config readable by all |
| `user` | `0o700` (rwx------) | `0o600` (rw-------) | Private user config                     |

  **New parameters for `deploy_config()`:**
  - `set_permissions: bool = True`  -  Enable/disable permission setting (default: enabled)
  - `dir_mode: int | None = None`  -  Override directory mode for all targets
  - `file_mode: int | None = None`  -  Override file mode for all targets

  **CLI flag:**
  - `--permissions / --no-permissions`  -  Enable/disable permission setting (default: `--permissions`)

  **Platform behavior:**
  - Linux/macOS: Full permission support via `chmod()`
  - Windows: Permissions skipped (Windows uses ACLs, not Unix modes)

  **Example usage:**
  ```python
  from lib_layered_config import deploy_config

  # Default: layer-aware permissions
  deploy_config(source="config.toml", vendor="Acme", app="MyApp", targets=["user"], slug="myapp")
  # User layer files get 700/600 permissions

  # Custom permissions
  deploy_config(
      source="config.toml", vendor="Acme", app="MyApp", targets=["app"], slug="myapp", dir_mode=0o750, file_mode=0o640
  )

  # Disable permissions
  deploy_config(source="config.toml", vendor="Acme", app="MyApp", targets=["user"], slug="myapp", set_permissions=False)
  ```

- **Permission constants exported in public API**  -  Four permission mode constants are now available from the main package:
  - `DEFAULT_APP_DIR_MODE`  -  `0o755`
  - `DEFAULT_APP_FILE_MODE`  -  `0o644`
  - `DEFAULT_USER_DIR_MODE`  -  `0o700`
  - `DEFAULT_USER_FILE_MODE`  -  `0o600`

- **`domain/permissions.py` module**  -  New domain module containing:
  - `set_permissions()`  -  Apply layer-aware default permissions
  - `set_custom_permissions()`  -  Apply custom permission modes
  - `LAYER_PERMISSIONS`  -  Mapping of layer names to permission modes

- **Profile name length validation**  -  Profile names are now validated for length with configurable limits for security and filesystem safety.

  **Length limits:**
  - Default max length: 64 characters (`DEFAULT_MAX_PROFILE_LENGTH`)
  - Absolute max length: 256 characters (internal security hardening)
  - Even if `max_length` is set higher than 256, the 256 limit is enforced
  - Setting `max_length=0` or negative uses the absolute maximum (256 chars)

  **New public API exports:**
  - `DEFAULT_MAX_PROFILE_LENGTH`  -  Constant (64 characters)
  - `validate_profile_name(value, *, max_length=64)`  -  Raises `ValueError` on invalid
  - `is_valid_profile_name(value, *, max_length=64)`  -  Returns `bool`, no exception

  **New parameter for `deploy_config()`:**
  - `max_profile_length: int = 64`  -  Maximum allowed profile name length

  **Security checks include:**
  - Path traversal prevention (`../`, `..\\`, absolute paths)
  - Control character rejection (null bytes, newlines, tabs)
  - Windows reserved name blocking (CON, PRN, NUL, COM1-9, LPT1-9)
  - Non-ASCII character rejection (encoding attack prevention)
  - Must start with alphanumeric, no trailing dots/spaces

  **Example usage:**
  ```python
  from lib_layered_config import (
      validate_profile_name,
      is_valid_profile_name,
      DEFAULT_MAX_PROFILE_LENGTH,
  )

  # Validate with exception
  validate_profile_name("production")  # OK
  validate_profile_name("a" * 100)  # Raises ValueError

  # Check without exception
  if is_valid_profile_name(user_input):
      deploy_config(..., profile=user_input)

  # Custom max length
  validate_profile_name("long-profile-name", max_length=128)
  ```

### Changed

- **README restructured by theme**  -  The README now has a cleaner organization with sections grouped by theme:
  - Getting Started (Key Features, Installation, Quick Start)
  - Core Concepts (Identifiers, Profiles, File Structure, Precedence)
  - Command Line Interface (all CLI commands)
  - Python API (all API functions and classes)
  - Deployment & Security (permissions, security best practices, .d directories)
  - Reference (observability, architecture, development)

### Documentation

- **Comprehensive security best practices**  -  New README sections covering:
  - File permissions by layer with rationale
  - Recommended permissions for `.env` files (`0o600`)
  - macOS and Windows platform-specific considerations
  - Recommendations for sensitive data (env vars, secrets managers, redaction)

- **Updated CLAUDE.md**  -  Added File Permissions section with API parameters, CLI flags, platform behavior, and implementation file references

## [5.3.9] - 2026-01-29

### Changed

- **Refactored config display using rtoml serialization**  -  The `display_config()` function now uses `rtoml.dumps()` for TOML serialization instead of custom formatting logic, then applies Rich styling to the output. This produces more accurate TOML output that matches standard TOML conventions and simplifies the codebase.

### Internal

- Replaced manual value formatting with `rtoml.dumps()` followed by regex-based parsing and styling
- Removed `_is_flat_dict()`, `_format_raw_value()`, `_styled_entry()`, `_has_leaf_values()`, and `_print_section()` helper functions
- Added `_SECTION_PATTERN` and `_KEY_VALUE_PATTERN` regex constants for parsing TOML output
- New `_render_toml_with_styling()` function handles line-by-line styling of TOML output

## [5.3.8] - 2026-01-29

### Added

- **Explanatory header in human output**  -  `display_config()` now prints a bright red header comment at the start of human-readable output explaining that nested dictionaries are displayed as `[section.subsection]` headers and may not match the original TOML structure. This helps users understand TOML serialization behavior.

## [5.3.5] - 2026-01-29

### Added

- **Provenance tracking for empty dicts**  -  The merge logic now stores provenance metadata for empty dict values (e.g., `console_styles: {}`). This allows `display_config()` to show source comments for empty dicts, matching the behavior for scalar values. Previously, empty dicts had no provenance and displayed without source information.

### Changed

- **`Config.origin()` returns data for empty dicts**  -  The `origin()` method now returns `SourceInfo` for empty dict keys instead of `None`, providing consistent provenance lookup across all value types.

## [5.3.4] - 2026-01-29

### Changed

- **`OutputFormat` moved to application layer**  -  The `OutputFormat` enum is now defined in `application.ports` instead of `cli.common` to satisfy Clean Architecture layer constraints. Both `cli` and `adapters.display` can now import it without violating import rules. The enum remains exported from the package root.

- **Flat dicts rendered as inline tables**  -  `display_config()` now renders flat dicts (containing only primitive values, no nested dicts) as TOML inline tables (e.g., `scrub_patterns = { password = ".+", token = ".+" }`) instead of section headers. This matches the TOML source style and reduces visual noise.

### Fixed

- **Leaf values now appear under correct section header**  -  `display_config()` now prints all leaf values (scalars, lists, and flat dicts) for a section before recursing into nested subsections. Previously, values appearing after a nested dict in iteration order would visually appear under the subsection header (e.g., `rate_limit` appearing under `[lib_log_rich.scrub_patterns]` instead of `[lib_log_rich]`).

## [5.3.3] - 2026-01-29

### Changed

- **`display_config` styling refinement**  -  Adjusted color scheme for better readability: keys now use light brown (`orange3`), the `=` separator is white (previously dimmed), and all values use green (previously yellow for non-strings).

### Fixed

- **Empty sections no longer displayed**  -  `display_config()` now skips empty dict values (e.g., `console_styles = {}`) instead of creating meaningless section headers like `[section.empty_table]`. Sections with no leaf values at any nesting level are omitted from output.

## [5.3.2] - 2026-01-29

### Added

- **Rich-styled configuration display**  -  New `display_config()` function in `adapters.display` for enhanced configuration visualization with Rich console styling.

  **Features:**
  - Human-readable TOML-like output with color-coded display (light brown keys, white `=`, green values)
  - JSON output format with automatic redaction
  - Provenance comments showing layer, profile, and source file path for each value
  - Cyan section headers, yellow provenance comments
  - Automatic redaction of sensitive values (passwords, tokens, secrets, API keys) displayed in dim red

  **Usage:**
  ```python
  from lib_layered_config import read_config, display_config, OutputFormat

  config = read_config(vendor="Acme", app="MyApp", slug="myapp")
  display_config(config)  # Human-readable output
  display_config(config, output_format=OutputFormat.JSON)  # JSON output
  display_config(config, section="database")  # Display specific section only
  ```

- **`OutputFormat` enum exported**  -  The `OutputFormat` enum (`OutputFormat.HUMAN`, `OutputFormat.JSON`) is now available from the main package for use with `display_config()`.

## [5.3.1] - 2026-01-28

### Changed
- **Provenance layer serialization**  -  `_store_scalar()` in `application/merge.py` now extracts the string `.value` from `Layer` enum instances before storing in the provenance dict. Previously, a `Layer` enum object could end up in the `"layer"` field, causing issues during JSON serialization

## [5.3.0] - 2026-01-27

### Added
- **Redaction support** - `Config.to_json(redact=True)` and `Config.as_dict(redact=True)` mask sensitive configuration values (passwords, tokens, secrets, API keys, credentials, private keys) with `***REDACTED***`. Prevents accidental exposure of secrets in logs, CLI output, or JSON exports.
- **`redact_mapping()` function** - Public domain function for recursive redaction of sensitive values in configuration dictionaries.
- **`is_sensitive()` predicate** - Public function to test whether a configuration key name matches known sensitive patterns.
- **`REDACTED_PLACEHOLDER` constant** - The `***REDACTED***` string used as replacement, exported for consumer use.
- **`orjson` as a production dependency** - Added `orjson>=3.11.5` for faster JSON serialization/deserialization.
- **`httpx` as a dev dependency** - Added `httpx>=0.28.0`, replacing `urllib` in development scripts.

### Changed
- `Config.with_overrides()` now performs **deep recursive merge** instead of
  shallow top-level replacement. Nested dict keys are preserved when overriding
  a sub-key. Non-mapping values (scalars, lists) are still replaced entirely.
- **TOML-style human-readable output**  -  `render_human()` now produces
  `[section.subsection]` headers and `key = value` lines instead of flat
  dotted-path listings. Provenance is shown as `# source:` comments above
  each setting. Strings are double-quoted, lists use JSON array syntax.
- Replaced stdlib `json` with `orjson` for JSON serialization/deserialization across all production modules (`domain/config.py`, `core.py`, `cli/common.py`, `cli/deploy.py`, `adapters/file_loaders/structured.py`).

### Fixed
- **import-linter contracts**  -  Fixed `make test` to invoke `lint-imports` CLI
  instead of a no-op `python -m importlinter.cli lint` command. Updated layers
  contract to use `containers` parameter (required by grimp v3.14). Corrected
  forbidden contract field name from `modules` to `source_modules`.
- `Config.to_json()` now uses orjson; the `indent` parameter always produces 2-space indent when set (orjson limitation).
- `Config.to_json()` gains `redact: bool = False` parameter.
- `Config.as_dict()` gains `redact: bool = False` parameter.
- `read_config_json()` gains `redact: bool = False` parameter.
- Replaced `tomllib`/`tomli` with `rtoml` in test suite (`tests/test_metadata.py`) for consistency with production TOML parser.
- Replaced `urllib` with `httpx` in `scripts/dependencies.py` for PyPI API requests.

## [5.2.1] - 2026-01-19

### Changed

- Removed unused `ctx.obj["traceback"]` storage in CLI root command. The `--traceback` flag continues to work via `_session_overrides()` which passes the flag to `lib_cli_exit_tools.cli_session`.

### Security

- Cleaned up pip-audit ignore list: removed `CVE-2025-68146` (filelock) which is no longer present in dependencies

## [5.2.0] - 2025-12-29

### Added

- **UNC path documentation and tests** - Documented support for UNC network paths (e.g., `//server/share`) in Windows path resolution. UNC paths are handled natively by `pathlib.Path` and can be configured via environment variable overrides.

  **Environment variables supporting UNC paths:**
  - `LIB_LAYERED_CONFIG_PROGRAMDATA` - Override for app-layer paths
  - `LIB_LAYERED_CONFIG_APPDATA` - Override for user-layer paths (roaming)
  - `LIB_LAYERED_CONFIG_LOCALAPPDATA` - Override for user-layer paths (local fallback)

  **Example:**
  ```bash
  export LIB_LAYERED_CONFIG_PROGRAMDATA="//fileserver/configs"
  ```

- **Cross-platform path handling documentation** - Added documentation noting that all path handling uses `pathlib.Path` for cross-platform compatibility.

### Changed

- Updated `_windows.py` module and class docstrings with UNC path support details
- Updated `_base.py` module docstring with cross-platform path handling note
- Reduced cyclomatic complexity in `cli/deploy.py`, `domain/identifiers.py`, and `examples/deploy.py` by extracting helper functions

### Fixed

- Fixed broken reference to non-existent `AGENTS.md` in `CONTRIBUTING.md` (now correctly references `CLAUDE.md`)

### Security

- Added `CVE-2025-68146` (filelock race condition) to pip-audit ignore list as accepted risk for transitive dependency

## [5.1.0] - 2025-12-13

### Added

- **`.d` directory expansion for configuration files** - Any configuration file now automatically discovers and merges files from a companion `.d` directory. This follows the pattern used by `/etc/apt/sources.list.d/` and similar Unix conventions.

  **Naming Convention:** The `.d` directory name is derived by replacing the file extension with `.d`:
  - `config.toml` → `config.d/`
  - `config.yaml` → `config.d/`
  - `config.json` → `config.d/`

  This design allows all formats to share the same companion directory and enables mixed format files within a single `.d` directory.

  **Features:**
  - Files in the `.d` directory are sorted lexicographically (e.g., `10-database.toml`, `20-cache.toml`)
  - Both the base file and `.d` directory are optional (either can exist independently)
  - Provenance tracks which specific `.d` file provided each configuration value
  - Supports mixed formats in the same `.d` directory (TOML, YAML, JSON)
  - Non-config files (e.g., `README.md`) are automatically ignored
  - Works at all layers: defaults, app, host, user

  **Example directory structure:**
  ```
  /etc/xdg/myapp/
  ├── config.toml              # Base configuration
  └── config.d/                # Companion .d directory
      ├── 10-database.toml     # Merged second
      ├── 20-cache.yaml        # Merged third (mixed formats OK)
      └── 30-logging.json      # Merged fourth
  ```

  **Merge order:** `config.toml` → `10-database.toml` → `20-cache.yaml` → `30-logging.json`

  **Usage example:**
  ```python
  from lib_layered_config import read_config

  # Automatically reads config.toml + config.d/* files
  config = read_config(vendor="Acme", app="MyApp", slug="myapp")

  # Provenance shows which .d file provided each value
  print(config.origin("database.host"))
  # → {"layer": "app", "path": "/etc/xdg/myapp/config.d/10-database.toml", "key": "database.host"}
  ```

- **`expand_dot_d()` function** - New public function in `adapters.file_loaders` for expanding a config file path to include `.d` directory entries. Useful for advanced use cases where direct control over file expansion is needed.

- **`_note_dot_d_expanded()` logging helper** - New observability helper that logs when `.d` expansion occurs with the count of additional files discovered.

- **`.d` directory support in `deploy_config`** - The `deploy_config` function now automatically detects and deploys companion `.d` directories. When deploying `config.toml`, if `config.d/` exists, its contents are also deployed to the corresponding `.d` directory at each destination.

  **Key behaviors:**
  - Deployment is **additive**: user-added files in the destination `.d` directory are preserved
  - Smart skip and backup functionality applies to `.d` files (identical to base file handling)
  - ALL files from source `.d` are copied (including README.md, notes.txt) to preserve documentation
  - Only config file parsing filters by extension; deployment copies everything

  **Best practice:** Override settings in a separate file (e.g., `90-local-overrides.toml`) instead of modifying distributed config files. This ensures customizations survive re-deployments.

  **JSON output fields for .d results:**
  - `dot_d_created`: Paths of .d files created
  - `dot_d_overwritten`: Paths of .d files overwritten
  - `dot_d_skipped`: Paths of .d files skipped (identical content)
  - `dot_d_backups`: Paths of .d backup files created

### Internal

- Added `adapters/file_loaders/_dot_d.py` module for `.d` directory expansion logic
- Modified `_layers._load_entry_with_dot_d()` to integrate `.d` expansion into the layer loading pipeline
- Updated `adapters/path_resolvers/_base.collect_layer()` to yield `config.toml` when `config.d/` directory exists (even if base file is missing)
- Added comprehensive test suites: `tests/adapters/test_dot_d.py` (15 unit tests) and `tests/e2e/test_dot_d_integration.py` (9 E2E tests)

## [5.0.0] - 2025-12-11

### Added

- **5x faster TOML parsing with rtoml** - Switched from stdlib `tomllib` to `rtoml` (Rust-based TOML parser) as the default parser. Benchmarks show ~5x faster parsing across all config sizes:
  - 1KB config: 0.15ms → 0.03ms
  - 17KB config: 2.9ms → 0.55ms
  - 60KB config: 8.3ms → 1.6ms

- **LRU caching for identifier validation** - Added `@lru_cache` to validation functions (`validate_identifier`, `validate_vendor_app`, `validate_hostname`) to avoid redundant validation when reading config multiple times with the same identifiers.

- **Smart skipping for `deploy` command** - When deploying a configuration file, the command now compares the source content with the existing destination file byte-by-byte. If the content is identical, the deployment is skipped without creating backup files. This prevents unnecessary `.bak` file proliferation when repeatedly deploying unchanged configurations.

  **Behavior:**
  - Applies to all modes: `--force`, `--batch`, and interactive
  - Uses exact byte comparison (whitespace differences are detected)
  - File modification time is preserved when skipped
  - JSON output reports `"skipped"` for identical content

  **Example:**
  ```bash
  # First deploy creates the file
  $ lib_layered_config deploy --source config.toml --vendor Acme --app Demo --slug demo --target app
  {"created": ["/etc/xdg/demo/config.toml"]}

  # Second deploy with same content skips (no backup created)
  $ lib_layered_config deploy --source config.toml --vendor Acme --app Demo --slug demo --target app --force
  {"skipped": ["/etc/xdg/demo/config.toml"]}

  # Deploy with different content creates backup and overwrites
  $ lib_layered_config deploy --source config-v2.toml --vendor Acme --app Demo --slug demo --target app --force
  {"overwritten": ["/etc/xdg/demo/config.toml"], "backups": ["/etc/xdg/demo/config.toml.bak"]}
  ```

- **`_content_matches()` helper** - New internal function in `examples/deploy.py` for byte-exact content comparison between source payload and destination file.

### Changed

- **TOML parser dependency** - Replaced `tomllib`/`tomli` with `rtoml` as the default TOML parser. This is a Rust-based parser that provides significant performance improvements while maintaining full TOML 1.0 compatibility.

### Removed

- **Deprecated internal shim functions** - Removed unused compatibility shims from `examples/deploy.py`:
  - Platform-specific destination helpers (`_linux_destination_for`, `_mac_destination_for`, `_windows_destination_for`)
  - Platform-specific path helpers (`_linux_app_path`, `_mac_app_path`, `_windows_app_path`, etc.)
  - Legacy helper functions (`_should_copy`, `_ensure_path`)

  These internal functions were replaced by the `DeploymentStrategy` class hierarchy and `_deploy_single()` function.

## [4.2.0] - 2025-12-11

### Added

- **Interactive conflict handling for `deploy` command** - When a destination file exists, the deploy command now offers two options:
  - **Keep existing** (`k`) - Save new config as `.ucf` (Update Configuration File), preserving the original  -  **default**
  - **Overwrite** (`o`) - Backup original to `.bak`, then write new file

- **`--batch` flag for `deploy` command** - Non-interactive mode that keeps existing files and writes new config as `.ucf` for manual review. Suitable for CI/CD pipelines and scripts where user customizations must be preserved.

- **Automatic backup creation** - When using `--force` or choosing "Overwrite", the existing file is backed up to `.bak` before being replaced.

- **Numbered suffix handling** - If `.bak` or `.ucf` files already exist, uses numbered suffixes (`.bak.1`, `.bak.2`, etc.) to avoid overwriting previous backups.

- **`DeployAction` enum** - New enum in `examples.deploy` tracking deployment outcomes: `CREATED`, `OVERWRITTEN`, `KEPT`, `SKIPPED`.

- **`DeployResult` dataclass** - Rich return type from `deploy_config()` providing:
  - `destination`: Target path
  - `action`: What action was taken (`DeployAction`)
  - `backup_path`: Path to backup file (if action was `OVERWRITTEN`)
  - `ucf_path`: Path to UCF file (if action was `KEPT`)

- **`ConflictResolver` callback type** - New type alias for custom conflict resolution callbacks: `Callable[[Path], DeployAction]`.

### Changed

- **`deploy_config()` return type** - Now returns `list[DeployResult]` instead of `list[Path]`. The destination paths are accessible via `result.destination`.

  **Breaking Change:** Update code that uses the return value:
  ```python
  # Before
  paths = deploy_config(source, vendor="V", app="A", targets=["app"], slug="s")
  for path in paths:
      print(f"Created: {path}")

  # After
  results = deploy_config(source, vendor="V", app="A", targets=["app"], slug="s")
  for result in results:
      print(f"{result.action.value}: {result.destination}")
  ```

- **`deploy_config()` signature** - Added new parameters:
  - `batch: bool = False` - Keep existing and write new as `.ucf` for review
  - `conflict_resolver: ConflictResolver | None = None` - Custom callback for conflict resolution

## [4.1.1] - 2025-12-11

### Documentation

- **Fixed error class names in system design docs** - Updated `concept.md` and `module_reference.md` to use actual class names (`InvalidFormatError`, `NotFoundError`) instead of shorthand (`InvalidFormat`, `NotFound`).

- **Improved `with_overrides` limitation documentation** - Added code example and rationale explaining why shallow (top-level) merge is intentional, covering provenance tracking, Clean Architecture, and use case fit. Added workaround guidance for deep override needs.

- **Clarified tomllib/tomli fallback** - Updated documentation to explicitly note `tomllib` (stdlib 3.11+) with `tomli` fallback for Python 3.10.

## [4.1.0] - 2025-12-11

### Added

- **Python 3.10+ compatibility** - The library now supports Python 3.10, 3.11, 3.12, and 3.13. Previously required Python 3.13+.
  - Added `tomli` as a conditional dependency for Python < 3.11 (provides TOML parsing before `tomllib` was added to stdlib)
  - CI matrix now tests against Python 3.10, 3.11, 3.12, 3.13, and latest 3.x

- **`parse_output_format()` function** - New CLI helper in `cli/common.py` that converts string input to `OutputFormat` enum at the CLI boundary, following the data architecture principle of parsing at system edges.

### Changed

- **`wants_json()` signature** - Now accepts only `OutputFormat` enum instead of `str | OutputFormat`. String-to-enum conversion should happen at the CLI boundary using `parse_output_format()`.

## [4.0.1] - 2025-12-08

### Changed

- **Data architecture enforcement** - Replaced magic string literals with named constants and enums throughout the codebase:
  - Added `OutputFormat` enum in CLI for type-safe output format selection (`json` vs `human`)
  - Added `_BOOL_TRUE`, `_BOOL_FALSE`, `_BOOL_LITERALS`, `_NULL_LITERALS` constants in env adapter
  - Added `_QUOTE_CHARS`, `_COMMENT_CHAR`, `_INLINE_COMMENT_DELIMITER`, `_KEY_VALUE_DELIMITER` constants in dotenv adapter
  - Added `NESTED_KEY_DELIMITER` constant for the `__` separator in nested key parsing

### Internal

- **Test suite refactoring** - Enhanced test architecture following clean code principles:
  - Centralized shared fixtures in `tests/conftest.py` (sandbox variants, CLI runner, source file fixtures)
  - Added `tests/unit/test_coverage_edge_cases.py` with 11 new laser-focused edge case tests
  - Improved test coverage from 97.88% to 98.49%
  - All tests now use real behavior over mocks where possible
  - Consistent OS-specific marking throughout (`@os_agnostic`, `@windows_only`, etc.)

## [4.0.0] - 2025-12-01

### Changed

- **Exception names follow PEP 8 convention** - Exception classes now use the `Error` suffix as recommended by PEP 8:
  - `InvalidFormat` → `InvalidFormatError`
  - `NotFound` → `NotFoundError`

  **Breaking Change:** The old names (`InvalidFormat`, `NotFound`) have been removed. Update your imports:

  ```python
  # Before
  from lib_layered_config import InvalidFormat, NotFound

  # After
  from lib_layered_config import InvalidFormatError, NotFoundError
  ```

- **Docstring style changed to Google format** - All docstrings throughout the codebase have been converted from NumPy style to Google style for consistency and wider compatibility.

  **Before (NumPy style):**
  ```python
  def func(value):
      """Short summary.

      Parameters
      ----------
      value : str
          Description of value.

      Returns
      -------
      bool
          Description of return value.
      """
  ```

  **After (Google style):**
  ```python
  def func(value):
      """Short summary.

      Args:
          value: Description of value.

      Returns:
          Description of return value.
      """
  ```

- **Configured `pydocstyle` convention** - Added `[tool.ruff.lint.pydocstyle]` with `convention = "google"` to `pyproject.toml` to enforce consistent docstring formatting.

### Internal

- Reduced cyclomatic complexity in `domain/identifiers.py` by extracting validation helper functions (`_check_not_empty`, `_check_ascii_only`, `_check_no_invalid_chars`, etc.).
- Modernized type annotations: replaced `typing.List`, `typing.Tuple`, `typing.Optional` with built-in `list`, `tuple`, and `X | None` syntax.
- Moved `Iterable`, `Iterator`, `Mapping`, `Sequence` imports from `typing` to `collections.abc`.
- Added docstrings to all Protocol methods in `application/ports.py`.
- Added docstrings to deployment strategy classes and methods in `examples/deploy.py`.
- Simplified `_should_copy()` function in `examples/deploy.py` (SIM103).
- Removed unused imports across CLI modules.

## [3.1.0] - 2025-12-01

### Added

- **Configuration profiles** - New `profile` parameter for `read_config()`, `read_config_json()`, `read_config_raw()`, and `deploy_config()` functions. Profiles allow organizing environment-specific configurations (e.g., `test`, `staging`, `production`) into isolated subdirectories. When specified, all configuration paths include a `profile/<name>/` segment.

  **Example paths with `profile="production"`:**
  - Linux: `/etc/xdg/<slug>/profile/production/config.toml`
  - macOS: `/Library/Application Support/<vendor>/<app>/profile/production/config.toml`
  - Windows: `C:\ProgramData\<vendor>\<app>\profile\production\config.toml`

- **CLI `--profile` option** - Added `--profile` option to `read`, `read-json`, and `deploy` commands.

  ```bash
  lib_layered_config read --vendor Acme --app MyApp --slug myapp --profile production
  lib_layered_config deploy --source config.toml --vendor Acme --app MyApp --slug myapp --profile test --target app
  ```

- **`validate_profile()` function** - New validation function in `domain/identifiers.py` for sanitizing profile names.

- **`validate_path_segment()` function** - New centralized validation function for all filesystem path segments.

- **`validate_vendor_app()` function** - New validation function for vendor/app that allows spaces (for macOS/Windows paths like `/Library/Application Support/Acme Corp/My App/`).

### Changed

- **Enhanced identifier validation** - All identifiers are now validated with comprehensive cross-platform filesystem safety rules:

  **Validation by Type:**
| Identifier | Spaces Allowed | Notes                       |
|------------|----------------|-----------------------------|
| `vendor`   | OK Yes         | For macOS/Windows paths     |
| `app`      | OK Yes         | For macOS/Windows paths     |
| `slug`     | NO No          | Linux paths, env var prefix |
| `profile`  | NO No          | Profile subdirectory        |
| `hostname` | NO No          | Host-specific files         |

  **Common Rules (All Identifiers):**
  - ASCII-only characters (no UTF-8/Unicode)
  - Must start with alphanumeric character (a-z, A-Z, 0-9)
  - No path separators (`/`, `\`)
  - No Windows-invalid characters (`<`, `>`, `:`, `"`, `|`, `?`, `*`)
  - No Windows reserved names (CON, PRN, AUX, NUL, COM1-9, LPT1-9)
  - Cannot end with dot or space (Windows restriction)

  **Examples:**
  ```python
  # OK Valid
  vendor = "Acme Corp"  # Spaces OK in vendor
  app = "Btx Fix Mcp"  # Spaces OK in app
  slug = "my-app"  # No spaces in slug
  profile = "production"  # No spaces in profile

  # NO Invalid (raises ValueError)
  "../etc"  # Path traversal
  "café"  # Non-ASCII
  "CON"  # Windows reserved
  slug = "my app"  # Slug cannot have spaces
  ".hidden"  # Starts with dot
  "app<test>"  # Windows-invalid character
  ```

## [3.0.1] - 2025-11-30

### Added

- **`Layer` enum** - New type-safe enumeration for configuration layer names (`Layer.DEFAULTS`, `Layer.APP`, `Layer.HOST`, `Layer.USER`, `Layer.DOTENV`, `Layer.ENV`). The enum values are strings, so they work seamlessly with existing code and provenance dictionaries.

- **Type conflict warnings** - When a later configuration layer overwrites a scalar value with a mapping (or vice versa), a warning is now logged. This helps identify configuration mismatches where a key changes type across layers.

- **Input validation for identifiers** - The `vendor`, `app`, and `slug` parameters are now validated to prevent path traversal attacks. Values containing `/`, `\`, or starting with `.` will raise `ValueError`.

- **Hostname sanitization** - Hostnames used in path resolution are now validated to prevent path traversal via malicious hostname values.

### Changed

- **`MergeResult` dataclass** - The merge function now returns a `MergeResult` dataclass with `data` and `provenance` attributes instead of a tuple, improving code clarity.

- **Observability module** - Added `log_warn()` function for structured warning logs with trace context.

### Internal

- Consolidated duplicate nested-key iteration logic into `adapters/_nested_keys.py`.
- Reduced cyclomatic complexity in `DefaultPathResolver` using Strategy pattern.
- Trimmed verbose docstrings to improve maintainability index scores.

## [3.0.0] - 2025-11-25

### Breaking Changes

- **Environment variable prefix format changed** - The environment variable prefix now uses triple underscore (`___`) as the separator between the slug prefix and configuration keys, instead of a single underscore. This change clearly distinguishes the application prefix from section/key separators (which use double underscores `__`).

  **Before (v2.x):**
  ```bash
  # Slug: "myapp" → Prefix: "MYAPP_"
  MYAPP_DATABASE__HOST=localhost
  MYAPP_DATABASE__PORT=5432
  MYAPP_SERVICE__TIMEOUT=30
  ```

  **After (v3.0):**
  ```bash
  # Slug: "myapp" → Prefix: "MYAPP___"
  MYAPP___DATABASE__HOST=localhost
  MYAPP___DATABASE__PORT=5432
  MYAPP___SERVICE__TIMEOUT=30
  ```

### Why This Change?

The new format makes it unambiguous where the prefix ends and the configuration path begins:
- `PREFIX___SECTION__SUBSECTION__KEY=value`
- Triple underscore (`___`) = prefix separator
- Double underscore (`__`) = nesting separator

This eliminates potential confusion when slugs contain underscores (e.g., `my_app` would have been `MY_APP_DATABASE__HOST`, making it unclear if `APP` was part of the prefix or a section name).

### Migration Guide

1. **Update all environment variables** - Add an extra two underscores after your prefix:
   - `MYAPP_DATABASE__HOST` → `MYAPP___DATABASE__HOST`
   - `CONFIG_KIT_SERVICE__TIMEOUT` → `CONFIG_KIT___SERVICE__TIMEOUT`

2. **Update shell scripts** - If you use `env-prefix` CLI command, note that it now returns the prefix with the trailing `___`:
   ```bash
   # Before: returns "MYAPP"
   # After: returns "MYAPP___"
   prefix=$(lib_layered_config env-prefix myapp)
   export ${prefix}DATABASE__HOST=localhost  # No extra underscore needed
   ```

3. **Update Python code** - If you use `default_env_prefix()`:
   ```python
   from lib_layered_config import default_env_prefix

   prefix = default_env_prefix("myapp")  # Returns "MYAPP___"
   os.environ[f"{prefix}DATABASE__HOST"] = "localhost"  # No extra underscore
   ```

### Changed

- `default_env_prefix()` now returns the slug in uppercase followed by `___` (e.g., `"MYAPP___"`)
- `_normalize_prefix()` ensures prefixes end with `___` instead of `_`
- CLI `env-prefix` command output now includes the `___` suffix
- Example `.env` templates now use the new format

### Documentation

- Updated README.md with new prefix format throughout all examples
- Updated all environment variable examples to use `PREFIX___SECTION__KEY` format
- Added explanation of why triple underscore was chosen as the separator

## [2.0.0] - 2025-11-20

### Breaking Changes

- **XDG Base Directory Specification compliance on Linux** - System-wide application configuration now defaults to `/etc/xdg/{slug}/` instead of `/etc/{slug}/` to follow the XDG Base Directory Specification.

### Changed

- **Path resolution (Linux)**: The path resolver now checks both `/etc/xdg/{slug}/` (XDG-compliant, checked first) and `/etc/{slug}/` (legacy, fallback) when reading configuration. This provides backward compatibility with existing installations.
- **Deployment (Linux)**: The `deploy_config()` function and `deploy` CLI command now deploy application-level configuration to `/etc/xdg/{slug}/config.toml` by default on Linux systems.
- **Host configuration (Linux)**: Host-specific configuration now deploys to `/etc/xdg/{slug}/hosts/{hostname}.toml` instead of `/etc/{slug}/hosts/{hostname}.toml`.
- **Example generation (Linux/POSIX)**: The `generate_examples()` function now creates example files in `xdg/{slug}/` for system-wide configuration and `home/{slug}/` for user-level configuration.

### Migration Guide

**For existing installations:**
- Configurations in `/etc/{slug}/` will continue to work (backward compatibility)
- New deployments will use `/etc/xdg/{slug}/`
- To migrate: move existing files from `/etc/{slug}/` to `/etc/xdg/{slug}/`
- Both locations are checked during reading, with `/etc/xdg/{slug}/` taking precedence

**Platform-specific behavior:**
- Linux: Uses `/etc/xdg/{slug}/` (system-wide) and `~/.config/{slug}/` (user-level)
- macOS: No change, continues to use `/Library/Application Support/{vendor}/{app}/`
- Windows: No change, continues to use `%ProgramData%\{vendor}\{app}\`

### Documentation

- Updated README.md with XDG-compliant paths throughout all examples
- Added backward compatibility notes explaining dual-path checking
- Updated all CLI command examples to reflect new default paths

## [1.1.1] - 2025-11-11

### Documentation

- **Major README enhancement** - Expanded from 787 to 2,800+ lines with comprehensive documentation for all functions, CLI commands, and parameters.

#### New Sections Added

- **Understanding Key Identifiers: Vendor, App, and Slug** - Detailed explanation of the three identifiers, their purposes, platform-specific usage, and naming best practices. Includes cross-platform path examples for Linux, macOS, and Windows.

- **Configuration File Structure** - Complete 200+ line example TOML configuration file demonstrating:
  - Top-level keys, sections, and nested sections
  - Arrays and all supported data types (strings, integers, floats, booleans, dates)
  - Real-world configuration patterns (database, service, logging, API, cache, email, monitoring)
  - Access patterns showing Python code, CLI usage, and environment variable mapping
  - Equivalent JSON and YAML representations

- **File Overwrite Behavior** - Comprehensive explanation of the `deploy` command's safe-by-default behavior:
  - Default behavior: creates new files, handles conflicts interactively (protects user customizations)
  - Force flag behavior: backs up existing files and overwrites
  - Visual decision flow diagram
  - 4 practical scenarios with examples
  - Best practices (DO's and DON'Ts) for safe deployment
  - Python API equivalents

#### Enhanced API Documentation

- **Config Class Methods** (6 methods, 23 examples):
  - `get()`: 3 examples showing basic lookups, handling missing keys, and deep nested paths
  - `origin()`: 3 examples for provenance checking, debugging precedence, and security validation
  - `as_dict()`: 2 examples for serialization and testing
  - `to_json()`: 2 examples for pretty-printing and compact output
  - `with_overrides()`: 2 examples for environment-specific configs and feature flags
  - `[key]` access: 2 examples for direct access and iteration

- **Core Functions** (7 functions, 31 examples):
  - `read_config()`: 5 examples from basic usage to complete production setup
  - `read_config_json()`: 3 examples for APIs, audit tools, and logging
  - `read_config_raw()`: 3 examples for templates, validation, and runtime overrides
  - `default_env_prefix()`: 3 examples for documentation generation and validation
  - `deploy_config()`: 5 examples for system-wide, user-specific, and host-specific deployment
  - `generate_examples()`: 5 examples including CI/CD validation
  - `i_should_fail()`: Testing error handling example

#### Enhanced CLI Documentation

Each CLI command now includes:
- Detailed parameter tables with type, required status, default values, and valid choices
- 4-6 real-world examples per command with expected outputs
- Clear explanations of when and why to use each example

- **`read` command**: 6 examples covering human-readable output, JSON for automation, provenance auditing, format preferences, defaults files, and debugging with environment variables

- **`deploy` command**: 6 examples for installation, user configuration, multiple targets, cross-platform deployment, host-specific configs, and safe deployment patterns

- **`generate-examples` command**: 6 examples for documentation generation, cross-platform support, updates, CI/CD validation, and onboarding workflows

- **`env-prefix` command**: 4 examples for checking prefixes, generating documentation, validation scripts, and test environment setup

- **`read-json` command**: Enhanced with API endpoint and audit tool examples

#### Parameter Documentation Improvements

All functions and CLI commands now document:
- Complete parameter lists with types (string, path, bool, int, etc.)
- Required vs. optional status clearly marked
- Default values explicitly stated
- Valid values for all choice/enum parameters (e.g., "app", "host", "user" for targets; "posix", "windows" for platforms)
- Return types and error conditions
- Platform-specific behaviors

#### Additional Improvements

- Updated Table of Contents to include all new sections
- Added environment variable naming pattern documentation with examples
- Included visual structure diagrams showing nested configuration as JSON
- Cross-referenced Python API and CLI equivalents throughout
- Added security considerations (e.g., where to store secrets)
- Included integration examples with Flask, jq, pytest, and other tools

## [1.1.0] - 2025-10-13

- Refactor CLI metadata commands (`info`, `--version`) to read from the
  statically generated `__init__conf__` module, removing runtime
  `importlib.metadata` lookups.
- Update CLI entrypoint to use `lib_cli_exit_tools.cli_session` for traceback
  management, keeping the shared configuration in sync with the newer
  `lib_cli_exit_tools` API without manual state restoration.
- Retire the `lib_layered_config.cli._default_env_prefix` compatibility export;
  import `default_env_prefix` from `lib_layered_config.core` instead.
- Refresh dependency baselines to the latest stable releases (rich-click 1.9.3,
  codecov-cli 11.2.3, PyYAML 6.0.3, ruff 0.14.0, etc.) and mark dataclasses with
  `slots=True` where appropriate to embrace Python 3.13 idioms.
- Simplify the CI notebook smoke test to rely on upstream nbformat behaviour,
  dropping compatibility shims for older notebook metadata schemas.

## [1.0.0] - 2025-10-09

- Add optional `default_file` support to the composition root and CLI so baseline configuration files load ahead of layered overrides.
- Refactor layer orchestration into `lib_layered_config._layers` to keep `core.py` small and more maintainable.
- Align Windows deployment with runtime path resolution by honouring `LIB_LAYERED_CONFIG_APPDATA` even when the directory is missing and falling back to `%LOCALAPPDATA%` only when necessary.
- Expand the test suite to cover CLI metadata helpers, layer fallbacks, and default-file precedence; raise the global coverage bar to 90%.
- Document the `default_file` usage pattern in the README and clarify that deployment respects the same environment overrides as the reader APIs.
- Raise the minimum supported Python version to 3.13; retire the legacy Conda, Nix, and Homebrew automation in favour of the PyPI-first build (now verified via pipx/uv in CI).

## [0.1.0] - 2025-09-26
- Implement core layered configuration system (`read_config`, immutable `Config`, provenance tracking).
- Add adapters for OS path resolution, TOML/JSON/YAML loaders, `.env` parser, and environment variables.
- Provide example generators, logging/observability helpers, and architecture enforcement via import-linter.
- Reset packaging manifests (PyPI, Conda, Nix, Homebrew) to the initial release version with Python ≥3.12.
- Refine the CLI into micro-helpers (`deploy`, `generate-examples`, provenance-aware `read`) with
  shared traceback settings and JSON formatting utilities.
- Bundle `tomli>=2.0.1` across all packaging targets (PyPI, Conda, Brew, Nix) so Python 3.10 users
  receive a TOML parser without extra steps; newer interpreters continue to use the stdlib module.
