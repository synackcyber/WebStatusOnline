"""
Universal webhook alert module.
Posts JSON payloads to configured webhook URLs.
"""
import httpx
import logging
from typing import Dict, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class WebhookNotifier:
    """Sends alerts to webhook endpoints."""

    def __init__(self, webhook_url: Optional[str] = None, enabled: bool = False):
        self.webhook_url = webhook_url
        self.enabled = enabled and bool(webhook_url)

        if self.enabled:
            logger.info(f"Webhook notifier enabled: {webhook_url}")
        else:
            logger.info("Webhook notifier disabled")

    def update_config(self, webhook_url: Optional[str], enabled: bool):
        """Update webhook configuration."""
        self.webhook_url = webhook_url
        self.enabled = enabled and bool(webhook_url)

        if self.enabled:
            logger.info(f"Webhook notifier updated: {webhook_url}")
        else:
            logger.info("Webhook notifier disabled")

    async def send(self, payload: Dict) -> bool:
        """
        Send a webhook notification.

        Args:
            payload: Dictionary to send as JSON

        Returns:
            True if successful, False otherwise
        """
        if not self.enabled or not self.webhook_url:
            logger.debug("Webhook not enabled, skipping")
            return False

        try:
            logger.info(f"📤 Sending webhook to {self.webhook_url}")

            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    self.webhook_url,
                    json=payload,
                    headers={'Content-Type': 'application/json'}
                )

                if 200 <= response.status_code < 300:
                    logger.info(f"✅ Webhook sent successfully (status: {response.status_code})")
                    return True
                else:
                    logger.error(f"❌ Webhook failed with status {response.status_code}: {response.text}")
                    return False

        except httpx.TimeoutException:
            logger.error(f"❌ Webhook timeout: {self.webhook_url}")
            return False
        except Exception as e:
            logger.error(f"❌ Webhook error: {e}")
            return False

    async def send_alert(self, event_type: str, target_name: str, target_id: str,
                        message: str, failures: int = 0, threshold: int = 0) -> bool:
        """
        Send an alert webhook with standardized payload.

        Args:
            event_type: Type of event (threshold_reached, recovered, alert_repeat)
            target_name: Name of the target
            target_id: ID of the target
            message: Alert message
            failures: Current failure count
            threshold: Failure threshold

        Returns:
            True if successful, False otherwise
        """
        payload = {
            'event_type': event_type,
            'target': {
                'id': target_id,
                'name': target_name
            },
            'message': message,
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'failures': failures,
            'threshold': threshold
        }

        return await self.send(payload)

    async def send_threshold_reached(self, target_name: str, target_id: str,
                                     failures: int, threshold: int, error: str = "") -> bool:
        """Send alert when failure threshold is reached."""
        message = f"🚨 ALERT: {target_name} is DOWN"
        if error:
            message += f" - {error}"

        logger.warning(message)

        return await self.send_alert(
            event_type='threshold_reached',
            target_name=target_name,
            target_id=target_id,
            message=message,
            failures=failures,
            threshold=threshold
        )

    async def send_recovery(self, target_name: str, target_id: str,
                           previous_failures: int = 0) -> bool:
        """Send notification when target recovers."""
        message = f"✅ RECOVERY: {target_name} is back UP"

        logger.info(message)

        return await self.send_alert(
            event_type='recovered',
            target_name=target_name,
            target_id=target_id,
            message=message,
            failures=0,
            threshold=0
        )

    async def send_repeat_alert(self, target_name: str, target_id: str,
                               failures: int, threshold: int) -> bool:
        """Send repeat alert for target that remains down."""
        message = f"🔔 {target_name} is still DOWN"

        logger.warning(message)

        return await self.send_alert(
            event_type='alert_repeat',
            target_name=target_name,
            target_id=target_id,
            message=message,
            failures=failures,
            threshold=threshold
        )

    async def test_webhook(self) -> bool:
        """Test webhook with a test payload."""
        if not self.enabled or not self.webhook_url:
            logger.warning("Cannot test webhook - not enabled or URL not set")
            return False

        logger.info("Testing webhook...")

        test_payload = {
            'event_type': 'test',
            'message': 'This is a test notification from WebStatus',
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

        return await self.send(test_payload)
