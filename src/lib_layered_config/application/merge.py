"""Application-layer merge policy.

Purpose
-------
Convert a sequence of layer payloads into a single coherent configuration
mapping while tracking provenance. Mirrors precedence rules documented in
``docs/systemdesign/module_reference.md`` and remains free of I/O so it can be
reused in alternative composition roots.

Contents
    - ``merge_layers``: public entry point driven by a simple loop.
    - ``_merge_layer`` / ``_merge_mapping``: recursive stanzas that keep
      precedence logic readable.
    - ``_set_scalar`` / ``_merge_branch`` / ``_clear_branch``: tiny helpers that
      narrate how provenance is updated when values change.

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
        _merge_layer(merged, meta, data, layer_name, path)
    return merged, meta


def _merge_layer(
    target: dict[str, object],
    meta: dict[str, dict[str, object]],
    payload: Mapping[str, object],
    layer: str,
    path: str | None,
) -> None:
    """Merge a single *payload* into *target* while tracking provenance."""

    clone = deepcopy(dict(payload))
    _merge_mapping(target, meta, clone, layer, path, [])


def _merge_mapping(
    target: dict[str, object],
    meta: dict[str, dict[str, object]],
    incoming: Mapping[str, object],
    layer: str,
    path: str | None,
    segments: list[str],
) -> None:
    """Recursively merge ``incoming`` into ``target`` while recording provenance."""

    for key, value in incoming.items():
        dotted = _dotted_key(segments, key)
        if isinstance(value, Mapping):
            _merge_branch(target, meta, key, value, dotted, layer, path, segments)
        else:
            _set_scalar(target, meta, key, value, dotted, layer, path)


def _merge_branch(
    target: dict[str, object],
    meta: dict[str, dict[str, object]],
    key: str,
    value: Mapping[str, object],
    dotted: str,
    layer: str,
    path: str | None,
    segments: list[str],
) -> None:
    """Merge mapping ``value`` into ``target[key]`` and recurse."""

    existing = target.get(key)
    payload = dict(value)
    if not value:
        if isinstance(existing, Mapping) and not segments:
            return
        _clear_branch(meta, dotted)
        target[key] = {}
        return

    if isinstance(existing, Mapping):
        container: dict[str, object] = dict(existing)
        created_new = False
    else:
        _clear_branch(meta, dotted)
        container = {}
        created_new = True

    target[key] = container
    _merge_mapping(container, meta, payload, layer, path, segments + [key])
    if created_new and not container:
        target.pop(key, None)


def _set_scalar(
    target: dict[str, object],
    meta: dict[str, dict[str, object]],
    key: str,
    value: object,
    dotted: str,
    layer: str,
    path: str | None,
) -> None:
    """Assign a scalar value and update provenance for ``dotted``."""

    _clear_branch(meta, dotted)
    target[key] = value
    meta[dotted] = {"layer": layer, "path": path, "key": dotted}


def _clear_branch(meta: dict[str, dict[str, object]], prefix: str) -> None:
    """Remove provenance entries that belong to *prefix* or its descendants."""

    for meta_key in list(meta.keys()):
        if meta_key == prefix or meta_key.startswith(prefix + "."):
            meta.pop(meta_key, None)


def _dotted_key(segments: list[str], key: str) -> str:
    """Join *segments* and *key* with dots, skipping empties."""

    return ".".join([*segments, key]) if segments else key
