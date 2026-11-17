"""A Linux or macOS layer root never resolves under the current working directory.

An empty or relative ``LIB_LAYERED_CONFIG_ETC`` made the app layer read ``./xdg/<slug>/config.toml``
from whatever directory the process ran in, and a deploy write there. The library's own overrides
(``LIB_LAYERED_CONFIG_ETC``, ``LIB_LAYERED_CONFIG_MAC_APP_ROOT``, ``LIB_LAYERED_CONFIG_MAC_HOME_ROOT``)
refuse such a value, as the Windows overrides do. ``XDG_CONFIG_HOME`` follows the XDG Base Directory
specification instead: empty means ``$HOME/.config``, and a relative value is ignored.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from lib_layered_config import DeployResult, LayerRootNotAbsoluteError
from lib_layered_config.adapters.path_resolvers._base import home_directory
from lib_layered_config.adapters.path_resolvers.default import DefaultPathResolver
from lib_layered_config.deploy import deploy_config
from tests.support.os_markers import os_agnostic, posix_only

_SLUG = "demo"


def _resolver(env: dict[str, str], *, platform: str, cwd: Path) -> DefaultPathResolver:
    return DefaultPathResolver(vendor="Acme", app="Demo", slug=_SLUG, env=env, platform=platform, cwd=cwd)


def _plant(path: Path, text: str = 'k = "planted"\n') -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def work(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty current directory, plus a HOME under tmp_path that Path.home() answers on every OS."""
    work = tmp_path / "work"
    work.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.chdir(work)
    return work


@os_agnostic
@pytest.mark.parametrize("value", ["", "rel/etc"], ids=["empty", "relative"])
def test_a_relative_linux_etc_override_is_refused_by_the_app_and_host_layers(work: Path, value: str) -> None:
    _plant(work / value / "xdg" / _SLUG / "config.toml")
    resolver = _resolver({"LIB_LAYERED_CONFIG_ETC": value}, platform="linux", cwd=work)
    with pytest.raises(LayerRootNotAbsoluteError) as caught:
        list(resolver.app())
    assert str(caught.value) == (
        f"The LIB_LAYERED_CONFIG_ETC root '{value}' is not an absolute path; set LIB_LAYERED_CONFIG_ETC to an "
        "absolute path or unset it"
    )


@os_agnostic
@pytest.mark.parametrize(
    ("variable", "layer"),
    [("LIB_LAYERED_CONFIG_MAC_APP_ROOT", "app"), ("LIB_LAYERED_CONFIG_MAC_HOME_ROOT", "user")],
)
@pytest.mark.parametrize("value", ["", "rel/root"], ids=["empty", "relative"])
def test_a_relative_macos_root_override_is_refused(work: Path, variable: str, layer: str, value: str) -> None:
    _plant(work / value / "Acme" / "Demo" / "config.toml")
    resolver = _resolver({variable: value}, platform="darwin", cwd=work)
    with pytest.raises(LayerRootNotAbsoluteError, match=f"^The {variable} root '{value}' is not an absolute path"):
        list(getattr(resolver, layer)())


@os_agnostic
@pytest.mark.parametrize("value", ["", "rel"], ids=["empty", "relative"])
def test_an_empty_or_relative_xdg_config_home_falls_back_to_home_config(work: Path, value: str) -> None:
    _plant(work / value / _SLUG / "config.toml")
    _plant(work / value / _SLUG / ".env", "K=planted\n")
    home_config = _plant(Path.home() / ".config" / _SLUG / "config.toml")
    home_dotenv = _plant(Path.home() / ".config" / _SLUG / ".env", "K=home\n")
    resolver = _resolver({"XDG_CONFIG_HOME": value}, platform="linux", cwd=work)

    assert [Path(p).resolve() for p in resolver.user()] == [home_config.resolve()]
    assert [Path(p).resolve() for p in resolver.dotenv()] == [home_dotenv.resolve()]


