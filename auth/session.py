"""
Session management with cryptographically secure tokens.

Security features:
- 32-byte random tokens (256 bits of entropy)
- HTTP-only cookies
- Configurable session lifetime
- Session invalidation on logout
"""
import secrets
from datetime import datetime, timedelta
from typing import Optional


class SessionManager:
    """Secure session token management."""

    # Token length in bytes (32 bytes = 256 bits)
    TOKEN_BYTES = 32

    # Default session lifetime (30 days)
    DEFAULT_SESSION_LIFETIME_DAYS = 30

    @classmethod
    def generate_token(cls) -> str:
        """
        Generate a cryptographically secure session token.

        Returns:
            URL-safe base64-encoded token string
        """
        return secrets.token_urlsafe(cls.TOKEN_BYTES)

    @classmethod
    def get_session_expiry(cls, days: Optional[int] = None) -> datetime:
        """
        Calculate session expiry datetime.

        Args:
            days: Number of days until expiry (default: 30)

        Returns:
            Datetime when session expires
        """
        lifetime = days if days is not None else cls.DEFAULT_SESSION_LIFETIME_DAYS
        return datetime.utcnow() + timedelta(days=lifetime)

    @classmethod
    def is_session_expired(cls, expires_at: datetime) -> bool:
        """
        Check if a session has expired.

        Args:
            expires_at: Session expiry datetime

        Returns:
            True if expired, False otherwise
        """
        return datetime.utcnow() > expires_at

    @classmethod
    def get_cookie_settings(
        cls,
        token: str,
        max_age_seconds: Optional[int] = None
    ) -> dict:
        """
        Get secure cookie settings for session token.

        Args:
            token: Session token value
            max_age_seconds: Cookie max age (default: 30 days in seconds)

        Returns:
            Dictionary of cookie parameters
        """
        if max_age_seconds is None:
            max_age_seconds = cls.DEFAULT_SESSION_LIFETIME_DAYS * 24 * 60 * 60

        return {
            "key": "session_token",
            "value": token,
            "max_age": max_age_seconds,
            "httponly": True,  # Prevent JavaScript access
            "secure": False,    # Set to True in production with HTTPS
            "samesite": "lax"  # CSRF protection
        }

    @classmethod
    def get_logout_cookie_settings(cls) -> dict:
        """
        Get cookie settings for logout (expires immediately).

        Returns:
            Dictionary of cookie parameters to clear session
        """
        return {
            "key": "session_token",
            "value": "",
            "max_age": 0,
            "httponly": True,
            "secure": False,
            "samesite": "lax"
        }
