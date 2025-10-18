"""
Rate limiting for login attempts to prevent brute force attacks.

Security features:
- 5 attempts per 15-minute window
- Account lockout after threshold
- Automatic cleanup of old attempts
- IP-based tracking
"""
from datetime import datetime, timedelta
from typing import Dict, Tuple
from collections import defaultdict


class RateLimiter:
    """Rate limiter for login attempts."""

    # Maximum login attempts per window
    MAX_ATTEMPTS = 5

    # Time window in minutes
    WINDOW_MINUTES = 15

    # In-memory storage of login attempts
    # Format: {username: [(timestamp, ip), ...]}
    _attempts: Dict[str, list] = defaultdict(list)

    @classmethod
    def record_attempt(cls, username: str, ip_address: str) -> None:
        """
        Record a failed login attempt.

        Args:
            username: Username that was attempted
            ip_address: IP address of the attempt
        """
        cls._attempts[username].append((datetime.utcnow(), ip_address))

    @classmethod
    def check_rate_limit(cls, username: str) -> Tuple[bool, int, int]:
        """
        Check if username has exceeded rate limit.

        Args:
            username: Username to check

        Returns:
            Tuple of (is_allowed, attempts_count, seconds_until_reset)
        """
        # Clean up old attempts first
        cls._cleanup_old_attempts(username)

        # Get recent attempts
        attempts = cls._attempts.get(username, [])
        attempt_count = len(attempts)

        # Check if over limit
        if attempt_count >= cls.MAX_ATTEMPTS:
            # Calculate time until reset
            oldest_attempt = attempts[0][0]
            window_end = oldest_attempt + timedelta(minutes=cls.WINDOW_MINUTES)
            seconds_until_reset = int((window_end - datetime.utcnow()).total_seconds())

            return False, attempt_count, max(0, seconds_until_reset)

        return True, attempt_count, 0

    @classmethod
    def clear_attempts(cls, username: str) -> None:
        """
        Clear all login attempts for a username (e.g., after successful login).

        Args:
            username: Username to clear
        """
        if username in cls._attempts:
            del cls._attempts[username]

    @classmethod
    def _cleanup_old_attempts(cls, username: str) -> None:
        """
        Remove attempts older than the time window.

        Args:
            username: Username to clean up
        """
        if username not in cls._attempts:
            return

        cutoff_time = datetime.utcnow() - timedelta(minutes=cls.WINDOW_MINUTES)
        cls._attempts[username] = [
            (timestamp, ip)
            for timestamp, ip in cls._attempts[username]
            if timestamp > cutoff_time
        ]

        # Remove empty entries
        if not cls._attempts[username]:
            del cls._attempts[username]

    @classmethod
    def get_attempt_info(cls, username: str) -> Dict:
        """
        Get detailed information about login attempts.

        Args:
            username: Username to check

        Returns:
            Dictionary with attempt details
        """
        cls._cleanup_old_attempts(username)
        attempts = cls._attempts.get(username, [])

        return {
            "attempt_count": len(attempts),
            "max_attempts": cls.MAX_ATTEMPTS,
            "is_locked": len(attempts) >= cls.MAX_ATTEMPTS,
            "window_minutes": cls.WINDOW_MINUTES
        }
