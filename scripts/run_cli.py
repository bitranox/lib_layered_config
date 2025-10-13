from __future__ import annotations

import sys
from collections.abc import Callable, Sequence
from contextlib import contextmanager
from importlib import import_module
from importlib.machinery import PathFinder
from importlib.util import module_from_spec
from pathlib import Path
from types import ModuleType

from ._utils import get_project_metadata, run

PROJECT = get_project_metadata()

__all__ = ["run_cli"]


def load_module(name: str) -> ModuleType:
    """Import from the environment, or fall back to the local source tree."""

    try:
        return import_module(name)
    except ModuleNotFoundError:
        src_root = Path(__file__).resolve().parents[1] / "src"
        spec = PathFinder.find_spec(name, [str(src_root)])
        if spec is None or spec.loader is None:
            raise
        module = module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module


@contextmanager
def temporary_argv(script_name: str, args: Sequence[str]):
    """Temporarily replace ``sys.argv`` so Click behaves as if invoked directly."""

    original = sys.argv[:]
    sys.argv = [script_name or original[0], *list(args)]
    try:
        yield
    finally:
        sys.argv = original


def exit_code_from(value: object) -> int:
    """Translate return values or SystemExit payloads into integers."""

    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 1
    return 0


def invocation_variants(args: Sequence[str]) -> Sequence[Callable[[Callable[..., object]], object]]:
    """Return call strategies covering the common Click entry signatures."""

    argv = list(args)
    return (
        lambda fn: fn(argv=argv),
        lambda fn: fn(arguments=argv),
        lambda fn: fn(args=argv),
        lambda fn: fn(argv),
        lambda fn: fn(*argv),
        lambda fn: fn(),
    )


def invoke_callable(command: Callable[..., object], *, script_name: str, args: Sequence[str]) -> int:
    """Call a Click entry point using the first signature that works."""

    last_error: TypeError | None = None
    with temporary_argv(script_name, args):
        for attempt in invocation_variants(args):
            try:
                return exit_code_from(attempt(command))
            except SystemExit as exc:
                return exit_code_from(exc.code)
            except TypeError as exc:
                last_error = exc
                continue
    if last_error is not None:
        raise last_error
    return 0


def candid_callable() -> tuple[str, Callable[..., object]] | None:
    """Return the callable CLI entry point described in project metadata."""

    entry = PROJECT.resolve_cli_entry()
    if entry is None:
        return None
    script_name, module_name, attr = entry
    module = load_module(module_name)
    names = [attr] if attr is not None else []
    names.extend(["main", "cli", "run"])
    for name in names:
        if not name:
            continue
        candidate = getattr(module, name, None)
        if callable(candidate):
            return script_name, candidate
    return None


def run_python_module(args: Sequence[str]) -> int:
    """Fallback: execute ``python -m package`` with the forwarded args."""

    command = [sys.executable, "-m", PROJECT.import_package, *list(args)]
    result = run(command, capture=False, check=False)
    if result.code != 0:
        raise SystemExit(result.code)
    return result.code


def delegate_to_module_entry(args: Sequence[str], *, script_name: str) -> int:
    """Run the package's ``__main__`` module or fall back to ``python -m``."""

    package_main = f"{PROJECT.import_package}.__main__"
    try:
        module = load_module(package_main)
    except ModuleNotFoundError:
        return run_python_module(args)

    runner = getattr(module, "run_module", None)
    if callable(runner):
        try:
            return invoke_callable(runner, script_name=script_name, args=args)
        except TypeError:
            pass
    return run_python_module(args)


def run_cli(args: Sequence[str] | None = None) -> int:
    """Invoke the project's CLI entry point as politely as possible."""

    forwarded = list(args) if args else ["--help"]
    candidate = candid_callable()
    if candidate is not None:
        script_name, command = candidate
        try:
            return invoke_callable(command, script_name=script_name, args=forwarded)
        except TypeError:
            return delegate_to_module_entry(forwarded, script_name=script_name)
    return delegate_to_module_entry(forwarded, script_name=PROJECT.slug)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(run_cli(sys.argv[1:]))