@os_agnostic
def test_a_linux_app_deploy_with_an_empty_etc_override_writes_nothing_into_the_cwd(
    work: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _plant(tmp_path / "source.toml", "a = 1\n")
    monkeypatch.setenv("LIB_LAYERED_CONFIG_ETC", "")

    with pytest.raises(LayerRootNotAbsoluteError):
        deploy_config(source, vendor="Acme", app="Demo", slug=_SLUG, targets=["app"], platform="linux")

    assert list(work.iterdir()) == []


@os_agnostic
def test_a_linux_user_deploy_with_a_relative_xdg_config_home_writes_under_home_config(
    work: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = _plant(tmp_path / "source.toml", "a = 1\n")
    monkeypatch.setenv("XDG_CONFIG_HOME", "rel")

    results = deploy_config(
        source, vendor="Acme", app="Demo", slug=_SLUG, targets=["user"], platform="linux", set_permissions=False
    )

    assert [r.destination.resolve() for r in results] == [(Path.home() / ".config" / _SLUG / "config.toml").resolve()]
    assert list(work.iterdir()) == []


@os_agnostic
@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_a_relative_home_is_refused_and_a_user_deploy_writes_nothing_into_the_cwd(
    work: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, platform: str
) -> None:
    # Path.home() reads HOME on POSIX and USERPROFILE on Windows; the refusal names the one it read.
    for name in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(name, "relhome")
    # On Linux an absolute XDG_CONFIG_HOME (set on GitHub's ubuntu image) wins over HOME, so HOME is never read;
    # on macOS the user-root override does the same.
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("LIB_LAYERED_CONFIG_MAC_HOME_ROOT", raising=False)
    _plant(work / "relhome" / ".config" / _SLUG / "config.toml")
    _plant(work / "relhome" / "Library" / "Application Support" / "Acme" / "Demo" / "config.toml")
    variable = "USERPROFILE" if os.name == "nt" else "HOME"
    expected = f"^The {variable} root 'relhome' is not an absolute path; set {variable} to an absolute path$"

    with pytest.raises(LayerRootNotAbsoluteError, match=expected):
        list(_resolver({}, platform=platform, cwd=work).user())
    before = sorted(p.relative_to(work) for p in work.rglob("*"))
    source = _plant(tmp_path / "source.toml", "a = 1\n")
    with pytest.raises(LayerRootNotAbsoluteError, match=expected):
        deploy_config(source, vendor="Acme", app="Demo", slug=_SLUG, targets=["user"], platform=platform)
    assert sorted(p.relative_to(work) for p in work.rglob("*")) == before


@os_agnostic
@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_an_empty_home_is_refused_rather_than_read_as_the_filesystem_root(
    work: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, platform: str
) -> None:
    # Path.home() answers "/" for HOME="" (3.10 to 3.15), which has a root, so a user deploy went to /.config/<slug>.
    for name in ("HOME", "USERPROFILE"):
        monkeypatch.setenv(name, "")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("LIB_LAYERED_CONFIG_MAC_HOME_ROOT", raising=False)
    variable = "USERPROFILE" if os.name == "nt" else "HOME"
    expected = f"^The {variable} root '' is not an absolute path; set {variable} to an absolute path$"

    with pytest.raises(LayerRootNotAbsoluteError, match=expected):
        list(_resolver({}, platform=platform, cwd=work).user())
    source = _plant(tmp_path / "source.toml", "a = 1\n")
    with pytest.raises(LayerRootNotAbsoluteError, match=expected):
        deploy_config(source, vendor="Acme", app="Demo", slug=_SLUG, targets=["user"], platform=platform)


@posix_only
@pytest.mark.parametrize("platform", ["linux", "darwin"])
def test_an_empty_passwd_home_is_refused_like_an_empty_home(
    work: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, platform: str
) -> None:
    # posix_only skips this test on Windows; the assert narrows sys.platform for pyright, which does not
    # read pytest.skip (a callable object) as ending the path.
    assert sys.platform != "win32"
    import pwd

    # With HOME unset, Path.home() reads the account's passwd home field, and an empty one also comes back as
    # "/" (CPython's posixpath.expanduser), so a user deploy went to /.config/<slug> (user decision 2026-11-17,
    # s6 R4-F2). The passwd database is the OS edge this suite cannot inject, so getpwuid is patched.
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("LIB_LAYERED_CONFIG_MAC_HOME_ROOT", raising=False)
    entry = pwd.struct_passwd(("nohome", "x", os.getuid(), os.getgid(), "", "", "/bin/sh"))

    def fake_getpwuid(uid: int, /) -> pwd.struct_passwd:
        del uid
        return entry

    monkeypatch.setattr(pwd, "getpwuid", fake_getpwuid)
    expected = "^The HOME root '' is not an absolute path; set HOME to an absolute path$"

    with pytest.raises(LayerRootNotAbsoluteError, match=expected):
        list(_resolver({}, platform=platform, cwd=work).user())
    source = _plant(tmp_path / "source.toml", "a = 1\n")
    with pytest.raises(LayerRootNotAbsoluteError, match=expected):
        deploy_config(source, vendor="Acme", app="Demo", slug=_SLUG, targets=["user"], platform=platform)


@posix_only
def test_a_passwd_home_is_used_when_home_is_unset(work: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # posix_only skips this test on Windows; the assert narrows sys.platform for pyright, which does not
    # read pytest.skip (a callable object) as ending the path.
    assert sys.platform != "win32"
    import pwd

    # The control: a non-empty passwd home still answers, so only the empty field is refused.
    monkeypatch.delenv("HOME", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    home = work / "account-home"
    entry = pwd.struct_passwd(("withhome", "x", os.getuid(), os.getgid(), "", str(home), "/bin/sh"))

    def fake_getpwuid(uid: int, /) -> pwd.struct_passwd:
        del uid
        return entry

    monkeypatch.setattr(pwd, "getpwuid", fake_getpwuid)

    assert list(_resolver({}, platform="linux", cwd=work).user()) == []
    assert home_directory() == home


@os_agnostic
@pytest.mark.parametrize("emptied", ["HOME", "USERPROFILE"])
def test_only_an_empty_home_variable_this_os_reads_is_refused(
    work: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, emptied: str
) -> None:
    # Path.home() reads HOME on POSIX and USERPROFILE on Windows; emptying the other one must change nothing.
    monkeypatch.setenv(emptied, "")
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    read_by_this_os = "USERPROFILE" if os.name == "nt" else "HOME"
    source = _plant(tmp_path / "source.toml", "a = 1\n")

    def deploy() -> list[DeployResult]:
        return deploy_config(
            source, vendor="Acme", app="Demo", slug=_SLUG, targets=["user"], platform="linux", set_permissions=False
        )

    if emptied == read_by_this_os:
        with pytest.raises(LayerRootNotAbsoluteError, match=f"^The {emptied} root '' is not an absolute path"):
            deploy()
    else:
        results = deploy()
        assert [r.destination.resolve().is_relative_to((tmp_path / "home").resolve()) for r in results] == [True]
