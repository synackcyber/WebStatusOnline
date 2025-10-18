"""
Application restart utilities.
Provides a simple mechanism to trigger application restart after critical operations.
"""
import os
import sys
import asyncio
import signal
import logging

logger = logging.getLogger(__name__)


async def schedule_restart(delay_seconds: int = 3):
    """
    Schedule application restart after a delay.

    This is used for operations that require a clean restart (e.g., database restore).
    The application will exit cleanly, allowing process supervisors (systemd, docker, PM2)
    to automatically restart it.

    Args:
        delay_seconds: Seconds to wait before triggering restart
    """
    logger.warning(f"⚠️  Application restart scheduled in {delay_seconds} seconds...")

    async def do_restart():
        await asyncio.sleep(delay_seconds)
        logger.warning("🔄 Initiating graceful restart...")

        # Send SIGTERM to self (graceful shutdown)
        os.kill(os.getpid(), signal.SIGTERM)

    # Run restart in background task
    asyncio.create_task(do_restart())


def get_restart_instructions() -> dict:
    """
    Return restart instructions based on deployment type.

    Returns:
        Dictionary with restart instructions for different environments
    """
    return {
        "systemd": "sudo systemctl restart webstatus",
        "docker": "docker restart webstatus",
        "docker_compose": "docker-compose restart",
        "pm2": "pm2 restart webstatus",
        "manual": "Stop the process and run: python3 main.py"
    }
