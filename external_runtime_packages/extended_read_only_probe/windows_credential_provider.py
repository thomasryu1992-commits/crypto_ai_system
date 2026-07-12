from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes


CRED_TYPE_GENERIC = 1


class CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


def read_generic_credential_secret(target_name: str) -> str:
    """Read a Windows Generic Credential secret into this process only."""
    if sys.platform != "win32":
        raise RuntimeError("Windows Credential Manager provider is available only on Windows")
    credential_ptr = ctypes.POINTER(CREDENTIALW)()
    advapi32 = ctypes.WinDLL("Advapi32.dll")
    cred_read = advapi32.CredReadW
    cred_read.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(CREDENTIALW))]
    cred_read.restype = wintypes.BOOL
    cred_free = advapi32.CredFree
    cred_free.argtypes = [ctypes.c_void_p]
    if not cred_read(target_name, CRED_TYPE_GENERIC, 0, ctypes.byref(credential_ptr)):
        raise ctypes.WinError()
    try:
        credential = credential_ptr.contents
        blob = ctypes.string_at(credential.CredentialBlob, credential.CredentialBlobSize)
        try:
            secret = blob.decode("utf-16-le")
        except UnicodeDecodeError:
            secret = blob.decode("utf-8")
        if not secret:
            raise RuntimeError("Credential secret is empty")
        return secret
    finally:
        cred_free(credential_ptr)
