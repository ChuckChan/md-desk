"""Windows Credential Manager store for the AI API Key (v0.3).

Why Windows Credential Manager (and NOT a plaintext settings.json field, and
NOT a non-Windows Fernet fallback):

  * The AI API Key is a secret. Persisting it in %APPDATA%/MdDesk/settings.json
    in cleartext would leak it. v0.3 therefore keeps the key OUT of settings.json.
  * The deliverable is a Windows .exe, so we store the key in the OS-native
    Windows Credential Manager (the same store browsers/Edge use). It is
    encrypted at rest by Windows, per-user, and never touches the filesystem
    as plaintext.
  * Per the v0.3 spec we intentionally do NOT implement a Fernet/keyring
    fallback for non-Windows. On a non-Windows host ``get_api_key`` returns
    ``None`` and ``set_api_key``/``delete_api_key`` raise ``CredentialStoreError``
    with a clear, actionable message. This is correct: shipping a half-baked
    plaintext fallback would undermine the security guarantee.

The implementation uses ctypes against ``advapi32.dll`` — zero third-party
dependencies, and it freezes cleanly into the PyInstaller bundle.

The secret is stored as a CRED_TYPE_GENERIC credential keyed by ``TARGET_NAME``.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Optional

# Target name under which the AI key is stored in Windows Credential Manager.
TARGET_NAME = "MdDesk/AI/OpenAI-Compatible-Key"

CRED_TYPE_GENERIC = 1
CRED_PERSIST_LOCAL_MACHINE = 2


class CredentialStoreError(Exception):
    """Raised when a credential operation cannot be performed.

    On non-Windows hosts this is raised by the mutating operations; on
    Windows it is raised only on an actual Cred API failure.
    """


class _CREDENTIALW(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", ctypes.POINTER(ctypes.c_byte)),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.c_void_p),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


def is_supported() -> bool:
    """True only on Windows, where the Credential Manager is available."""
    return sys.platform == "win32"


def _advapi32():
    return ctypes.windll.advapi32


def _configure(adv):
    adv.CredWriteW.argtypes = [ctypes.POINTER(_CREDENTIALW), wintypes.DWORD]
    adv.CredWriteW.restype = wintypes.BOOL
    adv.CredReadW.argtypes = [
        wintypes.LPWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(_CREDENTIALW)),
    ]
    adv.CredReadW.restype = wintypes.BOOL
    adv.CredDeleteW.argtypes = [wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
    adv.CredDeleteW.restype = wintypes.BOOL
    adv.CredFree.argtypes = [ctypes.POINTER(_CREDENTIALW)]
    adv.CredFree.restype = None


def set_api_key(key: str) -> None:
    """Persist the AI API Key in Windows Credential Manager.

    Raises ``CredentialStoreError`` on non-Windows hosts (no Fernet fallback)
    or on a Windows Cred API failure.
    """
    if not is_supported():
        raise CredentialStoreError(
            "当前平台不支持 Windows 凭据管理器；API Key 无法保存。"
            "MdDesk v0.3 的 AI 密钥仅在 Windows 上持久化。"
        )
    if key is None:
        raise CredentialStoreError("API Key 为空，未保存。")
    adv = _advapi32()
    _configure(adv)

    blob = key.encode("utf-16-le")
    cred = _CREDENTIALW()
    cred.Flags = 0
    cred.Type = CRED_TYPE_GENERIC
    cred.TargetName = TARGET_NAME
    cred.Comment = "MdDesk AI OpenAI-compatible API key"
    cred.CredentialBlobSize = len(blob)
    cred.CredentialBlob = (ctypes.c_byte * len(blob)).from_buffer_copy(blob)
    cred.Persist = CRED_PERSIST_LOCAL_MACHINE
    cred.UserName = ""

    if not adv.CredWriteW(ctypes.byref(cred), 0):
        err = ctypes.GetLastError()
        raise CredentialStoreError(f"保存 API Key 失败（CredWriteW 错误码 {err}）。")
    ctypes.POINTER(_CREDENTIALW)


def get_api_key() -> Optional[str]:
    """Return the stored AI API Key, or ``None`` if absent / unsupported.

    Never raises on a normal "not found" path; raises ``CredentialStoreError``
    only on an unexpected Windows Cred API failure.
    """
    if not is_supported():
        return None
    adv = _advapi32()
    _configure(adv)

    ptr = ctypes.POINTER(_CREDENTIALW)()
    if not adv.CredReadW(TARGET_NAME, CRED_TYPE_GENERIC, 0, ctypes.byref(ptr)):
        return None
    try:
        cred = ptr.contents
        size = cred.CredentialBlobSize
        if size == 0 or not cred.CredentialBlob:
            return None
        raw = ctypes.string_at(cred.CredentialBlob, size)
        return raw.decode("utf-16-le")
    finally:
        adv.CredFree(ptr)


def delete_api_key() -> None:
    """Remove the stored AI API Key. No-op on non-Windows / when absent."""
    if not is_supported():
        return
    adv = _advapi32()
    _configure(adv)

    if not adv.CredDeleteW(TARGET_NAME, CRED_TYPE_GENERIC, 0):
        err = ctypes.GetLastError()
        # 1168 = ERROR_NOT_FOUND -> already absent, treat as success.
        if err != 1168:
            raise CredentialStoreError(
                f"删除 API Key 失败（CredDeleteW 错误码 {err}）。"
            )
