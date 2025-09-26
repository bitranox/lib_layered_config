"""Adapter implementations for ``lib_layered_config``.

Purpose
-------
Group concrete boundary code (filesystem, dotenv, environment, file parsers)
that fulfils the application layer's ports.

System Role
-----------
Modules inside this package implement contracts defined in
:mod:`lib_layered_config.application.ports` and are wired together by the
composition root.
"""
