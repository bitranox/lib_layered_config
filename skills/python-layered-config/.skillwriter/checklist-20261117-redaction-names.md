# skill-writer checklist - python-layered-config (sensitive names, Config text form, every URL)

- [x] Change: the "Redaction helpers" paragraph now lists the built-in sensitive name patterns and
      how they match (per word, plurals, trailing digits), says a lookalike name (`pass_through`,
      `token_url`) is masked too and stays visible only through a Python
      `read_config(not_sensitive=[dotted path])`, and that a declared path shows its whole value,
      a URL password included. It states that `str(config)` / `repr(config)` print the redacted
      view. The URL sentence now says every URL a string holds is masked. Items from the [70]
      sweep-6 list (CHANGELOG [Unreleased] Security entries). The fourth sweep-6 item, the
      `.env.example` key, leaves nothing stale: the skill never names that file and already
      teaches unprefixed `.env` keys.
- [x] Ground truth, at 9670b44: `is_sensitive` true for db_pwd, smtpPass, privkey, auth_bearer,
      authorization, apiKey2, password2, api-token, client-secret, session_id, cookie, jwt,
      signature, pass_through, token_url, api_tokens, passwords, secrets; false for key,
      keyBinding. `str(c)` and `f"{c}"` print the redacted view. Two URLs separated by `;`, a
      space or `,` all come back with both passwords masked. `read_config(not_sensitive=
      ["features.pass_through"])` shows the bool, masked without it; `redact_mapping(...,
      not_sensitive=["net.token_url"])` shows a URL password in that value. The CLI has no
      `not_sensitive` option.
- [x] Receipt held (the batch's receipt from checklist-20261117-rescore-text.md); no ledger entry
      covers these passages.
- [x] RED, opus, text at 9670b44: Q1 (db.pwd) NONE, Q2 (logging a Config) NONE, Q3 (two URLs in
      one value) NONE, Q4 (pass_through) masked-or-not NONE.
- [x] GREEN, opus and haiku, same four questions (Q3 with a space-separated pair, not the
      example's): 8 of 8 correct, each quoting the new text.
- [x] Gaps settled. Closed: the dotted path for a nested declaration and that it is Python-only;
      that a declared path also shows a URL password. Declined as covered by the code and not
      worth text: `%s` and f-strings going through `str()` (Python's own rule), which separators
      split URLs (every separator tried was handled). Declined as covered elsewhere: the mask
      placeholder (same paragraph, `REDACTED_PLACEHOLDER`).
- [x] Re-probe on the final text, opus (effort medium) and haiku, four new questions (api_tokens
      under to_json, an assert message with smtp.pass, keeping `[net] token_url` visible and from
      the CLI, a comma-separated URL pair): 8 of 8 correct.
- [x] Width and fence check on the added lines: none over 100 columns, every code span closed on
      its line; ledger anchors asserted to occur once after the last reflow.
- [x] Decisions: d-20261117-788ba5c2, d-20261117-c35ac5db, d-20261117-590e975d (rule, measured).
- [x] Mirror: twin `coding-python-layered-config/SKILL.md` differs from this copy only in `name:`.
