"""
Windows DPAPI helpers (CryptProtectData / CryptUnprotectData).

Current-user scope: CRYPTPROTECT_LOCAL_MACHINE is not set.
Safe to import on macOS and Linux; protect/unprotect raise DpapiUnavailable there.
"""

import sys
from ctypes import wintypes
import ctypes


class DpapiUnavailable(Exception):
    """DPAPI is not available on this platform."""


class DpapiError(Exception):
    """CryptProtectData or CryptUnprotectData failed."""


# Do not pop a Windows UI if the key material cannot be used.
CRYPTPROTECT_UI_FORBIDDEN = 0x01
# Optional entropy for new blobs. Older blobs were protected with no entropy.
APP_ENTROPY = b"WorkTre.Desktop.DPAPI.v1"


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


def is_available() -> bool:
    """True only on Windows, where crypt32 is present."""
    return sys.platform == "win32"


def protect(data: bytes) -> bytes:
    """Encrypt bytes for the current Windows user, with app entropy."""
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("DPAPI protect expects bytes")
    if not data:
        raise ValueError("DPAPI protect expects non-empty data")
    if not is_available():
        raise DpapiUnavailable("DPAPI is only available on Windows")
    return _protect_windows(bytes(data), APP_ENTROPY)


def unprotect(data: bytes) -> bytes:
    """Decrypt bytes previously protected for the current Windows user."""
    plain, _legacy = unprotect_status(data)
    return plain


def unprotect_status(data):
    """
    Decrypt ``data``.

    Returns ``(plaintext, legacy)``. ``legacy`` is true when the blob was
    protected without app entropy and the caller should write it again.
    """
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError("DPAPI unprotect expects bytes")
    if not data:
        raise ValueError("DPAPI unprotect expects non-empty data")
    if not is_available():
        raise DpapiUnavailable("DPAPI is only available on Windows")
    blob = bytes(data)
    try:
        return _unprotect_windows(blob, APP_ENTROPY), False
    except DpapiError:
        return _unprotect_windows(blob, None), True


def _blob_from_bytes(data: bytes):
    buffer = ctypes.create_string_buffer(data, len(data))
    blob = DATA_BLOB()
    blob.cbData = len(data)
    blob.pbData = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))
    return blob, buffer


def _copy_out_blob(blob: DATA_BLOB) -> bytes:
    if not blob.pbData or blob.cbData == 0:
        raise DpapiError("DPAPI returned an empty blob")
    return ctypes.string_at(blob.pbData, blob.cbData)


def _windows_dlls():
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    kernel32.LocalFree.restype = ctypes.c_void_p
    return crypt32, kernel32


def _entropy_argument(entropy):
    """Keep the entropy buffer alive for the crypt32 call."""
    if not entropy:
        return None, None, None
    blob, buffer = _blob_from_bytes(entropy)
    return ctypes.byref(blob), buffer, blob


def _protect_windows(data: bytes, entropy) -> bytes:
    crypt32, kernel32 = _windows_dlls()
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(DATA_BLOB),
        ctypes.c_wchar_p,
        ctypes.POINTER(DATA_BLOB),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(DATA_BLOB),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL

    in_blob, _buffer = _blob_from_bytes(data)
    entropy_arg, _entropy_buffer, _entropy_blob = _entropy_argument(entropy)
    out_blob = DATA_BLOB()
    ok = crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        "WorkTre",
        entropy_arg,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise DpapiError(f"CryptProtectData failed (winerror={ctypes.get_last_error()})")
    try:
        return _copy_out_blob(out_blob)
    finally:
        if out_blob.pbData:
            kernel32.LocalFree(ctypes.cast(out_blob.pbData, ctypes.c_void_p))


def _unprotect_windows(data: bytes, entropy) -> bytes:
    crypt32, kernel32 = _windows_dlls()
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(DATA_BLOB),
        ctypes.c_void_p,
        ctypes.POINTER(DATA_BLOB),
        ctypes.c_void_p,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(DATA_BLOB),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL

    in_blob, _buffer = _blob_from_bytes(data)
    entropy_arg, _entropy_buffer, _entropy_blob = _entropy_argument(entropy)
    out_blob = DATA_BLOB()
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        entropy_arg,
        None,
        None,
        CRYPTPROTECT_UI_FORBIDDEN,
        ctypes.byref(out_blob),
    )
    if not ok:
        raise DpapiError(f"CryptUnprotectData failed (winerror={ctypes.get_last_error()})")
    try:
        return _copy_out_blob(out_blob)
    finally:
        if out_blob.pbData:
            kernel32.LocalFree(ctypes.cast(out_blob.pbData, ctypes.c_void_p))
