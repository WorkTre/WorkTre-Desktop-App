"""
src/utils/security.py
Security utilities for encryption and secure storage.

Remember me is stored with Windows DPAPI (current user). A legacy Fernet
remember_me.json + remember_me.key pair is decrypted once, rewritten with
DPAPI, then deleted. If that decryption fails, the legacy files are deleted
and the user signs in again. Without DPAPI (macOS/Linux) nothing secret is
written to disk.
"""

import os
import json
import base64
from typing import Optional, Dict, Any

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend

from ..config import constants, settings
from ..platform.utils import get_app_data_dir
from . import dpapi
from .file_utils import ensure_directory


class SecurityManager:
    """Manager for security operations."""

    def __init__(self, app_name: str = "WorkTre", base_dir: Optional[str] = None):
        self.app_name = app_name
        self._base_dir = base_dir
        self._key_path = None
        self._data_path = None
        self._dpapi_path = None
        self._initialize_paths()

    def _initialize_paths(self):
        """Initialize file paths."""
        base_dir = self._base_dir or get_app_data_dir(self.app_name)
        ensure_directory(base_dir)

        self._key_path = os.path.join(base_dir, settings.KEY_FILE_NAME)
        self._data_path = os.path.join(base_dir, settings.DATA_FILE_NAME)
        self._dpapi_path = os.path.join(base_dir, constants.DPAPI_CREDENTIALS_FILE)

    def _generate_key_from_password(self, password: str, salt: bytes = None) -> tuple:
        """
        Generate a key from a password using PBKDF2.

        Args:
            password: Password string
            salt: Optional salt bytes

        Returns:
            Tuple of (key, salt)
        """
        if salt is None:
            salt = os.urandom(16)

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
            backend=default_backend()
        )

        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return key, salt

    def encrypt(self, data: str) -> Optional[str]:
        """Encrypt a string with DPAPI. Returns None when DPAPI is unavailable."""
        if data is None or not dpapi.is_available():
            return None
        try:
            blob = dpapi.protect(data.encode("utf-8"))
            return base64.b64encode(blob).decode("ascii")
        except Exception:
            print("Error encrypting data")
            return None

    def decrypt(self, encrypted_data: str) -> Optional[str]:
        """Decrypt a DPAPI string produced by encrypt(). """
        if not encrypted_data or not dpapi.is_available():
            return None
        try:
            blob = base64.b64decode(encrypted_data)
            return dpapi.unprotect(blob).decode("utf-8")
        except Exception:
            print("Error decrypting data")
            return None

    def encrypt_with_password(self, data: str, password: str) -> Optional[Dict[str, str]]:
        """
        Encrypt data with a password using PBKDF2.

        Args:
            data: Data to encrypt
            password: Password for encryption

        Returns:
            Dictionary with encrypted data and salt
        """
        try:
            key, salt = self._generate_key_from_password(password)
            fernet = Fernet(key)
            encrypted = fernet.encrypt(data.encode())
            return {
                "data": encrypted.decode(),
                "salt": base64.b64encode(salt).decode()
            }
        except Exception:
            print("Error encrypting with password")
            return None

    def decrypt_with_password(self, encrypted_data: str, password: str,
                               salt_b64: str) -> Optional[str]:
        """
        Decrypt data with a password.

        Args:
            encrypted_data: Encrypted data
            password: Password for decryption
            salt_b64: Base64 encoded salt

        Returns:
            Decrypted data or None
        """
        try:
            salt = base64.b64decode(salt_b64)
            key, _ = self._generate_key_from_password(password, salt)
            fernet = Fernet(key)
            decrypted = fernet.decrypt(encrypted_data.encode())
            return decrypted.decode()
        except InvalidToken:
            print("Invalid password or corrupted data")
            return None
        except Exception:
            print("Error decrypting with password")
            return None

    def save_credentials(self, email: str, password: str) -> bool:
        """Save credentials with DPAPI. Empty values clear the saved password."""
        if not email or not password:
            return self.clear_credentials()
        if not self._write_dpapi_credentials({"email": email, "password": password}):
            return False
        self._delete_legacy_files()
        return True

    def load_credentials(self) -> Optional[Dict[str, Any]]:
        """Load credentials, migrating a legacy Fernet store on first success."""
        current = self._read_dpapi_credentials()
        if current:
            self._delete_legacy_files()
            return current

        legacy = self._take_legacy_credentials()
        if not legacy:
            return None
        if self._write_dpapi_credentials(legacy):
            self._delete_legacy_files()
        return legacy

    def clear_credentials(self) -> bool:
        """Clear saved credentials."""
        try:
            self._delete_file(self._dpapi_path)
            self._delete_legacy_files()
            return True
        except Exception:
            print("Error clearing credentials")
            return False

    def has_saved_credentials(self) -> bool:
        """Check if credentials are saved."""
        return os.path.exists(self._dpapi_path) or os.path.exists(self._data_path)

    def get_key_info(self) -> Dict[str, Any]:
        """Get information about the credential files."""
        return {
            "key_exists": os.path.exists(self._key_path),
            "data_exists": os.path.exists(self._data_path),
            "dpapi_exists": os.path.exists(self._dpapi_path),
            "key_path": self._key_path,
            "data_path": self._data_path,
            "dpapi_path": self._dpapi_path,
            "key_size": os.path.getsize(self._key_path) if os.path.exists(self._key_path) else 0,
            "data_size": os.path.getsize(self._data_path) if os.path.exists(self._data_path) else 0,
        }

    def rotate_key(self) -> bool:
        """Re-protect stored credentials with DPAPI."""
        credentials = self._read_dpapi_credentials() or self._take_legacy_credentials()
        if not credentials:
            return True
        if not self._write_dpapi_credentials(credentials):
            return False
        self._delete_legacy_files()
        return True

    def _write_dpapi_credentials(self, credentials: Dict[str, str]) -> bool:
        if not dpapi.is_available():
            return False
        expected = {
            "email": credentials.get("email") or "",
            "password": credentials.get("password") or "",
        }
        try:
            payload = json.dumps(expected).encode("utf-8")
            blob = dpapi.protect(payload)
            ensure_directory(os.path.dirname(self._dpapi_path))
            temporary = self._dpapi_path + ".tmp"
            with open(temporary, "wb") as handle:
                handle.write(blob)
            os.replace(temporary, self._dpapi_path)
        except Exception:
            print("Error saving credentials")
            self._delete_file(self._dpapi_path + ".tmp")
            return False
        verified = self._read_dpapi_credentials(delete_on_definite_failure=False)
        if not verified:
            return False
        if verified.get("email") != expected["email"] or verified.get("password") != expected["password"]:
            return False
        return True

    def _read_dpapi_credentials(self, delete_on_definite_failure: bool = True) -> Optional[Dict[str, str]]:
        if not os.path.exists(self._dpapi_path) or not dpapi.is_available():
            return None
        try:
            with open(self._dpapi_path, "rb") as handle:
                blob = handle.read()
        except OSError:
            print("Could not read saved credentials")
            return None
        try:
            plain, legacy = dpapi.unprotect_status(blob)
            payload = json.loads(plain.decode("utf-8"))
        except OSError:
            print("Could not read saved credentials")
            return None
        except dpapi.DpapiUnavailable:
            print("Could not read saved credentials")
            return None
        except dpapi.DpapiError as exc:
            # RPC / profile failures must leave remember_me.dpapi in place.
            if delete_on_definite_failure and dpapi.error_is_corrupt_data(exc):
                print("Could not decrypt saved credentials")
                self._delete_file(self._dpapi_path)
            return None
        except (json.JSONDecodeError, UnicodeError, ValueError, TypeError):
            if delete_on_definite_failure:
                print("Could not decrypt saved credentials")
                self._delete_file(self._dpapi_path)
            return None
        except Exception:
            print("Could not read saved credentials")
            return None
        if not isinstance(payload, dict):
            if delete_on_definite_failure:
                self._delete_file(self._dpapi_path)
            return None
        password = payload.get("password") or ""
        if not password:
            if delete_on_definite_failure:
                print("Could not decrypt saved credentials")
                self._delete_file(self._dpapi_path)
            return None
        loaded = {
            "email": payload.get("email") or "",
            "password": password,
        }
        if legacy:
            self._rewrite_with_entropy(loaded)
        return loaded

    def _rewrite_with_entropy(self, credentials: Dict[str, str]) -> None:
        """Re-protect an entropy-less blob. A failed rewrite leaves the file in place."""
        try:
            payload = json.dumps({
                "email": credentials.get("email") or "",
                "password": credentials.get("password") or "",
            }).encode("utf-8")
            blob = dpapi.protect(payload)
            temporary = self._dpapi_path + ".tmp"
            with open(temporary, "wb") as handle:
                handle.write(blob)
            os.replace(temporary, self._dpapi_path)
        except Exception:
            self._delete_file(self._dpapi_path + ".tmp")

    def _take_legacy_credentials(self) -> Optional[Dict[str, str]]:
        """
        Decrypt the Fernet remember-me files once.

        A broken pair is deleted so the next launch is a normal sign-in.
        Files are left in place when decryption works but DPAPI cannot save yet.
        """
        data_exists = os.path.exists(self._data_path)
        key_exists = os.path.exists(self._key_path)
        if not data_exists and not key_exists:
            return None
        if not data_exists or not key_exists:
            self._delete_legacy_files()
            return None
        try:
            with open(self._key_path, "rb") as handle:
                key_data = handle.read().strip()
            fernet = Fernet(key_data)
            with open(self._data_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            encrypted_password = data.get("password")
            if not encrypted_password:
                raise ValueError("missing password")
            password = fernet.decrypt(str(encrypted_password).encode("utf-8")).decode("utf-8")
            if not password:
                raise ValueError("empty password")
            return {
                "email": data.get("email") or "",
                "password": password,
            }
        except Exception:
            print("Could not decrypt legacy remember-me; removing it")
            self._delete_legacy_files()
            return None

    def _delete_legacy_files(self) -> None:
        self._delete_file(self._data_path)
        self._delete_file(self._key_path)

    @staticmethod
    def _delete_file(path: Optional[str]) -> None:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except Exception:
                print("Error removing credential file")


# ==================== CONVENIENCE FUNCTIONS ====================

_security_manager = None


def get_security_manager(app_name: str = "WorkTre") -> SecurityManager:
    """Get or create global security manager."""
    global _security_manager
    if _security_manager is None:
        _security_manager = SecurityManager(app_name)
    return _security_manager


def save_remembered_user(email: str, password: str, app_name: str = "WorkTre") -> bool:
    """Save remembered user credentials."""
    manager = get_security_manager(app_name)
    return manager.save_credentials(email, password)


def get_remembered_user(app_name: str = "WorkTre") -> Optional[Dict[str, Any]]:
    """Get remembered user credentials."""
    manager = get_security_manager(app_name)
    return manager.load_credentials()


def clear_remembered_user(app_name: str = "WorkTre") -> bool:
    """Clear remembered user credentials."""
    manager = get_security_manager(app_name)
    return manager.clear_credentials()


def encrypt_data(data: str, app_name: str = "WorkTre") -> Optional[str]:
    """Encrypt data using the security manager."""
    manager = get_security_manager(app_name)
    return manager.encrypt(data)


def decrypt_data(encrypted_data: str, app_name: str = "WorkTre") -> Optional[str]:
    """Decrypt data using the security manager."""
    manager = get_security_manager(app_name)
    return manager.decrypt(encrypted_data)


__all__ = [
    'SecurityManager',
    'save_remembered_user',
    'get_remembered_user',
    'clear_remembered_user',
    'encrypt_data',
    'decrypt_data',
    'get_security_manager',
]
