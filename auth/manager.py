"""
Authentication Manager - Orchestrates all authentication operations.

Handles:
- User creation and validation
- Login/logout flows
- Session management
- Rate limiting
- Audit logging
"""
import logging
from datetime import datetime
from typing import Optional, Dict, Tuple
from database.db import Database
from auth.password import PasswordManager
from auth.session import SessionManager
from auth.rate_limit import RateLimiter

logger = logging.getLogger(__name__)


class AuthManager:
    """Main authentication manager."""

    def __init__(self, db: Database):
        """
        Initialize auth manager.

        Args:
            db: Database manager instance
        """
        self.db = db
        self.password_manager = PasswordManager()
        self.session_manager = SessionManager()
        self.rate_limiter = RateLimiter()

    async def setup_required(self) -> bool:
        """
        Check if initial setup is required.

        Returns:
            True if no users exist, False otherwise
        """
        conn = await self.db._get_connection()
        async with conn.execute("SELECT COUNT(*) FROM users") as cursor:
            row = await cursor.fetchone()
            user_count = row[0] if row else 0

        return user_count == 0

    async def create_user(
        self,
        username: str,
        password: str,
        ip_address: Optional[str] = None
    ) -> Tuple[bool, str, Optional[int]]:
        """
        Create a new user account.

        Args:
            username: Username (3-50 chars, alphanumeric + hyphens/underscores)
            password: Password (8-128 chars)
            ip_address: IP address for audit log

        Returns:
            Tuple of (success, message, user_id)
        """
        # Validate password strength
        is_valid, error_msg = self.password_manager.validate_password_strength(password)
        if not is_valid:
            await self._log_audit_event(
                None, username, "user_creation", ip_address, False, error_msg
            )
            return False, error_msg, None

        # Check if user already exists
        conn = await self.db._get_connection()
        async with conn.execute(
            "SELECT id FROM users WHERE username = ?",
            (username.lower(),)
        ) as cursor:
            existing_user = await cursor.fetchone()

        if existing_user:
            await self._log_audit_event(
                None, username, "user_creation", ip_address, False, "Username already exists"
            )
            return False, "Username already exists", None

        # Hash password
        try:
            password_hash = self.password_manager.hash_password(password)
        except Exception as e:
            logger.error(f"Failed to hash password: {e}")
            return False, "Internal error", None

        # Create user
        try:
            async with conn.execute(
                """
                INSERT INTO users (username, password_hash, created_at, is_active)
                VALUES (?, ?, ?, 1)
                """,
                (username.lower(), password_hash, datetime.utcnow().isoformat())
            ) as cursor:
                user_id = cursor.lastrowid

            await conn.commit()

            await self._log_audit_event(
                user_id, username, "user_creation", ip_address, True, None
            )

            logger.info(f"User created: {username} (ID: {user_id})")
            return True, "User created successfully", user_id

        except Exception as e:
            logger.error(f"Failed to create user: {e}")
            await conn.rollback()
            return False, "Failed to create user", None

    async def login(
        self,
        username: str,
        password: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Authenticate user and create session.

        Args:
            username: Username
            password: Password
            ip_address: Client IP address
            user_agent: Client user agent

        Returns:
            Tuple of (success, message, session_token)
        """
        username = username.lower()

        # Check rate limit
        is_allowed, attempt_count, seconds_until_reset = self.rate_limiter.check_rate_limit(username)
        if not is_allowed:
            minutes_until_reset = (seconds_until_reset // 60) + 1
            await self._log_audit_event(
                None, username, "login", ip_address, False, "Rate limit exceeded"
            )
            return False, f"Too many failed attempts. Try again in {minutes_until_reset} minutes.", None

        # Get user from database
        conn = await self.db._get_connection()
        async with conn.execute(
            "SELECT id, username, password_hash, is_active FROM users WHERE username = ?",
            (username,)
        ) as cursor:
            user = await cursor.fetchone()

        if not user:
            # User doesn't exist - record attempt and return generic error
            self.rate_limiter.record_attempt(username, ip_address or "unknown")
            await self._log_audit_event(
                None, username, "login", ip_address, False, "Invalid credentials"
            )
            return False, "Invalid username or password", None

        user_id, db_username, password_hash, is_active = user

        # Check if account is active
        if not is_active:
            await self._log_audit_event(
                user_id, username, "login", ip_address, False, "Account disabled"
            )
            return False, "Account is disabled", None

        # Verify password
        if not self.password_manager.verify_password(password, password_hash):
            # Wrong password - record attempt
            self.rate_limiter.record_attempt(username, ip_address or "unknown")
            await self._log_audit_event(
                user_id, username, "login", ip_address, False, "Invalid credentials"
            )
            return False, "Invalid username or password", None

        # Success! Clear rate limit attempts
        self.rate_limiter.clear_attempts(username)

        # Create session
        session_token = self.session_manager.generate_token()
        expires_at = self.session_manager.get_session_expiry()

        try:
            await conn.execute(
                """
                INSERT INTO sessions (user_id, session_token, created_at, expires_at, ip_address, user_agent)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, session_token, datetime.utcnow().isoformat(), expires_at.isoformat(), ip_address, user_agent)
            )

            # Update last login
            await conn.execute(
                "UPDATE users SET last_login_at = ? WHERE id = ?",
                (datetime.utcnow().isoformat(), user_id)
            )

            await conn.commit()

            await self._log_audit_event(
                user_id, username, "login", ip_address, True, None
            )

            logger.info(f"User logged in: {username} from {ip_address}")
            return True, "Login successful", session_token

        except Exception as e:
            logger.error(f"Failed to create session: {e}")
            await conn.rollback()
            return False, "Login failed", None

    async def logout(self, session_token: str, ip_address: Optional[str] = None) -> bool:
        """
        Logout user by invalidating session.

        Args:
            session_token: Session token to invalidate
            ip_address: Client IP address for audit log

        Returns:
            True if logout successful
        """
        conn = await self.db._get_connection()

        # Get user info before deleting session
        async with conn.execute(
            """
            SELECT u.id, u.username
            FROM sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.session_token = ?
            """,
            (session_token,)
        ) as cursor:
            user = await cursor.fetchone()

        # Delete session
        await conn.execute(
            "DELETE FROM sessions WHERE session_token = ?",
            (session_token,)
        )
        await conn.commit()

        if user:
            user_id, username = user
            await self._log_audit_event(
                user_id, username, "logout", ip_address, True, None
            )
            logger.info(f"User logged out: {username}")

        return True

    async def validate_session(self, session_token: str) -> Optional[Dict]:
        """
        Validate session token and return user info.

        Args:
            session_token: Session token to validate

        Returns:
            User dict if valid, None otherwise
        """
        if not session_token:
            return None

        conn = await self.db._get_connection()
        async with conn.execute(
            """
            SELECT u.id, u.username, u.created_at, u.last_login_at, s.expires_at
            FROM sessions s
            JOIN users u ON s.user_id = u.id
            WHERE s.session_token = ? AND u.is_active = 1
            """,
            (session_token,)
        ) as cursor:
            row = await cursor.fetchone()

        if not row:
            return None

        user_id, username, created_at, last_login_at, expires_at = row

        # Check if session expired
        expires_datetime = datetime.fromisoformat(expires_at)
        if self.session_manager.is_session_expired(expires_datetime):
            # Delete expired session
            await conn.execute(
                "DELETE FROM sessions WHERE session_token = ?",
                (session_token,)
            )
            await conn.commit()
            return None

        return {
            "id": user_id,
            "username": username,
            "created_at": created_at,
            "last_login_at": last_login_at
        }

    async def cleanup_expired_sessions(self) -> int:
        """
        Remove expired sessions from database.

        Returns:
            Number of sessions deleted
        """
        conn = await self.db._get_connection()
        now = datetime.utcnow().isoformat()

        async with conn.execute(
            "DELETE FROM sessions WHERE expires_at < ?",
            (now,)
        ) as cursor:
            deleted_count = cursor.rowcount

        await conn.commit()

        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} expired sessions")

        return deleted_count

    async def _log_audit_event(
        self,
        user_id: Optional[int],
        username: str,
        event_type: str,
        ip_address: Optional[str],
        success: bool,
        failure_reason: Optional[str]
    ) -> None:
        """
        Log authentication event to audit log.

        Args:
            user_id: User ID (None if user doesn't exist)
            username: Username
            event_type: Type of event (login, logout, user_creation, etc.)
            ip_address: Client IP address
            success: Whether the event succeeded
            failure_reason: Reason for failure (if applicable)
        """
        try:
            conn = await self.db._get_connection()
            await conn.execute(
                """
                INSERT INTO auth_audit_log (user_id, username, event_type, ip_address, success, failure_reason, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (user_id, username, event_type, ip_address, 1 if success else 0, failure_reason, datetime.utcnow().isoformat())
            )
            await conn.commit()
        except Exception as e:
            logger.error(f"Failed to log audit event: {e}")
