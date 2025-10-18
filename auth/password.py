"""
Password hashing and verification using bcrypt.

Security standards:
- Bcrypt with cost factor 12 (2^12 iterations)
- Automatic salt generation
- Timing-safe comparison
"""
import bcrypt
from typing import Tuple


class PasswordManager:
    """Secure password hashing and verification."""

    # Bcrypt cost factor (2^12 = 4096 iterations)
    # Recommended by OWASP for 2024
    BCRYPT_ROUNDS = 12

    # Password policy
    MIN_LENGTH = 8
    MAX_LENGTH = 128

    @classmethod
    def hash_password(cls, password: str) -> str:
        """
        Hash a password using bcrypt.

        Args:
            password: Plain text password

        Returns:
            Bcrypt hash string (includes salt)

        Raises:
            ValueError: If password doesn't meet requirements
        """
        # Validate password
        if not password or len(password) < cls.MIN_LENGTH:
            raise ValueError(f"Password must be at least {cls.MIN_LENGTH} characters")
        if len(password) > cls.MAX_LENGTH:
            raise ValueError(f"Password must be less than {cls.MAX_LENGTH} characters")

        # Generate salt and hash
        salt = bcrypt.gensalt(rounds=cls.BCRYPT_ROUNDS)
        password_bytes = password.encode('utf-8')
        hashed = bcrypt.hashpw(password_bytes, salt)

        return hashed.decode('utf-8')

    @classmethod
    def verify_password(cls, password: str, password_hash: str) -> bool:
        """
        Verify a password against a hash.

        Uses timing-safe comparison to prevent timing attacks.

        Args:
            password: Plain text password to verify
            password_hash: Stored bcrypt hash

        Returns:
            True if password matches, False otherwise
        """
        try:
            password_bytes = password.encode('utf-8')
            hash_bytes = password_hash.encode('utf-8')
            return bcrypt.checkpw(password_bytes, hash_bytes)
        except Exception:
            # Invalid hash format or other error
            return False

    @classmethod
    def validate_password_strength(cls, password: str) -> Tuple[bool, str]:
        """
        Validate password strength.

        Args:
            password: Password to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not password:
            return False, "Password is required"

        if len(password) < cls.MIN_LENGTH:
            return False, f"Password must be at least {cls.MIN_LENGTH} characters"

        if len(password) > cls.MAX_LENGTH:
            return False, f"Password must be less than {cls.MAX_LENGTH} characters"

        # All checks passed
        return True, ""
