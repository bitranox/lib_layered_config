"""Build a Windows permission wall that ``os.stat`` cannot see past.

On Windows, ``os.stat`` of a directory the user may not open does not fail: CPython falls back
to reading the entry from the parent directory's listing. A wall that makes ``stat`` raise has to
deny BOTH - reading the directory's attributes, and listing its parent. Each DACL is saved first
and put back afterwards, so the wall leaves nothing behind.

An elevated process still sees through it while it holds ``SeBackupPrivilege`` enabled (an OpenSSH
session does), because ``stat`` opens with backup semantics. The wall therefore disables the backup
and restore privileges for its own lifetime and restores their previous state afterwards.

Contents:
    - ``stat_wall``: deny ``stat`` on a directory for the current user, for the duration.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

__all__ = ["stat_wall"]


if sys.platform == "win32":
    import ctypes
    from contextlib import ExitStack
    from ctypes import wintypes

    _BYPASS_PRIVILEGES = ("SeBackupPrivilege", "SeRestorePrivilege")
    _SE_PRIVILEGE_DISABLED = 0
    _TOKEN_ADJUST_PRIVILEGES = 0x0020
    _TOKEN_QUERY = 0x0008
    _TOKEN_USER_CLASS = 1
    _ERROR_NOT_ALL_ASSIGNED = 1300
    _SE_FILE_OBJECT = 1
    _DACL_SECURITY_INFORMATION = 0x4
    _DENY_ACCESS = 3
    _NO_INHERITANCE = 0
    _TRUSTEE_IS_SID = 0
    _TRUSTEE_IS_USER = 1
    _FILE_LIST_DIRECTORY = 0x0001
    _FILE_READ_ATTRIBUTES = 0x0080

    class _Luid(ctypes.Structure):
        _fields_ = [("LowPart", ctypes.c_uint32), ("HighPart", ctypes.c_int32)]

    class _LuidAndAttributes(ctypes.Structure):
        _fields_ = [("Luid", _Luid), ("Attributes", ctypes.c_uint32)]

    class _TokenPrivileges(ctypes.Structure):
        _fields_ = [
            ("PrivilegeCount", ctypes.c_uint32),
            ("Privileges", _LuidAndAttributes * len(_BYPASS_PRIVILEGES)),
        ]

    class _Trustee(ctypes.Structure):
        _fields_ = [
            ("pMultipleTrustee", ctypes.c_void_p),
            ("MultipleTrusteeOperation", ctypes.c_int32),
            ("TrusteeForm", ctypes.c_int32),
            ("TrusteeType", ctypes.c_int32),
            ("ptstrName", ctypes.c_void_p),
        ]

    class _ExplicitAccess(ctypes.Structure):
        _fields_ = [
            ("grfAccessPermissions", ctypes.c_uint32),
            ("grfAccessMode", ctypes.c_int32),
            ("grfInheritance", ctypes.c_uint32),
            ("Trustee", _Trustee),
        ]

    _advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.LocalFree.restype = ctypes.c_void_p
    _advapi32.OpenProcessToken.argtypes = [wintypes.HANDLE, ctypes.c_uint32, ctypes.POINTER(wintypes.HANDLE)]
    _advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int32,
        ctypes.c_void_p,
        ctypes.c_uint32,
        ctypes.POINTER(ctypes.c_uint32),
    ]
    _advapi32.LookupPrivilegeValueW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.POINTER(_Luid)]
    _advapi32.AdjustTokenPrivileges.argtypes = [
        wintypes.HANDLE,
        wintypes.BOOL,
        ctypes.POINTER(_TokenPrivileges),
        ctypes.c_uint32,
        ctypes.POINTER(_TokenPrivileges),
        ctypes.POINTER(ctypes.c_uint32),
    ]
    _advapi32.GetNamedSecurityInfoW.argtypes = [
        wintypes.LPCWSTR,
        ctypes.c_int32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    _advapi32.GetNamedSecurityInfoW.restype = ctypes.c_uint32
    _advapi32.SetNamedSecurityInfoW.argtypes = [
        wintypes.LPWSTR,
        ctypes.c_int32,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    _advapi32.SetNamedSecurityInfoW.restype = ctypes.c_uint32
    _advapi32.SetEntriesInAclW.argtypes = [
        ctypes.c_uint32,
        ctypes.POINTER(_ExplicitAccess),
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    _advapi32.SetEntriesInAclW.restype = ctypes.c_uint32

    def _check_status(status: int) -> None:
        """Raise the Win32 error the security functions RETURN (they do not set the last error)."""
        if status != 0:
            raise ctypes.WinError(status)

    @contextmanager
    def _process_token() -> Generator[wintypes.HANDLE, None, None]:
        token = wintypes.HANDLE()
        if not _advapi32.OpenProcessToken(
            _kernel32.GetCurrentProcess(), _TOKEN_ADJUST_PRIVILEGES | _TOKEN_QUERY, ctypes.byref(token)
        ):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            yield token
        finally:
            _kernel32.CloseHandle(token)

    def _user_sid(token: wintypes.HANDLE) -> ctypes.Array[ctypes.c_char]:
        """Return a buffer holding the token's TOKEN_USER; its first field points at the user SID."""
        size = ctypes.c_uint32(0)
        _advapi32.GetTokenInformation(token, _TOKEN_USER_CLASS, None, 0, ctypes.byref(size))
        buffer = ctypes.create_string_buffer(size.value)
        if not _advapi32.GetTokenInformation(token, _TOKEN_USER_CLASS, buffer, size, ctypes.byref(size)):
            raise ctypes.WinError(ctypes.get_last_error())
        return buffer

    def _adjust(token: wintypes.HANDLE, state: _TokenPrivileges) -> _TokenPrivileges:
        previous = _TokenPrivileges()
        size = ctypes.c_uint32(0)
        ok = _advapi32.AdjustTokenPrivileges(
            token, False, ctypes.byref(state), ctypes.sizeof(previous), ctypes.byref(previous), ctypes.byref(size)
        )
        error = ctypes.get_last_error()
        # NOT_ALL_ASSIGNED means the token does not hold a privilege at all: nothing to disable.
        if not ok or error not in (0, _ERROR_NOT_ALL_ASSIGNED):
            raise ctypes.WinError(error)
        return previous

    @contextmanager
    def _bypass_privileges_disabled(token: wintypes.HANDLE) -> Generator[None, None, None]:
        disabled = _TokenPrivileges(PrivilegeCount=len(_BYPASS_PRIVILEGES))
        for index, name in enumerate(_BYPASS_PRIVILEGES):
            if not _advapi32.LookupPrivilegeValueW(None, name, ctypes.byref(disabled.Privileges[index].Luid)):
                raise ctypes.WinError(ctypes.get_last_error())
            disabled.Privileges[index].Attributes = _SE_PRIVILEGE_DISABLED
        previous = _adjust(token, disabled)
        try:
            yield
        finally:
            _adjust(token, previous)

    def _set_dacl(path: Path, dacl: ctypes.c_void_p | int | None) -> None:
        _check_status(
            _advapi32.SetNamedSecurityInfoW(
                str(path), _SE_FILE_OBJECT, _DACL_SECURITY_INFORMATION, None, None, dacl, None
            )
        )

    @contextmanager
    def _denied(path: Path, sid: int, rights: int) -> Generator[None, None, None]:
        """Add a deny entry for *sid* to *path*'s DACL, and put the saved DACL back afterwards."""
        old_dacl = ctypes.c_void_p()
        descriptor = ctypes.c_void_p()
        _check_status(
            _advapi32.GetNamedSecurityInfoW(
                str(path),
                _SE_FILE_OBJECT,
                _DACL_SECURITY_INFORMATION,
                None,
                None,
                ctypes.byref(old_dacl),
                None,
                ctypes.byref(descriptor),
            )
        )
        try:
            entry = _ExplicitAccess(
                grfAccessPermissions=rights,
                grfAccessMode=_DENY_ACCESS,
                grfInheritance=_NO_INHERITANCE,
                Trustee=_Trustee(TrusteeForm=_TRUSTEE_IS_SID, TrusteeType=_TRUSTEE_IS_USER, ptstrName=sid),
            )
            new_dacl = ctypes.c_void_p()
            _check_status(_advapi32.SetEntriesInAclW(1, ctypes.byref(entry), old_dacl, ctypes.byref(new_dacl)))
            try:
                _set_dacl(path, new_dacl)
            finally:
                _kernel32.LocalFree(new_dacl)
            try:
                yield
            finally:
                _set_dacl(path, old_dacl)
        finally:
            _kernel32.LocalFree(descriptor)

    @contextmanager
    def stat_wall(directory: Path) -> Generator[None, None, None]:
        """Make ``directory.stat()`` raise ``PermissionError`` for the current user, for the duration.

        Args:
            directory: An existing directory whose parent the test owns (under ``tmp_path``).

        Raises:
            OSError: A DACL or a privilege could not be read or changed.
        """
        with _process_token() as token:
            token_user = _user_sid(token)
            sid = ctypes.c_void_p.from_buffer(token_user).value
            if sid is None:
                raise OSError("the process token names no user SID")
            with ExitStack() as walls:
                # Entered in this order, the parent's entry is removed first on the way out.
                walls.enter_context(_denied(directory, sid, _FILE_READ_ATTRIBUTES))
                walls.enter_context(_denied(directory.parent, sid, _FILE_LIST_DIRECTORY))
                walls.enter_context(_bypass_privileges_disabled(token))
                yield

else:

    @contextmanager
    def stat_wall(directory: Path) -> Generator[None, None, None]:
        """Refuse outside Windows: the wall is built from Windows ACLs."""
        raise OSError(f"stat_wall needs Windows ACLs; cannot wall {directory} on {sys.platform}")
        yield  # pragma: no cover - unreachable, keeps this a generator
