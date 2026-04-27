"""
src/utils/security.py
Security utilities for encryption and secure storage.
"""

import os
import json
import base64
from typing import Optional, Dict, Any, Union
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend

from ..config import settings
from ..platform.utils import get_app_data_dir
from .file_utils import ensure_directory


class SecurityManager:
    """Manager for security operations."""

    def __init__(self, app_name: str = "WorkTre"):
        self.app_name = app_name
        self._fernet = None
        self._key_path = None
        self._data_path = None
        self._initialize_paths()

    def _initialize_paths(self):
        """Initialize file paths."""
        base_dir = get_app_data_dir(self.app_name)
        ensure_directory(base_dir)

        self._key_path = os.path.join(base_dir, settings.KEY_FILE_NAME)
        self._data_path = os.path.join(base_dir, settings.DATA_FILE_NAME)

    def _generate_key_from_password(self, password: str, salt: bytes = None) -> tuple[bytes, bytes]:
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

    def _load_or_create_key(self) -> Optional[Fernet]:
        """Load existing key or create new one."""
        if self._fernet:
            return self._fernet

        try:
            if os.path.exists(self._key_path):
                with open(self._key_path, 'rb') as f:
                    key_data = f.read()

                # Check if it's a Fernet key (32 bytes base64 encoded)
                try:
                    self._fernet = Fernet(key_data)
                except Exception:
                    # Try to decode if it's a raw key
                    key = base64.urlsafe_b64encode(key_data)
                    self._fernet = Fernet(key)
            else:
                # Generate new Fernet key
                key = Fernet.generate_key()
                with open(self._key_path, 'wb') as f:
                    f.write(key)
                self._fernet = Fernet(key)

            return self._fernet

        except Exception as e:
            print(f"Error loading/creating key: {e}")
            return None

    def encrypt(self, data: str) -> Optional[str]:
        """Encrypt data using Fernet."""
        fernet = self._load_or_create_key()
        if not fernet:
            return None

        try:
            encrypted = fernet.encrypt(data.encode())
            return encrypted.decode()
        except Exception as e:
            print(f"Error encrypting data: {e}")
            return None

    def decrypt(self, encrypted_data: str) -> Optional[str]:
        """Decrypt data using Fernet."""
        fernet = self._load_or_create_key()
        if not fernet:
            return None

        try:
            decrypted = fernet.decrypt(encrypted_data.encode())
            return decrypted.decode()
        except InvalidToken:
            print("Invalid token - data may be corrupted")
            return None
        except Exception as e:
            print(f"Error decrypting data: {e}")
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
            # Generate key from password
            key, salt = self._generate_key_from_password(password)
            fernet = Fernet(key)

            # Encrypt data
            encrypted = fernet.encrypt(data.encode())

            return {
                "data": encrypted.decode(),
                "salt": base64.b64encode(salt).decode()
            }
        except Exception as e:
            print(f"Error encrypting with password: {e}")
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
            # Decode salt
            salt = base64.b64decode(salt_b64)

            # Generate key from password
            key, _ = self._generate_key_from_password(password, salt)
            fernet = Fernet(key)

            # Decrypt data
            decrypted = fernet.decrypt(encrypted_data.encode())
            return decrypted.decode()

        except InvalidToken:
            print("Invalid password or corrupted data")
            return None
        except Exception as e:
            print(f"Error decrypting with password: {e}")
            return None

    def save_credentials(self, email: str, password: str) -> bool:
        """Save encrypted credentials."""
        if not email or not password:
            return False

        try:
            encrypted_password = self.encrypt(password)
            if not encrypted_password:
                return False

            data = {
                "email": email,
                "password": encrypted_password,
                "timestamp": os.path.getmtime(self._key_path) if os.path.exists(self._key_path) else None
            }

            with open(self._data_path, 'w') as f:
                json.dump(data, f, indent=2)

            return True

        except Exception as e:
            print(f"Error saving credentials: {e}")
            return False

    def load_credentials(self) -> Optional[Dict[str, Any]]:
        """Load and decrypt credentials."""
        if not os.path.exists(self._data_path):
            return None

        try:
            with open(self._data_path, 'r') as f:
                data = json.load(f)

            encrypted_password = data.get("password")
            if not encrypted_password:
                return None

            decrypted_password = self.decrypt(encrypted_password)
            if not decrypted_password:
                return None

            return {
                "email": data.get("email", ""),
                "password": decrypted_password
            }

        except json.JSONDecodeError:
            print("Corrupted credentials file")
            return None
        except Exception as e:
            print(f"Error loading credentials: {e}")
            return None

    def clear_credentials(self) -> bool:
        """Clear saved credentials."""
        try:
            if os.path.exists(self._data_path):
                os.remove(self._data_path)
            return True
        except Exception as e:
            print(f"Error clearing credentials: {e}")
            return False

    def has_saved_credentials(self) -> bool:
        """Check if credentials are saved."""
        return os.path.exists(self._data_path)

    def get_key_info(self) -> Dict[str, Any]:
        """Get information about the encryption key."""
        return {
            "key_exists": os.path.exists(self._key_path),
            "data_exists": os.path.exists(self._data_path),
            "key_path": self._key_path,
            "data_path": self._data_path,
            "key_size": os.path.getsize(self._key_path) if os.path.exists(self._key_path) else 0,
            "data_size": os.path.getsize(self._data_path) if os.path.exists(self._data_path) else 0,
        }

    def rotate_key(self) -> bool:
        """
        Rotate encryption key and re-encrypt existing data.

        Returns:
            True if successful
        """
        # Load existing credentials
        credentials = self.load_credentials()

        # Generate new key
        new_key = Fernet.generate_key()

        # Save new key
        try:
            with open(self._key_path, 'wb') as f:
                f.write(new_key)

            # Re-initialize fernet with new key
            self._fernet = Fernet(new_key)

            # Re-encrypt credentials if they exist
            if credentials:
                self.save_credentials(credentials["email"], credentials["password"])

            return True
        except Exception as e:
            print(f"Error rotating key: {e}")
            return False


# ==================== CONVENIENCE FUNCTIONS ====================

# Global security manager instance
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


# ==================== EXPORTS ====================

__all__ = [
    'SecurityManager',
    'save_remembered_user',
    'get_remembered_user',
    'clear_remembered_user',
    'encrypt_data',
    'decrypt_data',
    'get_security_manager',
]