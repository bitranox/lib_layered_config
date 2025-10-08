from __future__ import annotations

import sys
from contextlib import contextmanager
from importlib import import_module
from pathlib import Path
from typing import Callable, Sequence

try:  # pragma: no cover - direct execution fallback
    from ._utils import get_project_metadata, run
except ImportError:  # pragma: no cover - executed when run as a module
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from scripts._utils import get_project_metadata, run

PROJECT = get_project_metadata()

__all__ = ["run_cli"]


def _prepare_paths() -> None:
    project_root = Path(__file__).resolve().parents[1]
    src_path = project_root / "src"
    for entry in (src_path, project_root):
        candidate = str(entry)
        if candidate not in sys.path:
            sys.path.insert(0, candidate)


@contextmanager
def _temporary_argv(script_name: str, args: Sequence[str]):
    original = sys.argv[:]
    sys.argv = [script_name or original[0], *list(args)]
    try:
        yield
    finally:
        sys.argv = original


def _normalise_exit(value: object) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 1
    return 0


def _invoke_callable(target: Callable[..., object], script_name: str, args: Sequence[str]) -> int:
    attempts = (
        lambda: target(argv=list(args)),
        lambda: target(arguments=list(args)),
        lambda: target(args=list(args)),
        lambda: target(list(args)),
        lambda: target(*list(args)),
        lambda: target(),
    )
    last_error: TypeError | None = None
    with _temporary_argv(script_name, args):
        for attempt in attempts:
            try:
                result = attempt()
            except TypeError as exc:
                last_error = exc
                continue
            except SystemExit as exc:
                return _normalise_exit(exc.code)
            else:
                return _normalise_exit(result)
    if last_error is not None:
        raise last_error
    return 0


def _resolve_cli_callable() -> tuple[str, Callable[..., object], str] | None:
    entry = PROJECT.resolve_cli_entry()
    if entry is None:
        return None
    script_name, module_name, attr = entry
    module = import_module(module_name)
    if attr is not None:
        candidate = getattr(module, attr, None)
        if callable(candidate):
            return script_name, candidate, module_name

    for fallback in ("main", "cli", "run"):
        candidate = getattr(module, fallback, None)
        if callable(candidate):
            return script_name, candidate, module_name

    return None


def _invoke_module_entry(args: Sequence[str], *, script_name: str) -> int:
    package_main = f"{PROJECT.import_package}.__main__"
    try:
        module = import_module(package_main)
    except ModuleNotFoundError:
        command = [sys.executable, "-m", PROJECT.import_package, *list(args)]
        result = run(command, capture=False, check=False)
        if result.code != 0:
            raise SystemExit(result.code)
        return result.code

    runner = getattr(module, "run_module", None)
    if callable(runner):
        try:
            return _invoke_callable(runner, script_name, args)
        except TypeError:
            pass

    command = [sys.executable, "-m", PROJECT.import_package, *list(args)]
    result = run(command, capture=False, check=False)
    if result.code != 0:
        raise SystemExit(result.code)
    return result.code


def run_cli(args: Sequence[str] | None = None) -> int:
    """Invoke the package CLI declared in ``pyproject.toml``."""

    _prepare_paths()
    forwarded = list(args) if args else ["--help"]
    resolved = _resolve_cli_callable()
    if resolved is not None:
        script_name, callable_obj, _module = resolved
        try:
            return _invoke_callable(callable_obj, script_name, forwarded)
        except TypeError:
            return _invoke_module_entry(forwarded, script_name=script_name)

    return _invoke_module_entry(forwarded, script_name=PROJECT.slug)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(run_cli(sys.argv[1:]))
