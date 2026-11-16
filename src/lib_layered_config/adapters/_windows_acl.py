"""Give a file written beside an existing one the existing file's Windows access list.

Deploy replaces a file by writing a new one and renaming it over the old, and backs a file up by
copying it. On Windows a new file gets the access list (DACL) its directory passes down, so a
``config.toml`` someone restricted with ``Set-Acl`` or ``icacls /inheritance:r`` became readable by
whoever may read the directory again, and so did its backup (measured on Windows 11 with Python
3.12: a file granting only its user full control came back with SYSTEM, Administrators and
CREATOR OWNER inherited). User decision 2026-11-16 (R4-F2, "Carry the file's ACL over"): the old
file's DACL, protected or not, is copied onto the new one. The owner is not copied: setting another
owner needs a privilege a deploy does not have, and a file the deploy writes is owned by its user.

A volume that keeps no access lists (FAT, exFAT, some network shares) answers "not supported";
there is nothing to carry over then. Off Windows this module does nothing: Linux keeps a POSIX ACL
by the rule in ``_file_write.py``.

Contents:
    - :func:`copy_dacl`: copy *source*'s DACL onto *target* (Windows only).
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["copy_dacl"]


def copy_dacl(source: Path, target: Path) -> None:
    """Give *target* the DACL of *source*, keeping whether it is protected from inheritance.

    Does nothing off Windows, when *source* does not exist (a first write has no access list to
    keep), or when the volume keeps no access lists.

    Raises:
        OSError: Windows refused to read *source*'s DACL or to set *target*'s.
    """
    if sys.platform != "win32":
        return
    _copy_dacl_windows(str(source), str(target))


if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes
    from typing import Final

    # Windows SDK values (winnt.h, accctrl.h). SE_FILE_OBJECT (second SE_OBJECT_TYPE member) and
    # SE_DACL_PROTECTED are as Microsoft Learn lists them; Learn gives the SECURITY_INFORMATION bits no
    # numbers, so those three are proven by the Windows tests (a protected DACL stays protected).
    _SE_FILE_OBJECT: Final = 1
    _DACL_SECURITY_INFORMATION: Final = 0x00000004
    _PROTECTED_DACL_SECURITY_INFORMATION: Final = 0x80000000
    _UNPROTECTED_DACL_SECURITY_INFORMATION: Final = 0x20000000
    _SE_DACL_PROTECTED: Final = 0x1000
    _ERROR_SUCCESS: Final = 0
    # What a volume without access lists answers: ERROR_INVALID_FUNCTION, ERROR_NOT_SUPPORTED.
    _NO_ACL_SUPPORT: Final = frozenset({1, 50})
    # A source that is not there: ERROR_FILE_NOT_FOUND, ERROR_PATH_NOT_FOUND. Asked here rather than
    # by the caller, so other systems pay no extra lookup and no check can go stale before the read.
    _NO_SOURCE: Final = frozenset({2, 3})

    _advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _get_named_security_info = _advapi32.GetNamedSecurityInfoW
    _get_named_security_info.restype = wintypes.DWORD
    _get_named_security_info.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    _set_named_security_info = _advapi32.SetNamedSecurityInfoW
    _set_named_security_info.restype = wintypes.DWORD
    _set_named_security_info.argtypes = [
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    _get_security_descriptor_control = _advapi32.GetSecurityDescriptorControl
    _get_security_descriptor_control.restype = wintypes.BOOL
    _get_security_descriptor_control.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.WORD),
        ctypes.POINTER(wintypes.DWORD),
    ]
    _local_free = _kernel32.LocalFree
    _local_free.restype = ctypes.c_void_p
    _local_free.argtypes = [ctypes.c_void_p]

    def _copy_dacl_windows(source: str, target: str) -> None:
        dacl = ctypes.c_void_p()
        descriptor = ctypes.c_void_p()
        status = _get_named_security_info(
            source,
            _SE_FILE_OBJECT,
            _DACL_SECURITY_INFORMATION,
            None,
            None,
            ctypes.byref(dacl),
            None,
            ctypes.byref(descriptor),
        )
        if status in _NO_ACL_SUPPORT or status in _NO_SOURCE:
            return
        if status != _ERROR_SUCCESS:
            raise ctypes.WinError(status, f"cannot read the access list of {source}")
        try:
            flags = _DACL_SECURITY_INFORMATION | _inheritance_flag(descriptor)
            status = _set_named_security_info(target, _SE_FILE_OBJECT, flags, None, None, dacl, None)
        finally:
            _local_free(descriptor)
        if status not in _NO_ACL_SUPPORT and status != _ERROR_SUCCESS:
            raise ctypes.WinError(status, f"cannot set the access list of {target}")

    def _inheritance_flag(descriptor: ctypes.c_void_p) -> int:
        """Protected when the source's DACL is protected from inheritance, else unprotected."""
        control = wintypes.WORD()
        revision = wintypes.DWORD()
        if not _get_security_descriptor_control(descriptor, ctypes.byref(control), ctypes.byref(revision)):
            raise ctypes.WinError(ctypes.get_last_error())
        if control.value & _SE_DACL_PROTECTED:
            return _PROTECTED_DACL_SECURITY_INFORMATION
        return _UNPROTECTED_DACL_SECURITY_INFORMATION
