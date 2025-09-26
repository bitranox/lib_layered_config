"""Application-layer merge policy.

Purpose
-------
Convert a sequence of layer payloads into a single coherent configuration
mapping while tracking provenance. Mirrors precedence rules documented in
``docs/systemdesign/module_reference.md`` and remains free of I/O so it can be
reused in alternative composition roots.

Contents
--------
* :func:`merge_layers` – public entry point that iterates over layer payloads.
* :func:`_merge_into` – recursive helper that handles nested dictionary updates
  while recording provenance.

System Role
-----------
Receives layer payloads from :mod:`lib_layered_config.core`, applies precedence
(`app → host → user → dotenv → env`), and returns data structures consumed by
:class:`lib_layered_config.domain.config.Config`.
"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Iterable


def merge_layers(
    layers: Iterable[tuple[str, Mapping[str, object], str | None]],
) -> tuple[dict[str, object], dict[str, dict[str, object]]]:
    """Merge configuration *layers* honouring precedence and provenance.

    Why
    ----
    Centralising merge semantics keeps the domain reusable and guarantees
    deterministic precedence regardless of adapter ordering.

    What
    ----
    Iterates layer tuples, calls :func:`_merge_into` for each mapping, and
    collects two dictionaries: the merged configuration and provenance metadata.

    Parameters
    ----------
    layers:
        Iterable of ``(layer_name, mapping, source_path)`` tuples ordered from
        lowest to highest precedence.

    Returns
    -------
    tuple[dict[str, object], dict[str, dict[str, object]]]
        ``(merged_data, provenance)`` where ``merged_data`` is a nested ``dict``
        and ``provenance`` maps dotted keys to ``{"layer", "path", "key"}``.

    Side Effects
    ------------
    None; operates on copies of provided mappings.

    Examples
    --------
    >>> merged, meta = merge_layers([
    ...     ("app", {"service": {"timeout": 5}}, None),
    ...     ("env", {"service": {"timeout": 10}}, None),
    ... ])
    >>> merged["service"]["timeout"], meta["service.timeout"]["layer"]
    (10, 'env')
    """

    merged: dict[str, object] = {}
    meta: dict[str, dict[str, object]] = {}

    for layer_name, data, path in layers:
        _merge_into(merged, meta, deepcopy(dict(data)), layer_name, path, [])
    return merged, meta


def _merge_into(
    target: dict[str, object],
    meta: dict[str, dict[str, object]],
    incoming: Mapping[str, object],
    layer: str,
    path: str | None,
    segments: list[str],
) -> None:
    """Recursively merge ``incoming`` into ``target`` while recording provenance.

    Why
    ----
    Support nested dictionaries without losing track of which layer supplied the
    final value.

    Parameters
    ----------
    target:
        Dictionary being mutated.
    meta:
        Provenance mapping updated alongside ``target``.
    incoming:
        Mapping provided by a specific configuration layer.
    layer:
        Layer identifier (``"app"``, ``"env"``, etc.).
    path:
        Filesystem path associated with ``incoming`` (if any).
    segments:
        Accumulator of path segments used to build dotted keys.

    Side Effects
    ------------
    Mutates ``target`` and ``meta`` in place.
    """

    for key, value in incoming.items():
        current_path = segments + [key]
        dotted = ".".join(current_path)
        if isinstance(value, Mapping):
            existing = target.get(key)
            if not isinstance(existing, Mapping):
                prefix = dotted
                for meta_key in list(meta.keys()):
                    if meta_key == prefix or meta_key.startswith(prefix + "."):
                        meta.pop(meta_key, None)
                container: dict[str, object] = {}
            else:
                container = dict(existing)
            target[key] = container
            _merge_into(container, meta, value, layer, path, current_path)
        else:
            prefix = dotted
            for meta_key in list(meta.keys()):
                if meta_key == prefix or meta_key.startswith(prefix + "."):
                    meta.pop(meta_key, None)
            target[key] = value
            meta[dotted] = {"layer": layer, "path": path, "key": dotted}
