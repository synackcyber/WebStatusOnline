"""
Database module for WebStatus.
Handles all SQLite operations asynchronously with connection pooling.
"""
import aiosqlite
import json
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
from pathlib import Path
import asyncio
import logging
from utils.encryption import get_secure_settings

logger = logging.getLogger(__name__)

# Fields that should be encrypted when stored in settings
SENSITIVE_FIELDS = {
    'smtp.password',
    'smtp.username',  # Also encrypt username for extra security
    'webhook.api_key',
    'backup.encryption_key'
}

# Whitelist of valid settings categories
VALID_CATEGORIES = {
    'smtp',
    'backup',
    'webhook',
    'relay',
    'system',
    'monitoring'
}


def utc_now() -> str:
    """Return current UTC timestamp in ISO format with timezone."""
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, db_path: str = "data/monitoring.db"):
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = None
        self._connection_lock = asyncio.Lock()

    async def _get_connection(self) -> aiosqlite.Connection:
        """
        Get or create a persistent database connection with optimizations.

        Benefits:
        - Connection pooling (reuses single connection)
        - WAL mode enabled (10-100x faster concurrent access)
        - Foreign key constraints enforced
        - 64MB cache for better performance
        """
        async with self._connection_lock:
            if self._connection is None:
                self._connection = await aiosqlite.connect(
                    self.db_path,
                    timeout=30.0,
                    check_same_thread=False
                )
                # Enable Write-Ahead Logging for better concurrency
                await self._connection.execute("PRAGMA journal_mode=WAL")
                # Enable foreign key constraints (not enabled by default in SQLite)
                await self._connection.execute("PRAGMA foreign_keys=ON")
                # Optimize for performance
                await self._connection.execute("PRAGMA synchronous=NORMAL")
                await self._connection.execute("PRAGMA cache_size=-64000")  # 64MB
                await self._connection.execute("PRAGMA temp_store=MEMORY")
                await self._connection.commit()
                logger.info(f"Database connection established with WAL mode: {self.db_path}")
            return self._connection

    async def close(self):
        """Close the database connection gracefully."""
        async with self._connection_lock:
            if self._connection:
                await self._connection.close()
                self._connection = None
                logger.info("Database connection closed")


    async def initialize(self):
        """
        Initialize database with required tables.

        This creates a clean, compacted schema with all fields included.
        All migrations have been consolidated into the base schema.
        """
        db = await self._get_connection()

        # ===== MONITORING TABLES =====

        # Targets table - COMPACTED SCHEMA (all migrations consolidated)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS targets (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                address TEXT NOT NULL,
                device_type TEXT DEFAULT 'other',
                check_interval INTEGER DEFAULT 60,
                failure_threshold INTEGER DEFAULT 3,
                current_failures INTEGER DEFAULT 0,
                status TEXT DEFAULT 'unknown',
                last_check TEXT,
                last_status_change TEXT,
                total_checks INTEGER DEFAULT 0,
                failed_checks INTEGER DEFAULT 0,
                enabled INTEGER DEFAULT 1,
                audio_behavior TEXT DEFAULT 'normal',
                audio_down_alert TEXT,
                audio_up_alert TEXT,
                acknowledged INTEGER DEFAULT 0,
                acknowledged_at TEXT,
                total_uptime INTEGER DEFAULT 0,
                total_downtime INTEGER DEFAULT 0,
                public_visible INTEGER DEFAULT 0,
                public_name TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Check history table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS check_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_id TEXT NOT NULL,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                status TEXT NOT NULL,
                response_time REAL,
                error_message TEXT,
                FOREIGN KEY (target_id) REFERENCES targets(id) ON DELETE CASCADE
            )
        """)

        # Alert log table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS alert_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target_id TEXT NOT NULL,
                timestamp TEXT DEFAULT CURRENT_TIMESTAMP,
                event_type TEXT NOT NULL,
                message TEXT,
                FOREIGN KEY (target_id) REFERENCES targets(id) ON DELETE CASCADE
            )
        """)

        # Settings table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                category TEXT NOT NULL,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Public tokens table (for status page sharing)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS public_tokens (
                token TEXT PRIMARY KEY,
                name TEXT,
                view_mode TEXT DEFAULT 'both',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                last_accessed TEXT,
                access_count INTEGER DEFAULT 0,
                enabled INTEGER DEFAULT 1
            )
        """)

        # ===== AUTHENTICATION TABLES =====

        # Users table - Single user per instance
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL,
                last_login_at TEXT,
                is_active INTEGER DEFAULT 1
            )
        """)

        # Sessions table - Active user sessions
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                session_token TEXT UNIQUE NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                ip_address TEXT,
                user_agent TEXT,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
            )
        """)

        # Auth audit log - Security event logging
        await db.execute("""
            CREATE TABLE IF NOT EXISTS auth_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                username TEXT,
                event_type TEXT NOT NULL,
                ip_address TEXT,
                user_agent TEXT,
                success INTEGER NOT NULL,
                failure_reason TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE SET NULL
            )
        """)

        # ===== PERFORMANCE INDEXES =====

        # Performance indexes - significantly speeds up filtered queries
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_targets_alert_status
            ON targets(status, enabled, acknowledged, audio_behavior)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_check_history_time
            ON check_history(timestamp DESC)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_check_history_target
            ON check_history(target_id, timestamp DESC)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_alert_log_target
            ON alert_log(target_id, timestamp DESC)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_settings_category
            ON settings(category)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_public_tokens_enabled
            ON public_tokens(enabled)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_token
            ON sessions (session_token)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_sessions_expires
            ON sessions (expires_at)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_event_type
            ON auth_audit_log (event_type)
        """)
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_created_at
            ON auth_audit_log (created_at)
        """)

        await db.commit()
        logger.info("Database schema initialized successfully (all tables including auth)")

    # Target CRUD operations
    async def create_target(self, target: Dict) -> str:
        """Create a new target."""
        db = await self._get_connection()
        await db.execute("""
            INSERT INTO targets (id, name, type, address, check_interval,
                               failure_threshold, enabled, audio_behavior,
                               audio_down_alert, audio_up_alert,
                               acknowledged, total_uptime, total_downtime, device_type)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            target['id'], target['name'], target['type'], target['address'],
            target.get('check_interval', 60),
            target.get('failure_threshold', 3),
            target.get('enabled', 1),
            target.get('audio_behavior', 'normal'),
            target.get('audio_down_alert'),
            target.get('audio_up_alert'),
            target.get('acknowledged', 0),
            target.get('total_uptime', 0),
            target.get('total_downtime', 0),
            target.get('device_type', 'other')
        ))
        await db.commit()
        return target['id']

    async def get_target(self, target_id: str) -> Optional[Dict]:
        """Get a target by ID."""
        db = await self._get_connection()
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM targets WHERE id = ?", (target_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)
            return None

    async def get_all_targets(self) -> List[Dict]:
        """Get all targets."""
        db = await self._get_connection()
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM targets ORDER BY name") as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_enabled_targets(self) -> List[Dict]:
        """Get all enabled targets."""
        db = await self._get_connection()
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM targets WHERE enabled = 1 ORDER BY name"
        ) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_down_unacknowledged_targets(self) -> List[Dict]:
        """
        Get targets that need alerting - optimized query.
        Returns down targets that are enabled, not acknowledged, and not silent.
        Ordered by urgency (urgent -> normal).
        """
        db = await self._get_connection()
        db.row_factory = aiosqlite.Row

        # Debug: Log the query
        logger.debug("Query: SELECT * FROM targets WHERE status='down' AND enabled=1 AND acknowledged=0 AND audio_behavior!='silent'")

        async with db.execute("""
            SELECT * FROM targets
            WHERE status = 'down'
            AND enabled = 1
            AND acknowledged = 0
            AND audio_behavior != 'silent'
            ORDER BY
                CASE audio_behavior
                    WHEN 'urgent' THEN 1
                    WHEN 'normal' THEN 2
                    ELSE 3
                END
        """) as cursor:
            rows = await cursor.fetchall()
            targets = [dict(row) for row in rows]

            # Debug: Log what we found
            if targets:
                logger.info(f"DB Query returned {len(targets)} target(s) needing alerts: {[t['name'] for t in targets]}")
            else:
                logger.warning("DB Query returned 0 targets needing alerts")

            return targets

    async def update_target(self, target_id: str, updates: Dict) -> bool:
        """Update a target."""
        allowed_fields = [
            'name', 'type', 'address', 'check_interval',
            'failure_threshold', 'enabled', 'audio_behavior',
            'audio_down_alert', 'audio_up_alert',
            'acknowledged', 'acknowledged_at', 'total_uptime', 'total_downtime',
            'device_type'
        ]
        update_fields = {k: v for k, v in updates.items() if k in allowed_fields}

        if not update_fields:
            return False

        set_clause = ", ".join([f"{k} = ?" for k in update_fields.keys()])
        values = list(update_fields.values()) + [target_id]

        db = await self._get_connection()
        await db.execute(
            f"UPDATE targets SET {set_clause} WHERE id = ?",
            values
        )
        await db.commit()
        return True

    async def delete_target(self, target_id: str) -> bool:
        """Delete a target."""
        db = await self._get_connection()
        await db.execute("DELETE FROM targets WHERE id = ?", (target_id,))
        await db.commit()
        return True

    async def acknowledge_target(self, target_id: str) -> bool:
        """Acknowledge a target alert."""
        now = utc_now()
        db = await self._get_connection()
        await db.execute("""
            UPDATE targets
            SET acknowledged = 1, acknowledged_at = ?
            WHERE id = ?
        """, (now, target_id))
        await db.commit()
        return True

    async def unacknowledge_target(self, target_id: str) -> bool:
        """Remove acknowledgment from a target."""
        db = await self._get_connection()
        await db.execute("""
            UPDATE targets
            SET acknowledged = 0, acknowledged_at = NULL
            WHERE id = ?
        """, (target_id,))
        await db.commit()
        return True

    async def update_target_status(self, target_id: str, status: str,
                                   current_failures: int, response_time: Optional[float] = None):
        """Update target status after a check."""
        now = utc_now()

        db = await self._get_connection()
        # Get current status and last status change to check if it changed and calculate time delta
        async with db.execute(
            "SELECT status, last_status_change FROM targets WHERE id = ?", (target_id,)
        ) as cursor:
            row = await cursor.fetchone()
            old_status = row[0] if row else 'unknown'
            last_status_change = row[1] if row and row[1] else now

        # Calculate time spent in previous status
        time_delta = 0
        if last_status_change:
            try:
                last_time = datetime.fromisoformat(last_status_change)
                current_time = datetime.fromisoformat(now)
                time_delta = int((current_time - last_time).total_seconds())
            except (ValueError, TypeError) as e:
                logger.debug(f"Failed to calculate time delta: {e}")
                time_delta = 0

        # Update target
        update_query = """
            UPDATE targets
            SET status = ?,
                current_failures = ?,
                last_check = ?,
                total_checks = total_checks + 1,
                failed_checks = failed_checks + ?
        """
        params = [status, current_failures, now, 1 if status == 'down' else 0]

        # Update last_status_change if status changed
        if old_status != status:
            update_query += ", last_status_change = ?"
            params.append(now)

            # Accumulate uptime/downtime based on previous status
            if old_status == 'up' and time_delta > 0:
                update_query += ", total_uptime = total_uptime + ?"
                params.append(time_delta)
            elif old_status == 'down' and time_delta > 0:
                update_query += ", total_downtime = total_downtime + ?"
                params.append(time_delta)

            # Clear acknowledgment when target recovers
            if status == 'up':
                update_query += ", acknowledged = 0, acknowledged_at = NULL"

        update_query += " WHERE id = ?"
        params.append(target_id)

        await db.execute(update_query, params)
        await db.commit()

    # Check history operations
    async def add_check_history(self, target_id: str, status: str,
                               response_time: Optional[float] = None,
                               error_message: Optional[str] = None):
        """Add a check history entry."""
        db = await self._get_connection()
        await db.execute("""
            INSERT INTO check_history (target_id, status, response_time, error_message)
            VALUES (?, ?, ?, ?)
        """, (target_id, status, response_time, error_message))
        await db.commit()

    async def get_check_history(self, target_id: str, limit: int = 100) -> List[Dict]:
        """Get check history for a target."""
        db = await self._get_connection()
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT * FROM check_history
            WHERE target_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (target_id, limit)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def cleanup_old_history(self, days: int = 30):
        """Clean up check history older than specified days."""
        db = await self._get_connection()
        await db.execute("""
            DELETE FROM check_history
            WHERE timestamp < datetime('now', '-' || ? || ' days')
        """, (days,))
        await db.commit()

    async def get_target_history(self, target_id: str, start_time: str, end_time: str) -> List[Dict]:
        """
        Get check history for a target within a time range.
        Used for timeline visualization in public dashboard.

        Args:
            target_id: Target ID
            start_time: Start timestamp (ISO format)
            end_time: End timestamp (ISO format)

        Returns:
            List of history records with timestamp and status
        """
        # Convert ISO format timestamps to SQLite format (replace 'T' with space)
        # to ensure string comparison works correctly
        start_time_sql = start_time.replace('T', ' ').split('.')[0]  # Remove microseconds too
        end_time_sql = end_time.replace('T', ' ').split('.')[0]

        db = await self._get_connection()
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT timestamp, status
            FROM check_history
            WHERE target_id = ?
              AND timestamp >= ?
              AND timestamp <= ?
            ORDER BY timestamp ASC
        """, (target_id, start_time_sql, end_time_sql)) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_uptime_metrics(self, target_id: str) -> Dict:
        """
        Calculate uptime metrics from check history (industry standard).
        Returns uptime percentages for 24h, 7d, and 30d windows.
        """
        db = await self._get_connection()
        # Calculate for three time windows: 24h, 7d, 30d
        windows = {
            '24h': 1,
            '7d': 7,
            '30d': 30
        }

        metrics = {}

        for label, days in windows.items():
            async with db.execute("""
                SELECT
                    COUNT(*) as total_checks,
                    SUM(CASE WHEN status='up' THEN 1 ELSE 0 END) as up_checks
                FROM check_history
                WHERE target_id = ?
                AND timestamp > datetime('now', '-' || ? || ' days')
            """, (target_id, days)) as cursor:
                row = await cursor.fetchone()
                if row and row[0] > 0:
                    total = row[0]
                    up = row[1] or 0
                    raw_pct = (up / total) * 100

                    # Round to whole numbers for cleaner display
                    uptime_pct = round(raw_pct)
                else:
                    # No data - assume 100%
                    total = 0
                    up = 0
                    uptime_pct = 100

                metrics[f'uptime_{label}'] = uptime_pct
                metrics[f'checks_{label}'] = total
                metrics[f'up_checks_{label}'] = up

        return metrics

    # Alert log operations
    async def add_alert_log(self, target_id: str, event_type: str, message: str):
        """Add an alert log entry."""
        db = await self._get_connection()
        await db.execute("""
            INSERT INTO alert_log (target_id, event_type, message)
            VALUES (?, ?, ?)
        """, (target_id, event_type, message))
        await db.commit()

    async def get_alert_log(self, target_id: Optional[str] = None,
                           limit: int = 100) -> List[Dict]:
        """Get alert log entries."""
        db = await self._get_connection()
        db.row_factory = aiosqlite.Row
        if target_id:
            query = """
                SELECT * FROM alert_log
                WHERE target_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """
            params = (target_id, limit)
        else:
            query = """
                SELECT * FROM alert_log
                ORDER BY timestamp DESC
                LIMIT ?
            """
            params = (limit,)

        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(row) for row in rows]

    async def get_statistics(self, target_id: str) -> Dict:
        """Get statistics for a target."""
        db = await self._get_connection()
        # Get basic stats from target
        async with db.execute("""
            SELECT total_checks, failed_checks, status, last_check, last_status_change
            FROM targets WHERE id = ?
        """, (target_id,)) as cursor:
            row = await cursor.fetchone()
            if not row:
                return {}

            total_checks, failed_checks, status, last_check, last_status_change = row
            uptime = 0.0
            if total_checks > 0:
                uptime = ((total_checks - failed_checks) / total_checks) * 100

            # Get average response time from recent history
            async with db.execute("""
                SELECT AVG(response_time)
                FROM check_history
                WHERE target_id = ? AND response_time IS NOT NULL
                AND timestamp > datetime('now', '-24 hours')
            """, (target_id,)) as cursor2:
                avg_row = await cursor2.fetchone()
                avg_response_time = avg_row[0] if avg_row[0] else 0.0

            return {
                'total_checks': total_checks,
                'failed_checks': failed_checks,
                'uptime_percentage': round(uptime, 2),
                'status': status,
                'last_check': last_check,
                'last_status_change': last_status_change,
                'avg_response_time_24h': round(avg_response_time, 3) if avg_response_time else None
            }

    async def cleanup_old_alerts(self, retention_days: int = 90) -> int:
        """
        Delete alert log entries older than the specified retention period.

        Args:
            retention_days: Number of days to retain alerts (default: 90)

        Returns:
            Number of records deleted
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=retention_days)
        cutoff_iso = cutoff_date.isoformat()

        db = await self._get_connection()
        cursor = await db.execute(
            "DELETE FROM alert_log WHERE timestamp < ?",
            (cutoff_iso,)
        )
        await db.commit()
        deleted = cursor.rowcount

        if deleted > 0:
            # Also cleanup old check history
            cursor = await db.execute(
                "DELETE FROM check_history WHERE timestamp < ?",
                (cutoff_iso,)
            )
            await db.commit()
            history_deleted = cursor.rowcount
            return deleted + history_deleted

        return deleted

    async def get_database_stats(self) -> Dict:
        """Get database statistics for monitoring."""
        db = await self._get_connection()
        # Get table row counts
        async with db.execute("SELECT COUNT(*) FROM targets") as cursor:
            targets_count = (await cursor.fetchone())[0]

        async with db.execute("SELECT COUNT(*) FROM alert_log") as cursor:
            alerts_count = (await cursor.fetchone())[0]

        async with db.execute("SELECT COUNT(*) FROM check_history") as cursor:
            history_count = (await cursor.fetchone())[0]

        # Get oldest and newest alerts
        async with db.execute(
            "SELECT MIN(timestamp), MAX(timestamp) FROM alert_log"
        ) as cursor:
            result = await cursor.fetchone()
            oldest_alert, newest_alert = result if result else (None, None)

        # Get database file size
        db_size_bytes = Path(self.db_path).stat().st_size
        db_size_mb = round(db_size_bytes / (1024 * 1024), 2)

        return {
            'targets': targets_count,
            'alert_logs': alerts_count,
            'check_history': history_count,
            'oldest_alert': oldest_alert,
            'newest_alert': newest_alert,
            'database_size_mb': db_size_mb
        }

    # ===== Settings CRUD =====

    async def save_settings(self, category: str, settings: dict):
        """
        Save settings for a category.
        Stores each setting as a separate row for easier querying.
        Automatically encrypts sensitive fields (passwords, API keys).

        Args:
            category: Settings category (e.g., 'smtp', 'backup')
            settings: Dictionary of settings to save

        Raises:
            ValueError: If category is not in the whitelist
        """
        # Validate category
        if category not in VALID_CATEGORIES:
            raise ValueError(f"Invalid settings category: {category}. Valid categories: {', '.join(VALID_CATEGORIES)}")

        db = await self._get_connection()
        encryption = get_secure_settings()

        try:
            for key, value in settings.items():
                full_key = f"{category}.{key}"

                # Convert value to JSON string if it's a list or dict
                if isinstance(value, (list, dict)):
                    value_str = json.dumps(value)
                else:
                    value_str = str(value)

                # Encrypt sensitive fields
                if full_key in SENSITIVE_FIELDS and value_str:
                    # Only encrypt if not already encrypted
                    if not encryption.is_encrypted(value_str):
                        value_str = encryption.encrypt(value_str)
                        logger.debug(f"Encrypted sensitive field: {full_key}")

                await db.execute("""
                    INSERT INTO settings (key, value, category, updated_at)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = excluded.updated_at
                """, (full_key, value_str, category, utc_now()))

            await db.commit()
            logger.info(f"Settings saved for category: {category}")

        except Exception as e:
            logger.error(f"Failed to save settings for {category}: {e}")
            raise

    async def get_settings_by_category(self, category: str) -> dict:
        """
        Get all settings for a category.
        Automatically decrypts sensitive fields (passwords, API keys).

        Args:
            category: Settings category (e.g., 'smtp', 'backup')

        Returns:
            Dictionary of settings with keys (without category prefix)

        Raises:
            ValueError: If category is not in the whitelist
        """
        # Validate category
        if category not in VALID_CATEGORIES:
            raise ValueError(f"Invalid settings category: {category}. Valid categories: {', '.join(VALID_CATEGORIES)}")

        db = await self._get_connection()
        encryption = get_secure_settings()
        settings = {}

        try:
            async with db.execute(
                "SELECT key, value FROM settings WHERE category = ?",
                (category,)
            ) as cursor:
                async for row in cursor:
                    full_key, value_str = row
                    # Remove category prefix from key
                    key = full_key.split('.', 1)[1] if '.' in full_key else full_key

                    # Decrypt sensitive fields
                    if full_key in SENSITIVE_FIELDS and value_str:
                        try:
                            if encryption.is_encrypted(value_str):
                                value_str = encryption.decrypt(value_str)
                                logger.debug(f"Decrypted sensitive field: {full_key}")
                        except Exception as e:
                            logger.warning(f"Failed to decrypt {full_key}: {e}")
                            # Continue with encrypted value rather than failing

                    # Try to parse JSON for lists/dicts
                    try:
                        value = json.loads(value_str)
                    except (json.JSONDecodeError, ValueError):
                        # Not JSON, check for boolean strings
                        if value_str.lower() in ('true', 'false'):
                            value = value_str.lower() == 'true'
                        # Check for numeric strings
                        elif value_str.isdigit():
                            value = int(value_str)
                        else:
                            value = value_str

                    settings[key] = value

            return settings

        except Exception as e:
            logger.error(f"Failed to get settings for {category}: {e}")
            return {}

    async def get_setting(self, key: str) -> Optional[str]:
        """
        Get a specific setting value.

        Args:
            key: Full setting key (e.g., 'smtp.host')

        Returns:
            Setting value as string, or None if not found
        """
        db = await self._get_connection()

        try:
            async with db.execute(
                "SELECT value FROM settings WHERE key = ?",
                (key,)
            ) as cursor:
                row = await cursor.fetchone()
                return row[0] if row else None

        except Exception as e:
            logger.error(f"Failed to get setting {key}: {e}")
            return None

    async def set_setting(self, key: str, value: str, category: str):
        """
        Set a specific setting value.

        Args:
            key: Full setting key (e.g., 'smtp.host')
            value: Setting value
            category: Settings category
        """
        db = await self._get_connection()

        try:
            await db.execute("""
                INSERT INTO settings (key, value, category, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value = excluded.value,
                    updated_at = excluded.updated_at
            """, (key, value, category, utc_now()))

            await db.commit()
            logger.debug(f"Setting updated: {key}")

        except Exception as e:
            logger.error(f"Failed to set setting {key}: {e}")
            raise

    async def delete_settings_by_category(self, category: str):
        """
        Delete all settings for a category.

        Raises:
            ValueError: If category is not in the whitelist
        """
        # Validate category
        if category not in VALID_CATEGORIES:
            raise ValueError(f"Invalid settings category: {category}. Valid categories: {', '.join(VALID_CATEGORIES)}")

        db = await self._get_connection()

        try:
            await db.execute(
                "DELETE FROM settings WHERE category = ?",
                (category,)
            )
            await db.commit()
            logger.info(f"Settings deleted for category: {category}")

        except Exception as e:
            logger.error(f"Failed to delete settings for {category}: {e}")
            raise

    # ===== Public Token Management =====

    async def create_public_token(self, token: str, name: Optional[str] = None,
                                 view_mode: str = 'both') -> Dict:
        """
        Create a new public token for status page sharing.

        Args:
            token: Cryptographically random token string
            name: Optional friendly name for the token
            view_mode: View mode ('both', 'timeline', 'cards') - default 'both'

        Returns:
            Dictionary with token details
        """
        db = await self._get_connection()

        try:
            now = utc_now()
            await db.execute("""
                INSERT INTO public_tokens (token, name, view_mode, created_at, enabled)
                VALUES (?, ?, ?, ?, 1)
            """, (token, name, view_mode, now))

            await db.commit()
            logger.info(f"Public token created: {name or token[:8]}... (view_mode: {view_mode})")

            return {
                'token': token,
                'name': name,
                'view_mode': view_mode,
                'created_at': now,
                'enabled': True,
                'access_count': 0
            }

        except Exception as e:
            logger.error(f"Failed to create public token: {e}")
            raise

    async def get_public_token(self, token: str) -> Optional[Dict]:
        """
        Get public token details and validate it exists and is enabled.

        Args:
            token: Token string to look up

        Returns:
            Token dictionary if valid and enabled, None otherwise
        """
        db = await self._get_connection()
        db.row_factory = aiosqlite.Row

        try:
            async with db.execute(
                "SELECT * FROM public_tokens WHERE token = ? AND enabled = 1",
                (token,)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

        except Exception as e:
            logger.error(f"Failed to get public token: {e}")
            return None

    async def get_all_public_tokens(self) -> List[Dict]:
        """
        Get all public tokens (for admin display).

        Returns:
            List of token dictionaries with metadata
        """
        db = await self._get_connection()
        db.row_factory = aiosqlite.Row

        try:
            async with db.execute(
                "SELECT * FROM public_tokens ORDER BY created_at DESC"
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"Failed to get all public tokens: {e}")
            return []

    async def update_token_access(self, token: str):
        """
        Update token access tracking (last accessed time and count).

        Args:
            token: Token that was accessed
        """
        db = await self._get_connection()

        try:
            now = utc_now()
            await db.execute("""
                UPDATE public_tokens
                SET last_accessed = ?,
                    access_count = access_count + 1
                WHERE token = ?
            """, (now, token))

            await db.commit()

        except Exception as e:
            logger.error(f"Failed to update token access: {e}")

    async def toggle_token_enabled(self, token: str, enabled: bool) -> bool:
        """
        Enable or disable a public token.

        Args:
            token: Token to toggle
            enabled: True to enable, False to disable

        Returns:
            True if successful
        """
        db = await self._get_connection()

        try:
            await db.execute("""
                UPDATE public_tokens
                SET enabled = ?
                WHERE token = ?
            """, (1 if enabled else 0, token))

            await db.commit()
            logger.info(f"Token {token[:8]}... {'enabled' if enabled else 'disabled'}")
            return True

        except Exception as e:
            logger.error(f"Failed to toggle token: {e}")
            return False

    async def update_token_details(self, token: str, name: str = None, view_mode: str = None) -> bool:
        """
        Update token name and/or view mode.

        Args:
            token: Token to update
            name: New name (optional)
            view_mode: New view mode (optional)

        Returns:
            True if successful
        """
        db = await self._get_connection()

        try:
            updates = []
            params = []

            if name is not None:
                updates.append("name = ?")
                params.append(name)

            if view_mode is not None:
                updates.append("view_mode = ?")
                params.append(view_mode)

            if not updates:
                return True  # Nothing to update

            params.append(token)
            query = f"UPDATE public_tokens SET {', '.join(updates)} WHERE token = ?"

            await db.execute(query, tuple(params))
            await db.commit()
            logger.info(f"Token details updated: {token[:8]}...")
            return True

        except Exception as e:
            logger.error(f"Failed to update token details: {e}")
            return False

    async def delete_public_token(self, token: str) -> bool:
        """
        Delete a public token (revoke access).

        Args:
            token: Token to delete

        Returns:
            True if successful
        """
        db = await self._get_connection()

        try:
            await db.execute("DELETE FROM public_tokens WHERE token = ?", (token,))
            await db.commit()
            logger.info(f"Public token deleted: {token[:8]}...")
            return True

        except Exception as e:
            logger.error(f"Failed to delete public token: {e}")
            return False

    async def get_public_targets(self) -> List[Dict]:
        """
        Get all targets that are marked as publicly visible.
        Returns only safe fields for public display.

        Returns:
            List of public target dictionaries (filtered for safety)
        """
        db = await self._get_connection()
        db.row_factory = aiosqlite.Row

        try:
            async with db.execute("""
                SELECT id, name, public_name, status, last_status_change,
                       total_checks, failed_checks
                FROM targets
                WHERE public_visible = 1 AND enabled = 1
                ORDER BY name
            """) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

        except Exception as e:
            logger.error(f"Failed to get public targets: {e}")
            return []

    async def update_target_visibility(self, target_id: str, public_visible: bool,
                                      public_name: Optional[str] = None) -> bool:
        """
        Update target's public visibility and optional public display name.

        Args:
            target_id: Target ID to update
            public_visible: True to show on public page, False to hide
            public_name: Optional custom name for public display

        Returns:
            True if successful
        """
        db = await self._get_connection()

        try:
            await db.execute("""
                UPDATE targets
                SET public_visible = ?,
                    public_name = ?
                WHERE id = ?
            """, (1 if public_visible else 0, public_name, target_id))

            await db.commit()
            logger.info(f"Updated visibility for target {target_id}: visible={public_visible}")
            return True

        except Exception as e:
            logger.error(f"Failed to update target visibility: {e}")
            return False


# Global database instance
db = Database()
