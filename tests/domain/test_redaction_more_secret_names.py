"""Redaction hides the short secret names and the password inside a URL.

Keys named ``pwd``, ``pass``, ``privatekey``, ``privkey`` or ``bearer`` used to come back in clear
from every redacted view, and so did ``postgres://alice:hunter2@db/x`` under a key such as ``url``
or ``dsn``, because only key names were looked at. The short names are now stems like ``password``,
and a URL-shaped value has its password replaced wherever it sits, unless its path is declared not
sensitive.
"""

from __future__ import annotations

from typing import Any

import pytest

from lib_layered_config import Config
from lib_layered_config.domain.redaction import REDACTED_PLACEHOLDER, NotSensitiveKeys, is_sensitive, redact_mapping
from tests.support.os_markers import os_agnostic

_MASKED_PASSWORD = f"postgres://alice:{REDACTED_PLACEHOLDER}@db.example:5432/app"


# A non-ASCII letter, built from its code point to keep the source ASCII.
_E_ACUTE = chr(0xE9)


@os_agnostic
@pytest.mark.parametrize(
    "key",
    [
        "pwd",
        "db_pwd",
        "dbPwd",
        "PWD",
        "pass",
        "smtp_pass",
        "smtpPass",
        "smtp-pass",
        "privatekey",
        "privkey",
        "ssh_privkey",
        "bearer",
        "auth_bearer",
        "bearer_tokens",
        # An HTTP Authorization header value ("Bearer ...", "Basic <base64 user:password>").
        "authorization",
        "Authorization",
        "http_authorization",
        "proxyAuthorization",
        "authorizations",
        # A stem followed directly by digits, as numbered secrets are often named.
        "password2",
        "PASSWORD1",
        "token2",
        "secret1",
        "api_key2",
        "apiKey2",
        "PrivateKey2",
        "db_password_2",
        # A `_key` followed by more letters, as key material is often named.
        "encryption_keyset",
        "tink_keyset",
        "encryptionKeyset",
        "primary_keysecret",
    ],
)
def test_the_short_secret_names_are_sensitive(key: str) -> None:
    assert is_sensitive(key) is True


@os_agnostic
@pytest.mark.parametrize(
    "key",
    [
        "passenger",
        "bypass",
        "passport",
        "compass",
        "passthrough",
        "pwdx",
        "authority",
        "author",
        "auth",
        "pass2go",
        "md5",
    ],
)
def test_words_that_only_contain_a_short_name_stay_visible(key: str) -> None:
    assert is_sensitive(key) is False


