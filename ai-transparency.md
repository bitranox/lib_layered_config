# AI transparency

The author and owner of this project is the human, [@bitranox](https://github.com/bitranox).
Every design and engineering decision is theirs, and they answer for everything published here.
An AI assistant (Claude, run through the Claude Code CLI) was used as a tool along the way,
mostly for the typing and the legwork under that direction. This page says where, plainly, so
you can weigh the work on its merits. The reasoning behind working this way is in
[ai-stance.md](ai-stance.md).

## The human's work

The shape of this software is the human's, start to finish. They set the problem, made every
call, and own the result.

- The problem is theirs: configuration that arrives from many places at once - bundled
  defaults, a system file, a per-host override, the user's own config, a `.env`, and
  environment variables - across Linux, macOS and Windows, with no honest answer to the one
  question that matters when something is wrong: which layer set this value, and from where.
  lib_layered_config resolves all of that into a single immutable object that can name the
  source of every key.
- Every design and architecture decision was the human's: the fixed six-layer precedence
  (`defaults -> app -> host -> user -> dotenv -> env`) deep-merged into one frozen `Config`;
  provenance tracking, so every key reports the layer and file it came from; the Clean
  Architecture split (domain / application / adapters / cli) with import-linter contracts that
  fail the build if a dependency points the wrong way; cross-platform path discovery (XDG on
  Linux, Application Support on macOS, ProgramData on Windows) with environment overrides for
  tests; configuration profiles for environment-specific trees; the `.d` split-config pattern
  with mixed TOML / YAML / JSON in one directory; deployment to the app, host and user layers
  with backup (`.bak`) and UCF (`.ucf`) conflict handling that protects a user's own edits;
  layer-appropriate Unix permission hardening on deploy; redaction of secret-shaped keys in
  output; and strict profile-name validation against path traversal, control characters and
  reserved names. Where there were options, the human picked.
- The dependency choices were the human's: `rtoml` and `orjson` (both Rust-backed) for fast
  parsing and serialization, `rich-click` and `lib_cli_exit_tools` for the CLI, and keeping YAML
  behind an optional extra so the default footprint stays small.
- The human reviewed and corrected the work at each step; what ships is what they signed off on.
- Every commit and every release went out under the human's name and authority, with no AI
  co-author line. The human is responsible for what is published to PyPI and GitHub.

## Where the AI was used

As a tool, under the human's direction, it did the mechanical parts: writing the domain model,
the merge and precedence logic, the adapters (file loaders, dotenv, environment, path
resolvers), the CLI commands, these docs and the tests to the human's design; laying out the
options at each fork for the human to choose from; and grinding through the cross-platform edge
cases a single code path has to get right (per-OS config directories, path separators,
permission handling that is a no-op on Windows, optional-dependency guards for YAML). It ran the
full gate repeatedly while iterating and fixed the lint, type-check and test failures it
surfaced; investigated reported behaviour - for example, that an environment variable with a
numeric segment did not override an array element the way the documentation implied - and
proposed fixes for the human to accept or redirect; and wrote the README, changelog entries and
module reference to the human's structure. None of the decisions, and none of the
accountability, were the AI's - the human directed and approved every action and owns the result.

## What's been checked, and what hasn't

`make test` runs the full gate: ruff (lint and format), pyright in strict mode, bandit, the
import-linter architecture contracts, the test suite under coverage, and pip-audit. The suite is
large (800+ tests, around 98% line coverage) and leans on real filesystem fixtures and Hypothesis
property tests rather than mocks, with unit, adapter, application, domain and end-to-end layers.
It runs green in CI across a matrix of Linux, macOS and Windows on Python 3.10 through the latest
3.x, which is where the cross-platform path and permission claims actually get tested rather than
assumed. A notebook smoke test executes `notebooks/Quickstart.ipynb` so the tutorial stays in
sync with the code.

What isn't guarded that way: the Windows and macOS path-building branches run through their own
platform-gated tests, but only fully on those runners; and the Unix permission hardening is a
deliberate no-op on Windows, which uses ACLs rather than Unix modes. The published releases on
PyPI (see the [changelog](CHANGELOG.md)) are what the gate signed off on.

## Checking it yourself

You don't have to take any of this on faith.

- The source and the history are on [GitHub](https://github.com/bitranox/lib_layered_config), and
  the design notes live under `docs/systemdesign/`.
- The tests live in the repository and need nothing exotic to run: `make test`, or `pytest` if
  you would rather drive it yourself.
- The architecture is not a matter of trust: `lint-imports` enforces the layer boundaries, so the
  claim that the domain layer imports no adapters is something the build checks, not something you
  have to believe.
- The central claim is self-checking. Provenance is built in, so on your own machine, with your
  own config, `config.origin("some.key")` (or `read-json` on the CLI) tells you exactly which
  layer and file produced any value.

If something does not line up, open an issue. That is what they are for.

## What this isn't

It isn't the parsers and libraries it builds on, and none of them have reviewed or endorsed it:
it leans on rtoml, orjson, PyYAML, rich-click and lib_cli_exit_tools, but their behaviour is
theirs. It isn't a secrets manager - it keeps secrets out of committed files by reading them from
the environment and `.env`, and can redact them from output, but storing and rotating secrets is
a job for a real vault. And it isn't a hosted service or a product with a support desk; it is a
library published in the open under a permissive license.

## License and attribution

The code and docs here are under the MIT License (see [`LICENSE`](LICENSE)). Anthropic's terms
put ownership of model output with the user, so the human owns this and answers for it. Under the
MIT License, anyone who passes it on keeps the copyright and license notice; there is no copyleft
obligation.
