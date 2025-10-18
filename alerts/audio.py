"""
Audio alert module - Browser-only architecture for Docker deployments.
All audio is played through the browser via WebSocket broadcasting.
"""
import asyncio
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class AudioBroadcaster:
    """Broadcasts audio alerts to browser clients via WebSocket."""

    def __init__(self):
        self.loop_task = None
        self.is_looping = False
        self.audio_mode = 'browser'  # Always browser-only
        self.websocket_manager = None
        self.current_alert_audio = None  # Track current alert audio file
        self.loop_count = 0  # Track number of alert loops
        self.max_loops = 100  # Maximum alert loops before auto-stop (safety limit)

        logger.info("AudioBroadcaster initialized - Browser-only mode")

    def set_websocket_manager(self, websocket_manager):
        """Set the WebSocket manager for browser-based audio."""
        self.websocket_manager = websocket_manager
        logger.info("✅ WebSocket manager configured for browser audio")

    async def start_looping(self, sound_type: str = 'down', interval: int = 5, custom_audio: str = None):
        """
        Start looping audio broadcast to browsers.

        Args:
            sound_type: 'down' or 'up'
            interval: Seconds between each broadcast
            custom_audio: Optional custom audio filename to use instead of default
        """
        if self.is_looping:
            logger.warning("Audio already looping")
            return

        self.is_looping = True
        self.loop_count = 0  # Reset loop counter
        audio_desc = custom_audio if custom_audio else f"system_{sound_type}"
        logger.info(f"🔁 Starting audio loop (every {interval}s) - Audio: {audio_desc}")

        self.loop_task = asyncio.create_task(self._loop_audio(sound_type, interval, custom_audio))

    async def stop_looping(self):
        """Stop looping audio broadcast."""
        if not self.is_looping:
            return

        self.is_looping = False

        if self.loop_task:
            self.loop_task.cancel()
            try:
                await self.loop_task
            except asyncio.CancelledError:
                pass
            self.loop_task = None

        logger.info("⏹️  Stopped audio loop")

    async def _loop_audio(self, sound_type: str, interval: int, custom_audio: str = None):
        """Internal method to loop audio broadcast."""
        try:
            while self.is_looping:
                # Safety check: prevent infinite loops
                self.loop_count += 1
                if self.loop_count > self.max_loops:
                    logger.error(
                        f"⚠️  SAFETY LIMIT REACHED: Audio loop stopped after {self.max_loops} iterations. "
                        "This may indicate a bug in the alert logic. Please check system status."
                    )
                    self.is_looping = False
                    break

                # Determine the audio file to broadcast
                audio_filename = custom_audio if custom_audio else f"system_{sound_type}.aiff"

                # Broadcast to browsers
                await self._broadcast_alert(
                    event_type='alert_repeat',
                    target_name='System',
                    target_id='loop',
                    audio_filename=audio_filename
                )

                # Wait for the interval
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            logger.debug("Audio loop cancelled")
        except Exception as e:
            logger.error(f"Error in audio loop: {e}")
            self.is_looping = False

    async def broadcast_recovery(self, target_name: str, target_id: str, audio_file: str = 'system_up.aiff'):
        """
        Broadcast a one-time recovery audio to browsers.

        Args:
            target_name: Name of the recovered target
            target_id: ID of the recovered target
            audio_file: Audio file to play (default: system_up.aiff)
        """
        logger.info(f"🔊 Broadcasting recovery audio for {target_name}: {audio_file}")
        await self._broadcast_alert(
            event_type='recovered',
            target_name=target_name,
            target_id=target_id,
            audio_filename=audio_file,
            message=f"{target_name} has recovered"
        )

    async def broadcast_alert(self, target_name: str, target_id: str, audio_file: str = 'system_down.aiff'):
        """
        Broadcast a one-time alert audio to browsers.

        Args:
            target_name: Name of the target in alert
            target_id: ID of the target
            audio_file: Audio file to play (default: system_down.aiff)
        """
        logger.info(f"🔊 Broadcasting alert audio for {target_name}: {audio_file}")
        await self._broadcast_alert(
            event_type='threshold_reached',
            target_name=target_name,
            target_id=target_id,
            audio_filename=audio_file,
            message=f"{target_name} is down"
        )

    async def _broadcast_alert(self, event_type: str, target_name: str, target_id: str,
                               audio_filename: str, message: str = None):
        """Broadcast alert to browsers via WebSocket."""
        if not self.websocket_manager:
            logger.warning("⚠️  WebSocket manager not configured - cannot broadcast alert")
            logger.warning("    💡 Open the web UI in a browser to hear alerts")
            return False

        try:
            await self.websocket_manager.broadcast_alert(
                event_type=event_type,
                target_name=target_name,
                target_id=target_id,
                audio_filename=audio_filename,
                message=message or f"{target_name} alert"
            )
            logger.info(f"🌐 Broadcasted browser alert: {audio_filename}")
            return True
        except Exception as e:
            logger.error(f"Failed to broadcast alert: {e}")
            return False

    def get_status(self) -> dict:
        """Get audio system status."""
        return {
            'audio_mode': 'browser',
            'available': self.websocket_manager is not None,
            'is_looping': self.is_looping,
            'loop_count': self.loop_count,
            'max_loops': self.max_loops,
            'websocket_connections': self.websocket_manager.get_connection_count() if self.websocket_manager else 0
        }


# Backward compatibility alias
AudioPlayer = AudioBroadcaster
