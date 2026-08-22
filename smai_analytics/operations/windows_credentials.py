"""Minimal Windows Credential Manager access for local operational secrets.

The helpers deliberately expose only a target, account label, and opaque
secret.  Callers must never persist or log the returned secret.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2
ERROR_NOT_FOUND = 1168


class CredentialManagerError(RuntimeError):
    """Raised when Windows Credential Manager cannot safely complete an operation."""


class FILETIME(ctypes.Structure):
    _fields_ = (("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD))


class CREDENTIAL_ATTRIBUTEW(ctypes.Structure):
    _fields_ = (("Keyword", wintypes.LPWSTR), ("Flags", wintypes.DWORD), ("ValueSize", wintypes.DWORD), ("Value", ctypes.POINTER(ctypes.c_byte)))


class CREDENTIALW(ctypes.Structure):
    _fields_ = (
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.POINTER(CREDENTIAL_ATTRIBUTEW)),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    )


PCREDENTIALW = ctypes.POINTER(CREDENTIALW)


def _credential_api():
    if os.name != "nt":
        raise CredentialManagerError("Windows Credential Manager is required for Gmail notification credentials.")
    api = ctypes.WinDLL("Advapi32.dll", use_last_error=True)
    api.CredWriteW.argtypes = (PCREDENTIALW, wintypes.DWORD)
    api.CredWriteW.restype = wintypes.BOOL
    api.CredReadW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(PCREDENTIALW))
    api.CredReadW.restype = wintypes.BOOL
    api.CredDeleteW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD)
    api.CredDeleteW.restype = wintypes.BOOL
    api.CredFree.argtypes = (ctypes.c_void_p,)
    api.CredFree.restype = None
    return api


def _raise_last_error(action: str) -> None:
    error = ctypes.get_last_error()
    raise CredentialManagerError(f"Credential Manager {action} failed (Windows error {error}).")


def write_generic_secret(*, target: str, username: str, secret: str) -> None:
    """Store a secret for the current Windows user without writing it to disk."""

    normalized_target = target.strip()
    normalized_username = username.strip()
    if not normalized_target or not normalized_username or not secret:
        raise ValueError("target, username, and secret are required")
    encoded_secret = secret.encode("utf-16-le")
    blob = (ctypes.c_byte * len(encoded_secret)).from_buffer_copy(encoded_secret)
    credential = CREDENTIALW()
    credential.Type = CRED_TYPE_GENERIC
    credential.TargetName = normalized_target
    credential.CredentialBlobSize = len(encoded_secret)
    credential.CredentialBlob = ctypes.cast(blob, ctypes.POINTER(ctypes.c_byte))
    credential.Persist = CRED_PERSIST_LOCAL_MACHINE
    credential.UserName = normalized_username
    if not _credential_api().CredWriteW(ctypes.byref(credential), 0):
        _raise_last_error("write")


def read_generic_secret(*, target: str) -> tuple[str, str] | None:
    """Return the current user's account label and secret, or ``None`` when absent."""

    normalized_target = target.strip()
    if not normalized_target:
        raise ValueError("target is required")
    pointer = PCREDENTIALW()
    api = _credential_api()
    if not api.CredReadW(normalized_target, CRED_TYPE_GENERIC, 0, ctypes.byref(pointer)):
        if ctypes.get_last_error() == ERROR_NOT_FOUND:
            return None
        _raise_last_error("read")
    try:
        credential = pointer.contents
        blob = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
        return str(credential.UserName or ""), blob.decode("utf-16-le")
    finally:
        api.CredFree(pointer)


def delete_generic_secret(*, target: str) -> bool:
    """Remove one current-user generic credential and report whether it existed."""

    normalized_target = target.strip()
    if not normalized_target:
        raise ValueError("target is required")
    api = _credential_api()
    if api.CredDeleteW(normalized_target, CRED_TYPE_GENERIC, 0):
        return True
    if ctypes.get_last_error() == ERROR_NOT_FOUND:
        return False
    _raise_last_error("delete")
