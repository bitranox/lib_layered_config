"""Factories for cross-platform layered configuration sandboxes.

These helpers centralise filesystem and environment scaffolding used across the
end-to-end, adapter, and example test suites. They keep each test focused on
behaviour (precedence, provenance, CLI UX) while remaining faithful to the
system design documented under ``docs/systemdesign``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict
import sys


@dataclass(slots=True)
class LayeredSandbox:
    """Container describing a deterministic layered configuration sandbox.

    Why
    ----
    Tests exercise the same precedence rules on multiple platforms. This
    dataclass packages the canonical root directories, environment overrides,
    and starting directory so suites can share behaviour-rich assertions rather
    than duplicating setup logic.

    Examples
    --------
    >>> from pathlib import Path
    >>> sandbox = LayeredSandbox(
    ...     vendor='Acme',
    ...     app='Demo',
    ...     slug='demo',
    ...     platform='linux',
    ...     roots={'app': Path('etc/xdg/demo'), 'host': Path('etc/xdg/demo/hosts'), 'user': Path('xdg/demo')},
    ...     env={'LIB_LAYERED_CONFIG_ETC': 'etc', 'XDG_CONFIG_HOME': 'xdg'},
    ...     start_dir=Path('xdg/demo'),
    ... )
    >>> sandbox.vendor, sandbox.start_dir.as_posix()
    ('Acme', 'xdg/demo')
    """

    vendor: str
    app: str
    slug: str
    platform: str
    roots: Dict[str, Path]
    env: Dict[str, str]
    start_dir: Path

    def write(self, layer: str, relative_path: str, *, content: str) -> Path:
        """Create *relative_path* under *layer* with *content* and return it.

        Parameters
        ----------
        layer:
            One of ``"app"``, ``"host"``, ``"user"``.
        relative_path:
            Path relative to the layer root.
        content:
            File payload written using UTF-8.

        Examples
        --------
        Use the helper to communicate that a test is shaping the "app" layer.

        >>> from pathlib import Path
        >>> from tempfile import TemporaryDirectory
        >>> with TemporaryDirectory() as tmp:
        ...     root = Path(tmp)
        ...     sandbox = LayeredSandbox('Acme', 'Demo', 'demo', 'linux',
        ...         {'app': root / 'etc' / 'xdg' / 'demo', 'host': root / 'etc' / 'xdg' / 'demo' / 'hosts', 'user': root / 'xdg' / 'demo'},
        ...         {}, root / 'xdg' / 'demo')
        ...     created = sandbox.write('app', 'config.toml', content='payload')
        ...     assert created.relative_to(root).as_posix() == 'etc/xdg/demo/config.toml'
        ...     assert created.read_text().strip() == 'payload'
        """

        if layer not in self.roots:
            raise KeyError(f"Unknown layer: {layer}")
        target = self.roots[layer] / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return target

    def apply_env(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        """Register the sandbox environment variables via *monkeypatch*.

        Examples
        --------
        >>> class DummyPatch:
        ...     def __init__(self):
        ...         self.captured = {}
        ...     def setenv(self, key, value):
        ...         self.captured[key] = value
        >>> patch = DummyPatch()
        >>> sandbox = LayeredSandbox('Acme', 'Demo', 'demo', 'linux',
        ...     {'app': Path('etc/xdg/demo'), 'host': Path('etc/xdg/demo/hosts'), 'user': Path('xdg/demo')},
        ...     {'LIB_LAYERED_CONFIG_ETC': '/etc'}, Path('xdg/demo'))
        >>> sandbox.apply_env(patch)
        >>> patch.captured['LIB_LAYERED_CONFIG_ETC']
        '/etc'
        """

        for key, value in self.env.items():
            monkeypatch.setenv(key, value)


def create_layered_sandbox(
    tmp_path: Path,
    *,
    vendor: str,
    app: str,
    slug: str,
    platform: str | None = None,
) -> LayeredSandbox:
    """Return a :class:`LayeredSandbox` configured for the current platform.

    Parameters
    ----------
    tmp_path:
        Pytest temporary directory root unique per test invocation.
    vendor / app / slug:
        Naming context passed through to the adapters under test.
    platform:
        Optional override for :data:`sys.platform` to make behaviour explicit in
        contract tests.

    Examples
    --------
    Build a Linux sandbox and confirm the directories mirror the documented layout.

    >>> from pathlib import Path
    >>> from tempfile import TemporaryDirectory
    >>> with TemporaryDirectory() as tmp:
    ...     sandbox = create_layered_sandbox(Path(tmp), vendor='Acme', app='Demo', slug='demo', platform='linux')
    ...     sandbox.roots['app'].relative_to(Path(tmp)).as_posix()
    'etc/xdg/demo'
    >>> with TemporaryDirectory() as tmp:
    ...     win = create_layered_sandbox(Path(tmp), vendor='Acme', app='Demo', slug='demo', platform='win32')
    ...     win.roots['host'].relative_to(Path(tmp)).as_posix().endswith('ProgramData/Acme/Demo/hosts')
    True
    """

    resolved_platform = platform or sys.platform
    roots: Dict[str, Path]
    env: Dict[str, str]

    if resolved_platform.startswith("win"):
        program_data = tmp_path / "ProgramData"
        appdata_roaming = tmp_path / "AppData" / "Roaming"
        local_appdata = tmp_path / "AppData" / "Local"
        roots = {
            "app": program_data / vendor / app,
            "host": program_data / vendor / app / "hosts",
            "user": appdata_roaming / vendor / app,
        }
        env = {
            "LIB_LAYERED_CONFIG_PROGRAMDATA": str(program_data),
            "LIB_LAYERED_CONFIG_APPDATA": str(appdata_roaming),
            "LIB_LAYERED_CONFIG_LOCALAPPDATA": str(local_appdata),
        }
        start_dir = roots["user"]
    elif resolved_platform == "darwin":
        app_support = tmp_path / "Library" / "Application Support"
        home_support = tmp_path / "HomeLibrary" / "Application Support"
        roots = {
            "app": app_support / vendor / app,
            "host": app_support / vendor / app / "hosts",
            "user": home_support / vendor / app,
        }
        env = {
            "LIB_LAYERED_CONFIG_MAC_APP_ROOT": str(app_support),
            "LIB_LAYERED_CONFIG_MAC_HOME_ROOT": str(home_support),
        }
        start_dir = roots["user"]
    else:
        etc_root = tmp_path / "etc"
        xdg_root = tmp_path / "xdg"
        roots = {
            "app": etc_root / "xdg" / slug,
            "host": etc_root / "xdg" / slug / "hosts",
            "user": xdg_root / slug,
        }
        env = {
            "LIB_LAYERED_CONFIG_ETC": str(etc_root),
            "XDG_CONFIG_HOME": str(xdg_root),
        }
        start_dir = roots["user"]

    for path in roots.values():
        path.parent.mkdir(parents=True, exist_ok=True)

    return LayeredSandbox(
        vendor=vendor,
        app=app,
        slug=slug,
        platform=resolved_platform,
        roots=roots,
        env=env,
        start_dir=start_dir,
    )
