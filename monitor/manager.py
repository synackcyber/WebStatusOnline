"""
Monitor Manager module.
Orchestrates all monitoring activities.
"""
import asyncio
from typing import Dict, Set
from datetime import datetime
import logging

from database.db import db
from monitor.checker import check_target
from monitor.models import AlertEvent

logger = logging.getLogger(__name__)


class MonitorManager:
    """Manages monitoring tasks for all targets."""

    def __init__(self, config: Dict):
        self.config = config
        self.tasks: Dict[str, asyncio.Task] = {}
        self.active_alerts: Set[str] = set()  # Target IDs currently alerting
        self.last_alert_time: Dict[str, datetime] = {}  # Last alert time per target
        self.running = False
        self.alert_callbacks = []  # Callbacks to trigger on alert events
        self._reload_lock = asyncio.Lock()  # Prevent concurrent reload operations

    def register_alert_callback(self, callback):
        """Register a callback function to be called on alert events."""
        self.alert_callbacks.append(callback)

    async def trigger_alert_callbacks(self, event: AlertEvent):
        """Trigger all registered alert callbacks."""
        for callback in self.alert_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
            except Exception as e:
                logger.error(f"Error in alert callback: {e}")

    async def start(self):
        """Start monitoring all enabled targets."""
        if self.running:
            logger.warning("Monitor manager already running")
            return

        self.running = True
        logger.info("Starting monitor manager...")

        # Get all enabled targets
        targets = await db.get_enabled_targets()
        logger.info(f"Found {len(targets)} enabled targets")

        # Restore alert state from database (for reliability across restarts)
        await self._restore_alert_state(targets)

        # Start monitoring task for each target
        for target in targets:
            await self.start_target_monitoring(target)

    async def stop(self):
        """Stop all monitoring tasks."""
        if not self.running:
            return

        self.running = False
        logger.info("Stopping monitor manager...")

        # Cancel all tasks
        for target_id, task in self.tasks.items():
            task.cancel()

        # Wait for all tasks to complete
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)

        self.tasks.clear()
        logger.info("Monitor manager stopped")

    async def _restore_alert_state(self, targets: list):
        """
        Restore alert state from database on startup.

        This ensures that targets which were in alert state before a server restart
        are correctly tracked, allowing recovery alerts to be sent when they come back up.

        Args:
            targets: List of enabled targets from database
        """
        restored_count = 0

        for target in targets:
            target_id = target['id']
            target_name = target['name']
            current_failures = target.get('current_failures', 0)
            failure_threshold = target.get('failure_threshold', 3)
            acknowledged = target.get('acknowledged', False)

            # Only restore alert state if:
            # 1. Target has failures >= threshold (was in alert state)
            # 2. Target is NOT acknowledged (acknowledged targets don't alert)
            if current_failures >= failure_threshold and not acknowledged:
                self.active_alerts.add(target_id)
                restored_count += 1
                logger.info(f"🔄 Restored alert state for {target_name} ({current_failures}/{failure_threshold} failures)")
            elif current_failures >= failure_threshold and acknowledged:
                logger.debug(f"⏭️  Skipping alert restore for {target_name} (acknowledged)")

        if restored_count > 0:
            logger.info(f"✅ Restored alert state for {restored_count} target(s)")
        else:
            logger.info("✅ No active alerts to restore (all targets healthy)")

    def _task_done_callback(self, task: asyncio.Task, target_id: str, target_name: str):
        """Callback when a monitoring task completes or crashes."""
        try:
            # This will raise the exception if the task failed
            task.result()
        except asyncio.CancelledError:
            # Expected when we cancel a task
            logger.debug(f"Task cancelled for {target_name}")
        except Exception as e:
            # Unexpected exception - this is a bug!
            logger.error(f"⚠️ Monitoring task crashed for {target_name} (ID: {target_id}): {e}", exc_info=True)
            # Remove from active tasks since it's dead
            if target_id in self.tasks:
                del self.tasks[target_id]

    async def start_target_monitoring(self, target: Dict):
        """Start monitoring a specific target."""
        target_id = target['id']

        # Cancel existing task if any
        if target_id in self.tasks:
            self.tasks[target_id].cancel()
            try:
                await self.tasks[target_id]
            except asyncio.CancelledError:
                pass  # Expected when cancelling
            del self.tasks[target_id]

        # Create new monitoring task
        task = asyncio.create_task(self._monitor_target(target))

        # Add done callback to log exceptions
        task.add_done_callback(
            lambda t: self._task_done_callback(t, target_id, target['name'])
        )

        self.tasks[target_id] = task

        logger.info(f"Started monitoring: {target['name']} ({target['type']}://{target['address']})")

    async def stop_target_monitoring(self, target_id: str):
        """Stop monitoring a specific target."""
        if target_id in self.tasks:
            self.tasks[target_id].cancel()
            try:
                # Wait for task to actually stop
                await self.tasks[target_id]
            except asyncio.CancelledError:
                pass  # Expected when cancelling
            del self.tasks[target_id]
            logger.info(f"Stopped monitoring target: {target_id}")

    async def _monitor_target(self, target: Dict):
        """
        Monitor a single target continuously.
        This runs as a long-lived task.

        Note: Refreshes target data from DB every 10 checks to pick up configuration changes.
        """
        target_id = target['id']
        target_name = target['name']
        check_count = 0
        refresh_interval = 10  # Refresh target data every 10 checks

        logger.info(f"Monitoring loop started for {target_name}")

        while self.running:
            try:
                # Refresh target data periodically to pick up configuration changes
                if check_count % refresh_interval == 0:
                    fresh_target = await db.get_target(target_id)
                    if fresh_target:
                        target = fresh_target
                        logger.debug(f"Refreshed config for {target_name}")
                    else:
                        logger.warning(f"Target {target_id} no longer exists, stopping monitoring")
                        break

                check_count += 1

                # Get current check interval (may have changed)
                check_interval = target.get('check_interval', self.config.get('check_interval', 60))

                # Perform the check
                await self._check_target_once(target)

                # Wait for next check
                await asyncio.sleep(check_interval)

            except asyncio.CancelledError:
                logger.info(f"Monitoring cancelled for {target_name}")
                break
            except Exception as e:
                logger.error(f"Error monitoring {target_name}: {e}")
                # Use current check_interval or fallback
                check_interval = target.get('check_interval', self.config.get('check_interval', 60))
                await asyncio.sleep(check_interval)

    async def _check_target_once(self, target: Dict):
        """Perform a single check on a target."""
        target_id = target['id']
        target_name = target['name']
        target_type = target['type']
        address = target['address']

        # Get timeout from config
        if target_type == 'ping':
            timeout = self.config.get('ping_timeout', 3)
        else:
            timeout = self.config.get('http_timeout', 10)

        # Perform check
        logger.debug(f"🔍 Checking {target_name}...")

        # Pass ping-specific config if target is ping type
        ping_config = None
        if target_type == 'ping':
            ping_config = {
                'packet_count': self.config.get('ping_packet_count', 3),
                'min_success': self.config.get('ping_min_success', 1)
            }

        # Wrap check_target in timeout to prevent hanging
        # Add 5 seconds buffer on top of the check timeout
        overall_timeout = timeout + 5
        try:
            success, response_time, error_message, extra_data = await asyncio.wait_for(
                check_target(target_type, address, timeout, None, ping_config),
                timeout=overall_timeout
            )
        except asyncio.TimeoutError:
            # Overall timeout exceeded - this shouldn't happen if check_target respects timeouts
            logger.error(f"Check timeout exceeded for {target_name} (>{overall_timeout}s)")
            success = False
            response_time = overall_timeout
            error_message = f"Check timeout exceeded ({overall_timeout}s)"
            extra_data = None

        # Update failure count
        current_failures = target.get('current_failures', 0)

        if success:
            # Target is up
            status = 'up'
            previous_failures = current_failures
            current_failures = 0

            # Log success
            logger.info(f"✅ {target_name} - UP (response: {response_time:.3f}s)")

            # Update database FIRST before triggering callbacks
            await db.update_target_status(target_id, status, current_failures, response_time)
            await db.add_check_history(target_id, status, response_time, error_message)

            # Update local target data
            target['status'] = status
            target['current_failures'] = current_failures

            # Check if we need to clear an alert (after DB update to prevent race condition)
            # Only trigger recovery if target was actively alerting (tracked in self.active_alerts)
            # Alert state is restored from DB on startup, so this works correctly across restarts
            if previous_failures >= target['failure_threshold'] and target_id in self.active_alerts:
                await self._handle_recovery(target, previous_failures)

        else:
            # Target is down
            status = 'down'
            current_failures += 1
            logger.warning(f"❌ {target_name} - DOWN ({current_failures}/{target['failure_threshold']}) - {error_message}")

            # Update database FIRST before triggering callbacks
            await db.update_target_status(target_id, status, current_failures, response_time)
            await db.add_check_history(target_id, status, response_time, error_message)

            # Update local target data
            target['status'] = status
            target['current_failures'] = current_failures

            # Check if we've reached the threshold (after DB update to prevent race condition)
            if current_failures >= target['failure_threshold']:
                if target_id not in self.active_alerts:
                    # First time reaching threshold
                    await self._handle_threshold_reached(target, current_failures, error_message)
                else:
                    # Check if we need to repeat the alert
                    await self._handle_alert_repeat(target, current_failures)

    async def _handle_threshold_reached(self, target: Dict, failures: int, error_message: str):
        """Handle when a target reaches its failure threshold."""
        target_id = target['id']
        target_name = target['name']

        self.active_alerts.add(target_id)
        self.last_alert_time[target_id] = datetime.utcnow()

        logger.error(f"🚨 ALERT: {target_name} has reached failure threshold ({failures}/{target['failure_threshold']})")

        # Create alert event
        event = AlertEvent(
            target_id=target_id,
            target_name=target_name,
            event_type='threshold_reached',
            message=f"{target_name} is DOWN - {error_message}",
            current_failures=failures,
            failure_threshold=target['failure_threshold']
        )

        # Log to database
        await db.add_alert_log(
            target_id,
            'threshold_reached',
            f"Target down after {failures} consecutive failures: {error_message}"
        )

        # Trigger alert callbacks
        await self.trigger_alert_callbacks(event)

    async def _handle_recovery(self, target: Dict, previous_failures: int):
        """Handle when a target recovers from failure."""
        target_id = target['id']
        target_name = target['name']

        self.active_alerts.discard(target_id)
        if target_id in self.last_alert_time:
            del self.last_alert_time[target_id]

        logger.info(f"✅ RECOVERY: {target_name} has recovered")

        # Create recovery event
        event = AlertEvent(
            target_id=target_id,
            target_name=target_name,
            event_type='recovered',
            message=f"{target_name} has recovered",
            current_failures=0,
            failure_threshold=target['failure_threshold']
        )

        # Log to database
        await db.add_alert_log(
            target_id,
            'recovered',
            f"Target recovered after {previous_failures} failures"
        )

        # Trigger alert callbacks
        await self.trigger_alert_callbacks(event)

    async def _handle_alert_repeat(self, target: Dict, failures: int):
        """Handle repeating alerts for targets that remain down."""
        target_id = target['id']
        target_name = target['name']

        # Check if we should repeat the alert
        alert_repeat_interval = self.config.get('alert_repeat_interval', 300)  # Default 5 minutes
        last_alert = self.last_alert_time.get(target_id)

        if last_alert:
            time_since_alert = (datetime.utcnow() - last_alert).total_seconds()
            if time_since_alert >= alert_repeat_interval:
                logger.warning(f"🔔 ALERT REPEAT: {target_name} still down")

                self.last_alert_time[target_id] = datetime.utcnow()

                # Create repeat alert event
                event = AlertEvent(
                    target_id=target_id,
                    target_name=target_name,
                    event_type='alert_repeat',
                    message=f"{target_name} is still DOWN",
                    current_failures=failures,
                    failure_threshold=target['failure_threshold']
                )

                # Log to database
                await db.add_alert_log(
                    target_id,
                    'alert_repeat',
                    f"Target still down after {failures} checks"
                )

                # Trigger alert callbacks
                await self.trigger_alert_callbacks(event)

    async def reload_targets(self):
        """Reload all targets from database and restart monitoring."""
        # Use lock to prevent concurrent reloads
        async with self._reload_lock:
            logger.info("Reloading targets...")

            # Get current enabled targets
            enabled_targets = await db.get_enabled_targets()
            enabled_ids = {t['id'] for t in enabled_targets}

            # Stop monitoring for targets that are no longer enabled
            current_ids = set(self.tasks.keys())
            to_stop = current_ids - enabled_ids

            for target_id in to_stop:
                await self.stop_target_monitoring(target_id)

            # Start or restart monitoring for enabled targets
            for target in enabled_targets:
                await self.start_target_monitoring(target)

            logger.info(f"Reload complete: {len(enabled_targets)} targets monitored")

    async def check_target_now(self, target_id: str):
        """Manually trigger a check for a specific target."""
        target = await db.get_target(target_id)
        if not target:
            raise ValueError(f"Target {target_id} not found")

        await self._check_target_once(target)

    def get_active_alerts(self) -> Set[str]:
        """Get the set of target IDs with active alerts."""
        return self.active_alerts.copy()
