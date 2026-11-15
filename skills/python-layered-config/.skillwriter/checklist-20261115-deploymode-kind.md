# skill-writer checklist - python-layered-config (DeployMode kind)

- [x] Change: the "Deploying and scaffolding" paragraph. The sentence "`ModeKind.DIRECTORY` /
      `ModeKind.FILE` names which kind of mode a `DeployModeError` is about" was false: the error
      has no attributes at all (measured: `vars(exc) == {}`, `exc.args` is the message alone).
      It now says `DeployMode(value, kind)` checks one mode (`value` an int, `kind` a `ModeKind`),
      a refused mode raises `DeployModeError` with no kind field, its message names the kind and
      every offending bit (real message quoted), and a caller knows which kind it passed.
      Closes QUALITY-REVIEW R5-S-F2.
- [x] Receipt held (skill_receipt.py start meta-skill-writer) before the edit. The skill has no
      decision ledger, so no rejected or removed decision applies.
- [x] RED, behavioural: given the pre-edit sentence and a "print bad directory mode / bad file
      mode" task, haiku wrote `if exc.kind is ModeKind.DIRECTORY`, an attribute that does not
      exist, quoting that sentence as its only support.
- [x] GREEN quote-back on the new sentence, opus and haiku, same task: both checked each candidate
      with its own `DeployMode(value, ModeKind...)` call and took the kind from the call that
      raised, never from the exception, each quoting the new sentence. 2 tiers x 1 task = 2 cells,
      both correct.
- [x] Gaps settled: the int value type was a gap both GREEN probes named, so the sentence now
      says `value` is an int such as `0o750`. The import path is shown elsewhere in the skill
      (`from lib_layered_config import ...`; `DeployMode`, `DeployModeError`, `ModeKind` are
      root exports). "What if both modes are refused" is declined: each `DeployMode` call checks
      one mode, which the sentence states.
- [x] Width and fence check: added lines 78-104 characters, no fence touched; the sentence after
      it (`force=True` ...) still reads correctly.
- [x] Security scan: prose only; no secrets, hostnames, private paths or PII.
- [x] Twin: plugins/bitranox/skills/coding-python-layered-config/SKILL.md in bitranox-skills holds
      the same body (diffed from line 4 on), parked with the [70] marketplace commit.
- [x] Decisions: none - a factual correction to the library's current behaviour, measured above.
