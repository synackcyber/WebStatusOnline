"""
Alert State Manager for centralized alert state tracking.

Provides a single source of truth for current alert state, designed to be
lightweight and scalable. Tracks only ONE active alert at a time (the most urgent)
regardless of how many targets are down.

Memory usage: O(1) - only stores current alert and last recovery
CPU usage: O(1) - simple datetime arithmetic, no loops
Scales to: unlimited targets (only tracks the ONE currently alerting)
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class AlertStateManager:
    """
    Lightweight in-memory alert state manager.

    Designed for backend-driven polling approach where clients query
    current state rather than receiving WebSocket event streams.
    """

    def __init__(self):
        # Only ONE active alert at a time (most urgent target)
        self.current_alert: Optional[Dict[str, Any]] = None

        # Last recovery event (expires after 30 seconds)
        self.last_recovery: Optional[Dict[str, Any]] = None

        # Webhook state tracking - tracks which targets have been notified
        # Set of target_ids that have received down webhooks
        self.webhook_notified: set = set()

        # Email state tracking - tracks which targets have been emailed
        # Set of target_ids that have received down emails
        self.email_notified: set = set()

        # Lock for thread-safe operations
        self._lock = asyncio.Lock()

        # Cleanup task for recovery expiration
        self._cleanup_task: Optional[asyncio.Task] = None

    def get_state(self) -> Dict[str, Any]:
        """
        Get current alert state.

        O(1) operation - just returns current state with calculated next play time.
        No database queries, no loops, no complex logic.

        Returns:
            dict: Current alert state with structure:
                {
                    "is_alerting": bool,
                    "current_alert": {
                        "target_id": str,
                        "target_name": str,
                        "audio_file": str,
                        "event_type": "down",
                        "interval_seconds": int,
                        "started_at": ISO timestamp,
                        "next_play_time": ISO timestamp (calculated on-the-fly)
                    } | None,
                    "last_recovery": {
                        "target_id": str,
                        "target_name": str,
                        "audio_file": str,
                        "event_type": "up",
                        "timestamp": ISO timestamp
                    } | None
                }
        """
        if not self.current_alert:
            return {
                "is_alerting": False,
                "current_alert": None,
                "last_recovery": self.last_recovery
            }

        # Calculate next play time on-the-fly (no need to store it)
        now = datetime.utcnow()
        started_at = self.current_alert["started_at"]
        interval = self.current_alert["interval_seconds"]

        # How many complete intervals have passed since alert started?
        elapsed = (now - started_at).total_seconds()
        intervals_passed = int(elapsed / interval)

        # When should the NEXT interval play?
        # Example: started at 10:30:00, interval 5s, now 10:30:07
        # elapsed = 7s, intervals_passed = 1, next = 10:30:00 + (2 * 5s) = 10:30:10
        next_play_time = started_at + timedelta(seconds=(intervals_passed + 1) * interval)

        return {
            "is_alerting": True,
            "current_alert": {
                **self.current_alert,
                "next_play_time": next_play_time.isoformat() + "Z"
            },
            "last_recovery": self.last_recovery
        }

    async def set_alert(
        self,
        target_id: str,
        target_name: str,
        audio_file: str,
        interval_seconds: int
    ):
        """
        Set the current active alert.

        O(1) operation - just updates a single dict.

        Args:
            target_id: ID of the target being alerted
            target_name: Display name of the target
            audio_file: Audio file to play (e.g., "system_down.mp3")
            interval_seconds: Seconds between alert repetitions
        """
        async with self._lock:
            # Check if this is the same target we're already alerting for
            if self.current_alert and self.current_alert.get("target_id") == target_id:
                # Same target - don't reset start time, just update details if needed
                logger.debug(f"Alert continues for {target_name} (already alerting)")
                return

            # Different target or first alert
            self.current_alert = {
                "target_id": target_id,
                "target_name": target_name,
                "audio_file": audio_file,
                "event_type": "down",
                "interval_seconds": interval_seconds,
                "started_at": datetime.utcnow()
            }

            # Clear any stale recovery state when a new down alert starts
            # This prevents clients from seeing both down and recovery alerts simultaneously
            if self.last_recovery:
                logger.debug(f"Clearing stale recovery state (new alert for {target_name})")
                self.last_recovery = None

            logger.info(
                f"🔊 Alert state set: {target_name} (interval: {interval_seconds}s, audio: {audio_file})"
            )

    async def clear_alert(self, target_id: Optional[str] = None):
        """
        Clear the current active alert.

        O(1) operation - just sets to None.

        Args:
            target_id: Optional target ID to clear. If provided, only clears if it matches
                      current alert. If None, clears unconditionally.
        """
        async with self._lock:
            # If target_id specified, only clear if it matches
            if target_id is not None:
                if self.current_alert and self.current_alert.get("target_id") == target_id:
                    logger.info(f"🔇 Alert cleared for target: {target_id}")
                    self.current_alert = None
                else:
                    logger.debug(f"Alert clear skipped - target {target_id} not currently alerting")
            else:
                # Clear unconditionally
                if self.current_alert:
                    logger.info("🔇 All alerts cleared (system nominal)")
                self.current_alert = None

    async def set_recovery(
        self,
        target_id: str,
        target_name: str,
        audio_file: str
    ):
        """
        Record a recovery event.

        Recovery events are shown to clients for 30 seconds, then expire.
        This prevents recovery sounds from playing repeatedly.

        O(1) operation - just updates a dict and schedules cleanup.

        Args:
            target_id: ID of the recovered target
            target_name: Display name of the target
            audio_file: Audio file to play (e.g., "system_up.mp3")
        """
        async with self._lock:
            self.last_recovery = {
                "target_id": target_id,
                "target_name": target_name,
                "audio_file": audio_file,
                "event_type": "up",
                "timestamp": datetime.utcnow().isoformat() + "Z"
            }

            logger.info(f"✅ Recovery state set: {target_name} (audio: {audio_file})")

            # Cancel existing cleanup task if any
            if self._cleanup_task and not self._cleanup_task.done():
                self._cleanup_task.cancel()

            # Schedule cleanup after 30 seconds
            self._cleanup_task = asyncio.create_task(self._cleanup_recovery())

    def should_send_webhook(self, target_id: str) -> bool:
        """
        Check if a webhook should be sent for this target.

        Webhooks are sent once when a target goes down.
        They are NOT sent again until the target recovers and goes down again.

        Args:
            target_id: Target to check

        Returns:
            True if webhook should be sent, False if already notified
        """
        return target_id not in self.webhook_notified

    def mark_webhook_sent(self, target_id: str):
        """
        Mark that a webhook has been sent for this target.

        Args:
            target_id: Target that was notified
        """
        self.webhook_notified.add(target_id)
        logger.debug(f"Webhook marked as sent for target: {target_id}")

    def clear_webhook_state(self, target_id: str):
        """
        Clear webhook state for a target (called on recovery).

        This allows a new webhook to be sent if the target goes down again.

        Args:
            target_id: Target to clear state for
        """
        if target_id in self.webhook_notified:
            self.webhook_notified.remove(target_id)
            logger.debug(f"Webhook state cleared for target: {target_id}")

    def should_send_email(self, target_id: str) -> bool:
        """
        Check if an email should be sent for this target.

        Emails are sent once when a target goes down.
        They are NOT sent again until the target recovers and goes down again.

        Args:
            target_id: Target to check

        Returns:
            True if email should be sent, False if already notified
        """
        return target_id not in self.email_notified

    def mark_email_sent(self, target_id: str):
        """
        Mark that an email has been sent for this target.

        Args:
            target_id: Target that was notified
        """
        self.email_notified.add(target_id)
        logger.debug(f"Email marked as sent for target: {target_id}")

    def clear_email_state(self, target_id: str):
        """
        Clear email state for a target (called on recovery).

        This allows a new email to be sent if the target goes down again.

        Args:
            target_id: Target to clear state for
        """
        if target_id in self.email_notified:
            self.email_notified.remove(target_id)
            logger.debug(f"Email state cleared for target: {target_id}")

    async def _cleanup_recovery(self):
        """
        Internal: Remove recovery event after 30 seconds.

        This prevents the same recovery from being played multiple times
        if a client connects/refreshes within the 30 second window.
        """
        try:
            await asyncio.sleep(30)

            async with self._lock:
                if self.last_recovery:
                    # Double-check age in case another recovery was set
                    timestamp = datetime.fromisoformat(
                        self.last_recovery["timestamp"].rstrip("Z")
                    )
                    age = (datetime.utcnow() - timestamp).total_seconds()

                    if age >= 30:
                        logger.debug(f"Recovery event expired: {self.last_recovery['target_name']}")
                        self.last_recovery = None
        except asyncio.CancelledError:
            # Task was cancelled because new recovery was set
            logger.debug("Recovery cleanup cancelled (new recovery set)")
        except Exception as e:
            logger.error(f"Error in recovery cleanup: {e}")


# Global instance
alert_state = AlertStateManager()
