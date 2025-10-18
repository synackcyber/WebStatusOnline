"""
Backup Scheduler
Schedules automated backups using cron expressions.
"""
import asyncio
import logging
from croniter import croniter
from datetime import datetime

logger = logging.getLogger(__name__)


class BackupScheduler:
    """Schedule automated backups"""

    def __init__(self, backup_manager, schedule: str):
        self.backup_manager = backup_manager
        self.schedule = schedule  # Cron expression: "minute hour day month weekday"
        self.running = False
        self.task = None

    async def start(self):
        """Start the scheduler"""
        if self.running:
            logger.warning("Backup scheduler already running")
            return

        self.running = True
        self.task = asyncio.create_task(self._run())
        logger.info(f"Backup scheduler started: {self.schedule}")

    async def stop(self):
        """Stop the scheduler"""
        self.running = False
        if self.task:
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        logger.info("Backup scheduler stopped")

    def get_next_run_time(self) -> datetime:
        """Get the next scheduled run time"""
        cron = croniter(self.schedule, datetime.now())
        return cron.get_next(datetime)

    async def _run(self):
        """Scheduler loop"""
        cron = croniter(self.schedule, datetime.now())

        while self.running:
            # Calculate next run
            next_run = cron.get_next(datetime)
            wait_seconds = (next_run - datetime.now()).total_seconds()

            if wait_seconds > 0:
                logger.info(f"Next backup scheduled: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")

                try:
                    await asyncio.sleep(wait_seconds)

                    if self.running:
                        logger.info("Running scheduled backup...")
                        result = await asyncio.to_thread(self.backup_manager.create_backup)

                        if result:
                            logger.info(f"Scheduled backup completed: {result['size_human']}")
                        else:
                            logger.error("Scheduled backup failed")

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Backup scheduler error: {e}")
                    # Wait a bit before retrying to avoid rapid failures
                    await asyncio.sleep(60)