@os_agnostic
@pytest.mark.parametrize(
    ("value", "shown"),
    [
        ("postgres://alice:hunter2@db.example:5432/app", _MASKED_PASSWORD),
        ("redis://:hunter2@cache.example/0", f"redis://:{REDACTED_PLACEHOLDER}@cache.example/0"),
        ("amqp://alice:p@ss@mq.example/vh", f"amqp://alice:{REDACTED_PLACEHOLDER}@mq.example/vh"),
        ("HTTPS://alice:hunter2@example.com", f"HTTPS://alice:{REDACTED_PLACEHOLDER}@example.com"),
        # A user name holding an '@', as a mail login often does (urllib reads the password here too).
        (
            "smtp://alice@example.com:hunter2@mail.example.com:587",
            f"smtp://alice@example.com:{REDACTED_PLACEHOLDER}@mail.example.com:587",
        ),
        # A password holding an unencoded '/', '?' or '#', which database URL parsers accept.
        ("postgresql://app:Ab/9+x@db.example/prod", f"postgresql://app:{REDACTED_PLACEHOLDER}@db.example/prod"),
        ("postgresql://app:a?b@db.example/prod", f"postgresql://app:{REDACTED_PLACEHOLDER}@db.example/prod"),
        ("postgresql://app:a#b@db.example/prod", f"postgresql://app:{REDACTED_PLACEHOLDER}@db.example/prod"),
        ("postgresql://app:1234@db.example/prod", f"postgresql://app:{REDACTED_PLACEHOLDER}@db.example/prod"),
        ("postgresql://app:Ab/9@x@db.example/prod", f"postgresql://app:{REDACTED_PLACEHOLDER}@db.example/prod"),
        # An '@' in the query after a real password: only the password is masked, the host stays.
        (
            "https://alice:hunter2@example.com/p?email=bob@example.com",
            f"https://alice:{REDACTED_PLACEHOLDER}@example.com/p?email=bob@example.com",
        ),
        # A password starting with '/', which SQLAlchemy reads (a base64 password does about once in 64).
        ("postgresql://app:/x9Kq@db.example/prod", f"postgresql://app:{REDACTED_PLACEHOLDER}@db.example/prod"),
        # A user holding an '@' and a password holding a '/'.
        (
            "smtp://alice@example.com:Ab/9@mail.example.com",
            f"smtp://alice@example.com:{REDACTED_PLACEHOLDER}@mail.example.com",
        ),
        # A password holding a '/' and an '@' in the query: the host and database stay shown.
        (
            "postgresql://app:Ab/9+x@db.example/prod?sslrootcert=a@b",
            f"postgresql://app:{REDACTED_PLACEHOLDER}@db.example/prod?sslrootcert=a@b",
        ),
        # A path holding an '@' after a password urllib finds: the host and path stay shown.
        (
            "https://alice:hunter2@example.com/users/bob@example.com",
            f"https://alice:{REDACTED_PLACEHOLDER}@example.com/users/bob@example.com",
        ),
        # Several URLs in one value, as a broker failover list holds them: every password is masked.
        (
            "amqp://u:p1@h1//;amqp://u:p2@h2//",
            f"amqp://u:{REDACTED_PLACEHOLDER}@h1//;amqp://u:{REDACTED_PLACEHOLDER}@h2//",
        ),
        (
            "redis://u:p1@h1,redis://u:p2@h2/0",
            f"redis://u:{REDACTED_PLACEHOLDER}@h1,redis://u:{REDACTED_PLACEHOLDER}@h2/0",
        ),
        # A URL that does not open the value: after a space, or inside another URL's query.
        (" postgres://u:s3cret@h/db", f" postgres://u:{REDACTED_PLACEHOLDER}@h/db"),
        ("http://h/?redirect=http://u:pw@other", f"http://h/?redirect=http://u:{REDACTED_PLACEHOLDER}@other"),
        # A password that starts with '//' or holds letters, ':' and '//', which reads like a scheme of its own.
        ("https://app://8xK3pQ@db.example.com/app", f"https://app:{REDACTED_PLACEHOLDER}@db.example.com/app"),
        ("postgresql://app://Zm9vYmFy@db/prod", f"postgresql://app:{REDACTED_PLACEHOLDER}@db/prod"),
        ("https://app:ab://cd@h/x", f"https://app:{REDACTED_PLACEHOLDER}@h/x"),
        ("https://app:a+b://cd@h/x", f"https://app:{REDACTED_PLACEHOLDER}@h/x"),
        ("https://app:a.b://cd@h/x", f"https://app:{REDACTED_PLACEHOLDER}@h/x"),
        ("https://app:a-b://cd@h/x", f"https://app:{REDACTED_PLACEHOLDER}@h/x"),
        ("https://app://x://y@h/x", f"https://app:{REDACTED_PLACEHOLDER}@h/x"),
        # A '://' in the user info (none of / ? # @ space , ; before it, an '@' after it) is part of the URL.
        ("postgresql://svc_user://8xK3pQ@db/prod", f"postgresql://svc_user:{REDACTED_PLACEHOLDER}@db/prod"),
        ("https://my_app://8xK3pQ@db", f"https://my_app:{REDACTED_PLACEHOLDER}@db"),
        ("https://1app:ab://cd@h", f"https://1app:{REDACTED_PLACEHOLDER}@h"),
        ("https://:ab://cd@h", f"https://:{REDACTED_PLACEHOLDER}@h"),
        ("https://app:1a://cd@h", f"https://app:{REDACTED_PLACEHOLDER}@h"),
        ("https://app:+ab://cd@h", f"https://app:{REDACTED_PLACEHOLDER}@h"),
        ("https://app:-x://cd@h", f"https://app:{REDACTED_PLACEHOLDER}@h"),
        ("https://app:.x://cd@h", f"https://app:{REDACTED_PLACEHOLDER}@h"),
        ("https://u:a_b://c@h", f"https://u:{REDACTED_PLACEHOLDER}@h"),
        ("https://u:-://redis://x@h", f"https://u:{REDACTED_PLACEHOLDER}@h"),
        ("https://u:%://redis://x@h", f"https://u:{REDACTED_PLACEHOLDER}@h"),
        ("https://u:1://a://b@h", f"https://u:{REDACTED_PLACEHOLDER}@h"),
        ("https://app:1://https://u:pw@h", f"https://app:{REDACTED_PLACEHOLDER}@h"),
        # A one-letter user name is a drive letter only in a file URL.
        ("https://u://8xK3pQ@db", f"https://u:{REDACTED_PLACEHOLDER}@db"),
        ("https://u:/x9Kq@db/prod", f"https://u:{REDACTED_PLACEHOLDER}@db/prod"),
        ("a://b://c://d:pw@h", f"a://b:{REDACTED_PLACEHOLDER}@h"),
        # A '[' (an IPv6 host, a markdown link) ends the user info, so the next URL is its own.
        ("http://[::1]:3128|http://user:S3cr3t@proxy", f"http://[::1]:3128|http://user:{REDACTED_PLACEHOLDER}@proxy"),
        ("http://[2001:db8::1]:8080|https://u:pw@h2", f"http://[2001:db8::1]:8080|https://u:{REDACTED_PLACEHOLDER}@h2"),
        ("(http://[::1]:8080)(https://u:pw@h)", f"(http://[::1]:8080)(https://u:{REDACTED_PLACEHOLDER}@h)"),
        ('"http://[::1]"+"https://u:pw@h2"', f'"http://[::1]"+"https://u:{REDACTED_PLACEHOLDER}@h2"'),
        ("[docs](http://h1)[db](https://u:pw@h2)", f"[docs](http://h1)[db](https://u:{REDACTED_PLACEHOLDER}@h2)"),
        # A '[' ends it even in the middle of a host; a ']' does not.
        ("http://h[x://u:pw@h2", f"http://h[x://u:{REDACTED_PLACEHOLDER}@h2"),
        # An '@' or a list separator BEFORE the URL is found once and remembered; the URL's own '@' and the
        # missing separator after it must still be searched for.
        ("me@example.com https://svc:pa://ss@db", f"me@example.com https://svc:{REDACTED_PLACEHOLDER}@db"),
        ("x,y https://u:pa://ss@h", f"x,y https://u:{REDACTED_PLACEHOLDER}@h"),
        # A '/', '?', '#', ',', ';' or '@' ends the user info too.
        ("https://h/path|x://u:pw@h2", f"https://h/path|x://u:{REDACTED_PLACEHOLDER}@h2"),
        ("amqp://h1,amqp://u:pw@h2", f"amqp://h1,amqp://u:{REDACTED_PLACEHOLDER}@h2"),
        (
            "https://example.com?redirect=https://u:pw@h2",
            f"https://example.com?redirect=https://u:{REDACTED_PLACEHOLDER}@h2",
        ),
        ("https://example.com#x://u:pw@h2", f"https://example.com#x://u:{REDACTED_PLACEHOLDER}@h2"),
        ("amqp://h1;amqp://u:pw@h2", f"amqp://h1;amqp://u:{REDACTED_PLACEHOLDER}@h2"),
        (
            "https://u1:p1@h1|https://u2:p2@h2",
            f"https://u1:{REDACTED_PLACEHOLDER}@h1|https://u2:{REDACTED_PLACEHOLDER}@h2",
        ),
        # A '://' with no scheme in front of it does not hide the URL that follows it.
        ("1://https://u:pw@h", f"1://https://u:{REDACTED_PLACEHOLDER}@h"),
        ("://https://u:pw@h", f"://https://u:{REDACTED_PLACEHOLDER}@h"),
        ("*://https://u:pw@h", f"*://https://u:{REDACTED_PLACEHOLDER}@h"),
        ("-://redis://u:pw@h", f"-://redis://u:{REDACTED_PLACEHOLDER}@h"),
        # A URL after text that is not a scheme: digits, a '-', a number list.
        ("12:https://u:pw@h/x", f"12:https://u:{REDACTED_PLACEHOLDER}@h/x"),
        ("-https://u:pw@h", f"-https://u:{REDACTED_PLACEHOLDER}@h"),
        ("abc:123:https://u:pw@h", f"abc:123:https://u:{REDACTED_PLACEHOLDER}@h"),
        ("sentinel:26379:redis://u:p@h", f"sentinel:26379:redis://u:{REDACTED_PLACEHOLDER}@h"),
        (".redis://u:p@h", f".redis://u:{REDACTED_PLACEHOLDER}@h"),
        (
            "1:redis://u:p1@h1;2:redis://u:p2@h2",
            f"1:redis://u:{REDACTED_PLACEHOLDER}@h1;2:redis://u:{REDACTED_PLACEHOLDER}@h2",
        ),
        (
            "redis://u:p1@h1 , 1:redis://u:p2@h2",
            f"redis://u:{REDACTED_PLACEHOLDER}@h1 , 1:redis://u:{REDACTED_PLACEHOLDER}@h2",
        ),
        # An '@' in the fragment, after a password with a '/', leaves the host shown.
        ("postgresql://app:Ab/9@db/prod#a@b", f"postgresql://app:{REDACTED_PLACEHOLDER}@db/prod#a@b"),
        # One letter before ':' is a drive letter only when the rest starts with '/' and the letter is ASCII.
        ("x://a:b/c@h", f"x://a:{REDACTED_PLACEHOLDER}@h"),
        (f"x://{_E_ACUTE}:/pw@h", f"x://{_E_ACUTE}:{REDACTED_PLACEHOLDER}@h"),
        # A scheme holding a digit, '+', '.' or '-'.
        ("s3://AKIAEXAMPLE:s3cr3t@bucket", f"s3://AKIAEXAMPLE:{REDACTED_PLACEHOLDER}@bucket"),
        ("svn+ssh://u:pw@h/repo", f"svn+ssh://u:{REDACTED_PLACEHOLDER}@h/repo"),
        ("x-my.app://u:pw@h", f"x-my.app://u:{REDACTED_PLACEHOLDER}@h"),
        # A JDBC URL, whose scheme has a sub-scheme.
        ("jdbc:mysql://alice:hunter2@db.example/app", f"jdbc:mysql://alice:{REDACTED_PLACEHOLDER}@db.example/app"),
    ],
)
def test_the_password_of_a_url_value_is_masked_under_any_key(value: str, shown: str) -> None:
    assert redact_mapping({"db": {"url": value}}) == {"db": {"url": shown}}


