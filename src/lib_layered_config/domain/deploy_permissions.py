"""Per-layer deploy permission settings and their one validated reading.

Contents:
    - ``LayerModes``: the directory and file mode of one layer.
    - ``DeployPermissions``: the modes of every layer plus ``enabled``.
    - ``PermissionProblem`` / ``DeployPermissionsError``: one line per refused setting.
    - ``parse_deploy_permissions`` / ``deploy_permissions_from_config``: read the
      ``[lib_layered_config.default_permissions]`` section in one pass, with a caller's runtime
      overrides laid over it.

System Role:
    Applications document this section in their bundled defaults; ``deploy_config`` reads it
    through this module so a configured mode is either applied to every file the deploy writes
    or refused, never silently ignored. A file the deploy leaves unchanged keeps its mode.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, cast

from .deploy_mode import DeployMode, DeployModeError, ModeKind, brief_repr
from .errors import ValidationError
from .identifiers import Layer
from .permissions import LAYER_PERMISSIONS

if TYPE_CHECKING:
    from .config import Config

__all__ = [
    "OVERRIDE_SOURCE",
    "SECTION_KEY",
    "DeployPermissions",
    "DeployPermissionsError",
    "LayerModes",
    "PermissionProblem",
    "deploy_permissions_from_config",
    "parse_deploy_permissions",
]

SECTION_KEY: Final[str] = "lib_layered_config.default_permissions"
#: The source a refusal names for a value the caller passed as a runtime
#: override (such as an application's ``--set``).
OVERRIDE_SOURCE: Final[str] = "override"
_NAMESPACE_KEY: Final[str] = "lib_layered_config"
_ENABLED: Final[str] = "enabled"
_MODE_FIELDS: Final[dict[str, ModeKind]] = {
    f"{layer.value}_{suffix}": kind
    for layer in (Layer.APP, Layer.HOST, Layer.USER)
    for suffix, kind in (("directory", ModeKind.DIRECTORY), ("file", ModeKind.FILE))
}
_KNOWN_KEYS: Final[str] = ", ".join(sorted({*_MODE_FIELDS, _ENABLED}))


@dataclass(frozen=True, slots=True)
class LayerModes:
    """The directory mode and the file mode one layer is deployed with."""

    directory: DeployMode
    file: DeployMode

    def __post_init__(self) -> None:
        """Refuse a field that is not a DeployMode, or a pair whose kinds are swapped.

        A caller outside the type checker can build one directly (it is exported from the
        package root), so the declared field types are checked here too, not only by the type
        checker.
        """
        # A field access is statically typed DeployMode already, so a direct `isinstance` on it
        # is flagged reportUnnecessaryIsInstance under pyright strict. Reading it back through
        # `getattr` (as DeployPermissions.__post_init__ below already does for its own fields)
        # defeats that static narrowing, so `isinstance` is meaningful again - and, unlike
        # `type(x) is not DeployMode`, accepts a DeployMode subclass.
        for name in ("directory", "file"):
            value = getattr(self, name)
            if not isinstance(value, DeployMode):
                raise DeployModeError(f"{name} must be a DeployMode, got {type(value).__name__}")
        if self.directory.kind is not ModeKind.DIRECTORY or self.file.kind is not ModeKind.FILE:
            raise DeployModeError("LayerModes needs a directory mode and a file mode, in that order")


@dataclass(frozen=True, slots=True)
class PermissionProblem:
    """One refused setting: its dotted key, why, and where it was set when known."""

    key: str
    reason: str
    source: str | None = None

    def __str__(self) -> str:
        """Return ``<key>: <reason>``, followed by ``(source: ...)`` when the source is known."""
        suffix = f" (source: {self.source})" if self.source else ""
        return f"{self.key}: {self.reason}{suffix}"


class DeployPermissionsError(ValidationError):
    """The permission settings cannot be used; one line per problem, then an optional hint."""

    def __init__(self, problems: Sequence[PermissionProblem], *, hint: str | None = None) -> None:
        """Store the problems and build the message from them."""
        self.problems: tuple[PermissionProblem, ...] = tuple(problems)
        self.hint: str | None = hint
        lines = [str(problem) for problem in self.problems]
        super().__init__("\n".join([*lines, hint] if hint else lines))

    def __reduce__(
        self,
    ) -> tuple[Callable[..., DeployPermissionsError], tuple[object, ...], dict[str, object]]:
        """Pickle and copy through the constructor, so the message is rebuilt from the problems.

        Exception's own reduce calls the class with ``args``, which hold only the message, and
        ``tuple(message)`` would turn every character into a problem line. The third item carries
        every other instance attribute, ``__notes__`` from ``add_note`` among them, which a
        constructor-only reduce would drop (re-review m-c); the constructor sets the other two.
        """
        state = {name: value for name, value in self.__dict__.items() if name not in ("problems", "hint")}
        return (_rebuild_permissions_error, (type(self), self.problems, self.hint), state)


def _rebuild_permissions_error(
    cls: type[DeployPermissionsError],
    problems: tuple[PermissionProblem, ...],
    hint: str | None,
) -> DeployPermissionsError:
    """Recreate a pickled or copied :class:`DeployPermissionsError` (module level, so pickle can name it)."""
    return cls(problems, hint=hint)


def _built_in(layer: Layer) -> LayerModes:
    modes = LAYER_PERMISSIONS[layer.value]
    return LayerModes(DeployMode(modes["dir"], ModeKind.DIRECTORY), DeployMode(modes["file"], ModeKind.FILE))


@dataclass(frozen=True, slots=True)
class DeployPermissions:
    """Directory and file modes per deployment layer, plus whether to set them at all."""

    app: LayerModes
    host: LayerModes
    user: LayerModes
    enabled: bool = True

    def __post_init__(self) -> None:
        """Refuse a field that does not match its declared type, for a caller-built instance too."""
        for name in ("app", "host", "user"):
            value = getattr(self, name)
            if not isinstance(value, LayerModes):
                raise DeployModeError(f"{name} must be a LayerModes, got {type(value).__name__}")
        if type(self.enabled) is not bool:
            raise DeployModeError(f"enabled must be a bool, got {type(self.enabled).__name__}")

    @classmethod
    def defaults(cls) -> DeployPermissions:
        """Return the built-in layer modes (``LAYER_PERMISSIONS``) with ``enabled`` true."""
        return cls(app=_built_in(Layer.APP), host=_built_in(Layer.HOST), user=_built_in(Layer.USER))

    def for_layer(self, layer: str) -> LayerModes:
        """Return the modes for *layer* (``"app"``, ``"host"`` or ``"user"``)."""
        by_layer = {Layer.APP.value: self.app, Layer.HOST.value: self.host, Layer.USER.value: self.user}
        if layer not in by_layer:
            raise ValidationError(f"Unsupported deployment target: {layer}")
        return by_layer[layer]


def _no_source(_key: str) -> str | None:
    return None


def _read_enabled(value: object) -> bool:
    if isinstance(value, bool):
        return value
    raise ValidationError(f"must be true or false, got {type(value).__name__} {brief_repr(value)}")


def _unknown_setting(name: str) -> str | None:
    """Return the refusal for a name that is not a setting of the section, else None.

    The name is shown only through ``brief_repr``: a quoted TOML key, an override key or a
    ``--set`` path segment can be arbitrarily long or hold a newline, and the problem is one
    bounded line keyed by the section, never by the raw name (re-review m-b).
    """
    if name == _ENABLED or name in _MODE_FIELDS:
        return None
    return f"unknown setting {brief_repr(name)}; expected one of {_KNOWN_KEYS}"


def _assemble(modes: Mapping[str, DeployMode], *, enabled: bool) -> DeployPermissions:
    defaults = DeployPermissions.defaults()

    def pick(layer: str) -> LayerModes:
        fallback = defaults.for_layer(layer)
        return LayerModes(
            modes.get(f"{layer}_directory", fallback.directory),
            modes.get(f"{layer}_file", fallback.file),
        )

    return DeployPermissions(app=pick("app"), host=pick("host"), user=pick("user"), enabled=enabled)


def parse_deploy_permissions(
    section: object,
    *,
    source_of: Callable[[str], str | None] = _no_source,
) -> DeployPermissions:
    """Validate the ``default_permissions`` table in one pass.

    Args:
        section: The table as loaded (``None`` when absent).
        source_of: Returns where a dotted key was set (a path or a layer name), for the message.

    Returns:
        The settings; an absent key keeps its built-in layer default.

    Raises:
        DeployPermissionsError: One problem per bad value, unknown key, or a non-table section.
    """
    if section is None:
        return DeployPermissions.defaults()
    if not isinstance(section, Mapping):
        problem = PermissionProblem(
            SECTION_KEY, f"must be a table, got {type(section).__name__}", source_of(SECTION_KEY)
        )
        raise DeployPermissionsError([problem])
    table = cast("Mapping[object, object]", section)
    modes: dict[str, DeployMode] = {}
    enabled = True
    problems: list[PermissionProblem] = []
    for raw_key, value in table.items():
        name = str(raw_key)
        key = f"{SECTION_KEY}.{name}"  # the provenance lookup key; displayed only for a known name
        unknown = _unknown_setting(name)
        if unknown is not None:
            problems.append(PermissionProblem(SECTION_KEY, unknown, source_of(key)))
            continue
        try:
            if name == _ENABLED:
                enabled = _read_enabled(value)
            else:
                modes[name] = DeployMode.from_config_value(value, _MODE_FIELDS[name])
        except ValidationError as exc:
            problems.append(PermissionProblem(key, str(exc), source_of(key)))
    if problems:
        raise DeployPermissionsError(problems)
    return _assemble(modes, enabled=enabled)


def _source(config: Config, key: str) -> str | None:
    origin = config.origin(key)
    if origin is None:
        return None
    return origin["path"] or origin["layer"]


def _merge_overrides(section: object, overrides: Mapping[str, object]) -> object:
    """Lay *overrides* over the configured *section*; a non-table section is returned as is, to be refused."""
    if section is not None and not isinstance(section, Mapping):
        return section
    base: Mapping[object, object] = cast("Mapping[object, object]", section) if section is not None else {}
    merged: dict[str, object] = {str(key): value for key, value in base.items()}
    merged.update(overrides)
    return merged


def deploy_permissions_from_config(
    config: Config,
    *,
    overrides: Mapping[str, object] | None = None,
) -> DeployPermissions:
    """Read ``[lib_layered_config.default_permissions]`` from a merged configuration.

    Args:
        config: The merged configuration.
        overrides: Runtime values keyed by the section's own setting names (``{"user_file":
            "0o640"}``), laid over the configured ones and validated the same way. A dotted or
            nested key is an unknown setting. A refusal names ``(source: override)``.

    Raises:
        DeployPermissionsError: The ``lib_layered_config`` namespace or the section is not a table,
            or a setting is refused; each problem names the file, layer or override that set it.

    Examples:
        >>> from lib_layered_config.domain.config import Config
        >>> deploy_permissions_from_config(Config({}, {})).user.file.value == 0o600
        True
        >>> settings = deploy_permissions_from_config(Config({}, {}), overrides={"user_file": "0o640"})
        >>> oct(settings.user.file.value)
        '0o640'
    """
    namespace = config.get(_NAMESPACE_KEY)
    if namespace is not None and not isinstance(namespace, Mapping):
        reason = f"must be a table, got {type(namespace).__name__}"
        raise DeployPermissionsError([PermissionProblem(_NAMESPACE_KEY, reason, _source(config, _NAMESPACE_KEY))])
    section = config.get(SECTION_KEY)
    if not overrides:
        return parse_deploy_permissions(section, source_of=lambda key: _source(config, key))
    overridden = frozenset(f"{SECTION_KEY}.{name}" for name in overrides)

    def source_of(key: str) -> str | None:
        return OVERRIDE_SOURCE if key in overridden else _source(config, key)

    return parse_deploy_permissions(_merge_overrides(section, overrides), source_of=source_of)
