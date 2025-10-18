"""
Encryption utilities for sensitive data storage.
Provides symmetric encryption for passwords and other sensitive settings.
"""
import logging
from pathlib import Path
from cryptography.fernet import Fernet
from typing import Optional

logger = logging.getLogger(__name__)


class SecureSettings:
    """
    Handles encryption/decryption of sensitive settings data.

    Uses Fernet (symmetric encryption) with a persistent key stored in the data directory.
    The encryption key is generated once and reused across application restarts.
    """

    def __init__(self, key_path: str = './data/.encryption_key'):
        """
        Initialize the encryption handler.

        Args:
            key_path: Path to store the encryption key file
        """
        self.key_path = Path(key_path)
        self.cipher = None
        self._initialize_encryption()

    def _initialize_encryption(self):
        """Initialize or load encryption key."""
        try:
            # Ensure data directory exists
            self.key_path.parent.mkdir(parents=True, exist_ok=True)

            if self.key_path.exists():
                # Load existing key
                self.key = self.key_path.read_bytes()
                logger.info("Loaded existing encryption key")
            else:
                # Generate new key
                self.key = Fernet.generate_key()
                self.key_path.write_bytes(self.key)
                # Restrict permissions (owner read/write only)
                self.key_path.chmod(0o600)
                logger.info("Generated new encryption key and secured with 0o600 permissions")

            self.cipher = Fernet(self.key)

        except Exception as e:
            logger.error(f"Failed to initialize encryption: {e}")
            raise

    def encrypt(self, value: str) -> str:
        """
        Encrypt a string value.

        Args:
            value: Plain text string to encrypt

        Returns:
            Encrypted string (base64 encoded)
        """
        if not value:
            return value

        try:
            encrypted = self.cipher.encrypt(value.encode())
            return encrypted.decode()
        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise

    def decrypt(self, value: str) -> str:
        """
        Decrypt an encrypted string value.

        Args:
            value: Encrypted string (base64 encoded)

        Returns:
            Decrypted plain text string
        """
        if not value:
            return value

        try:
            decrypted = self.cipher.decrypt(value.encode())
            return decrypted.decode()
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise

    def is_encrypted(self, value: str) -> bool:
        """
        Check if a value appears to be encrypted.

        Args:
            value: String to check

        Returns:
            True if value looks like encrypted data (Fernet format)
        """
        if not value:
            return False

        try:
            # Fernet tokens start with 'gAAAAA' when base64 decoded
            # This is a heuristic check
            self.cipher.decrypt(value.encode())
            return True
        except Exception:
            return False


# Global instance for application-wide use
_secure_settings_instance: Optional[SecureSettings] = None


def get_secure_settings() -> SecureSettings:
    """
    Get or create the global SecureSettings instance.

    Returns:
        SecureSettings instance
    """
    global _secure_settings_instance
    if _secure_settings_instance is None:
        _secure_settings_instance = SecureSettings()
    return _secure_settings_instance