@os_agnostic
@pytest.mark.parametrize(
    "value",
    [
        "postgres://alice@db.example/app",
        "redis://alice@cache.example",
        "redis://cache.example:6379",
        "https://example.com/path?next=a:b@c",
        "https://example.com/a:b@c",
        "alice:hunter2@db.example",
        "mailto:alice@example.com",
        # A port, not a password, before an '@' further on in the path or query.
        "https://example.com:8443/?to=alice@example.com",
        "https://alice@example.com:8443/users/bob@example.com",
        # A ':' inside an IPv6 literal or a drive letter, with an '@' further on, is no password.
        "http://[2001:db8::1]:8080/api?user=alice@example.com",
        "http://[::1]/?next=alice@example.com",
        "file://C:/data/alice@example.toml",
        "FILE://c:/data/alice@example.toml",
        "jar:file://C:/data/alice@example.toml",
        # A '://' whose '@' comes only after a space is no user info: the text after it is not a password.
        "https://my_app://notes by admin@example.com",
        "https://example.com:8443/users/bob@example.com?tab=1",
        # A ':' in the query or fragment of a URL with no path is not a password's.
        "https://example.com?redirect=mailto:bob@example.com",
        "https://example.com?t=12:30&to=bob@example.com",
        "https://example.com#a:b@c",
        "not a url at all",
    ],
)
def test_a_value_without_a_url_password_is_left_as_it_is(value: str) -> None:
    assert redact_mapping({"url": value}) == {"url": value}


@os_agnostic
def test_a_password_of_non_ascii_digits_before_a_slash_is_not_read_as_a_port() -> None:
    arabic_three = chr(0x0663)
    value = f"postgresql://app:{arabic_three * 3}/x@db.example/prod"

    assert redact_mapping({"url": value}) == {"url": f"postgresql://app:{REDACTED_PLACEHOLDER}@db.example/prod"}


@os_agnostic
def test_a_url_password_in_a_list_is_masked() -> None:
    redacted = redact_mapping({"mirrors": ["https://a:b@one.example", "https://two.example"]})

    assert redacted == {"mirrors": [f"https://a:{REDACTED_PLACEHOLDER}@one.example", "https://two.example"]}


@os_agnostic
def test_a_url_under_a_path_declared_not_sensitive_stays_visible() -> None:
    data: dict[str, Any] = {"db": {"url": "postgres://alice:hunter2@db.example:5432/app"}}

    assert redact_mapping(data, not_sensitive=["db.url"]) == data


@os_agnostic
def test_every_redacted_view_of_a_config_masks_a_url_password() -> None:
    cfg = Config(
        {"db": {"url": "postgres://alice:hunter2@db.example:5432/app", "pass": "x"}}, {}, NotSensitiveKeys.NONE
    )

    assert cfg.as_dict(redact=True) == {"db": {"url": _MASKED_PASSWORD, "pass": REDACTED_PLACEHOLDER}}
    assert "hunter2" not in cfg.to_json(redact=True)
    assert cfg.get_redacted("db.url") == _MASKED_PASSWORD
    assert cfg.get_redacted("db") == {"url": _MASKED_PASSWORD, "pass": REDACTED_PLACEHOLDER}
    assert cfg.get("db.url") == "postgres://alice:hunter2@db.example:5432/app"
