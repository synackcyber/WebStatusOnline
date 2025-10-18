#!/usr/bin/env python3
"""
WebStatus - Network Monitoring System
Main application entry point
"""
import asyncio
import json
import logging
import sys
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Dict, Optional

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import uvicorn

from database.db import db
from monitor.manager import MonitorManager
from monitor.models import AlertEvent
from alerts.audio_library import audio_library
from alerts.webhook import WebhookNotifier
from alerts.smtp import SMTPNotifier
from alerts.state_manager import alert_state
from utils.backup.manager import BackupManager
from utils.backup.scheduler import BackupScheduler
from api import routes
from api import public_routes
from api import auth_routes
from auth.manager import AuthManager
from auth.middleware import AuthMiddleware
from auth.security_headers import SecurityHeadersMiddleware


# Configure logging
import os
log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)
logger.info(f"Logging level set to: {log_level}")

# Audio interval constants (in seconds)
# Simplified 3-tier system for clarity
AUDIO_INTERVAL_URGENT = 30     # Critical infrastructure - every 30 seconds
AUDIO_INTERVAL_NORMAL = 120    # Standard monitoring - every 2 minutes
AUDIO_INTERVAL_SILENT = None   # No audio alerts

AUDIO_INTERVALS = {
    'urgent': AUDIO_INTERVAL_URGENT,
    'normal': AUDIO_INTERVAL_NORMAL,
    'silent': AUDIO_INTERVAL_SILENT
}

# Device type presets - sensible defaults for common device categories
DEVICE_PRESETS = {
    'server': {
        'failure_threshold': 3,       # 3 minutes down = alert (critical)
        'audio_behavior': 'urgent',   # 5s interval - critical infrastructure
        'check_interval': 60,         # Check every minute
        'description': 'Production servers, critical infrastructure'
    },
    'network': {
        'failure_threshold': 2,       # 2 minutes down = alert (very critical)
        'audio_behavior': 'urgent',   # 5s interval - critical infrastructure
        'check_interval': 60,         # Check every minute
        'description': 'Routers, switches, gateways, firewalls'
    },
    'workstation': {
        'failure_threshold': 5,       # 5 minutes down = alert
        'audio_behavior': 'normal',   # 30s interval - standard monitoring
        'check_interval': 120,        # Check every 2 minutes
        'description': 'Desktop computers, laptops'
    },
    'mobile': {
        'failure_threshold': 10,      # 10 minutes down = alert (sleep tolerance)
        'audio_behavior': 'silent',   # No audio - mobile devices sleep frequently
        'check_interval': 300,        # Check every 5 minutes
        'description': 'Phones, tablets - frequently sleep/disconnect'
    },
    'printer': {
        'failure_threshold': 5,       # 5 minutes down = alert
        'audio_behavior': 'normal',   # 30s interval - standard monitoring
        'check_interval': 120,        # Check every 2 minutes
        'description': 'Printers, scanners, fax machines'
    },
    'iot': {
        'failure_threshold': 6,       # 6 minutes down = alert
        'audio_behavior': 'normal',   # 30s interval - standard monitoring
        'check_interval': 120,        # Check every 2 minutes
        'description': 'Smart home devices, sensors, cameras'
    },
    'storage': {
        'failure_threshold': 3,       # 3 minutes down = alert (important)
        'audio_behavior': 'urgent',   # 5s interval - critical infrastructure
        'check_interval': 60,         # Check every minute
        'description': 'NAS, SAN, file servers'
    },
    'other': {
        'failure_threshold': 3,       # Default: 3 minutes
        'audio_behavior': 'normal',   # 30s interval - standard monitoring
        'check_interval': 60,         # Check every minute
        'description': 'Uncategorized devices'
    }
}

# Global instances
monitor_manager = None
webhook_notifier = None
smtp_notifier = None
backup_manager = None
backup_scheduler = None
auth_manager = None
config = {}


def load_config():
    """Load configuration from config.json"""
    global config
    try:
        with open('config.json', 'r') as f:
            config = json.load(f)
        logger.info("Configuration loaded successfully")
        return config
    except Exception as e:
        logger.error(f"Failed to load config.json: {e}")
        # Return default config
        return {
            "failure_threshold": 3,
            "check_interval": 60,
            "alert_repeat_interval": 300,
            "audio_enabled": True,
            "webhook_url": "",
            "webhook_enabled": False,
            "web_port": 8000,
            "ping_timeout": 5,
            "http_timeout": 10
        }


def detect_platform():
    """Detect if running on Raspberry Pi"""
    import os
    is_pi = os.path.exists('/sys/firmware/devicetree/base/model')
    return "Raspberry Pi" if is_pi else "Development"


def get_audio_interval(audio_behavior: str) -> Optional[int]:
    """
    Map audio behavior to loop interval.

    Args:
        audio_behavior: One of 'urgent', 'normal', 'silent'

    Returns:
        Interval in seconds, or None for silent
    """
    return AUDIO_INTERVALS.get(audio_behavior, AUDIO_INTERVAL_NORMAL)


def get_device_presets() -> Dict:
    """
    Get device type presets for auto-configuration.

    Returns:
        Dictionary of device presets
    """
    return DEVICE_PRESETS


async def stop_all_alerts():
    """Stop all active alerts."""
    # Clear alert state for client polling
    await alert_state.clear_alert()
    logger.warning("✅ AUDIBLE ALERT STOPPED - All systems up or acknowledged")


async def start_alert_for_target(target: Dict):
    """Start audio alert for the given target."""
    target_id = target['id']
    target_name = target['name']
    audio_behavior = target.get('audio_behavior', 'normal')

    # Get interval (handles legacy values via AUDIO_INTERVALS mapping)
    interval = get_audio_interval(audio_behavior)

    # Silent behavior - don't alert at all
    if interval is None or audio_behavior == 'silent':
        logger.debug(f"Audio disabled for {target_name} (behavior: {audio_behavior})")
        return

    # Get custom audio or use default
    custom_audio = target.get('audio_down_alert')
    if not custom_audio:
        custom_audio = audio_library.get_default_down_alert()
    if not custom_audio:
        custom_audio = 'system_down.mp3'  # Fallback

    # Update alert state for client polling
    await alert_state.set_alert(
        target_id=target_id,
        target_name=target_name,
        audio_file=custom_audio,
        interval_seconds=interval
    )

    logger.warning(
        f"🔊 AUDIBLE ALERT STARTED for HOST: {target_name} "
        f"({target['type']}://{target['address']}) - "
        f"Interval: {interval}s, Behavior: {audio_behavior}, "
        f"Audio: {custom_audio}"
    )


async def evaluate_global_alert_state():
    """
    Evaluate alert state and manage audio for all down targets.
    Uses optimized database query to only fetch targets that need alerting.
    """
    # Get targets that need alerting (optimized query with SQL filtering)
    down_targets = await db.get_down_unacknowledged_targets()

    # Log all down targets for visibility
    if down_targets:
        down_hosts = [
            f"{t['name']} ({t['type']}://{t['address']}, audio:{t.get('audio_behavior', 'unknown')})"
            for t in down_targets
        ]
        logger.info(
            f"Alert evaluation: {len(down_targets)} target(s) need alerting: {', '.join(down_hosts)}"
        )
    else:
        # Debug: Check if there are ANY down targets (even silent ones)
        all_targets = await db.get_all_targets()
        all_down = [t for t in all_targets if t.get('status') == 'down']
        if all_down:
            target_details = []
            for t in all_down:
                details = (f"{t['name']}(audio:{t.get('audio_behavior', 'NULL')}, "
                          f"enabled:{t.get('enabled', '?')}, ack:{t.get('acknowledged', '?')})")
                target_details.append(details)
            logger.warning(
                f"Alert evaluation: 0 targets need alerting (but {len(all_down)} down targets exist). "
                f"Details: {', '.join(target_details)}"
            )
        else:
            logger.info("Alert evaluation: 0 targets need alerting")

    logger.info(f"Alert state: audio_enabled={config.get('audio_enabled')}")

    if not down_targets:
        # All clear - stop everything
        await stop_all_alerts()
        return None

    # Most urgent target is already first (query returns ordered by urgency)
    most_urgent_target = down_targets[0]

    # Start or continue alerting
    await start_alert_for_target(most_urgent_target)

    return most_urgent_target


async def handle_alert_event(event: AlertEvent):
    """
    Handle alert events from the monitor manager.

    Uses Global Alert Aggregation:
    - Evaluates ALL down targets to find most urgent
    - Plays ONE audio loop for the most critical target
    - Webhooks still send per-target for granular notifications
    """
    logger.info(f"Alert event: {event.event_type} for {event.target_name}")

    # Get target for webhook and acknowledgment check
    target = await db.get_target(event.target_id)
    acknowledged = target.get('acknowledged', False) if target else False
    enabled = target.get('enabled', True) if target else True

    # Handle webhooks (per-target, sent ONCE when target goes down)
    if event.event_type in ['threshold_reached', 'alert_repeat']:
        # Only send webhook if:
        # 1. Target is not acknowledged
        # 2. Target is enabled
        # 3. Haven't already sent a webhook for this down event
        should_send = (
            webhook_notifier and
            webhook_notifier.enabled and
            not acknowledged and
            enabled and
            alert_state.should_send_webhook(event.target_id)
        )

        if should_send:
            try:
                await webhook_notifier.send_threshold_reached(
                    event.target_name,
                    event.target_id,
                    event.current_failures,
                    event.failure_threshold
                )
                # Mark that we've sent the webhook
                alert_state.mark_webhook_sent(event.target_id)
                logger.info(f"📤 Webhook sent for {event.target_name}")
            except Exception as e:
                logger.error(f"Failed to send webhook: {e}")
        elif webhook_notifier and webhook_notifier.enabled:
            # Log why webhook was skipped
            if acknowledged:
                logger.debug(f"Webhook skipped for {event.target_name}: target is acknowledged")
            elif not enabled:
                logger.debug(f"Webhook skipped for {event.target_name}: target is disabled")
            elif not alert_state.should_send_webhook(event.target_id):
                logger.debug(f"Webhook skipped for {event.target_name}: already notified")

        # Send SMTP email notification (only for threshold_reached, sent ONCE)
        if event.event_type == 'threshold_reached':
            # Only send email if:
            # 1. Target is not acknowledged
            # 2. Target is enabled
            # 3. Haven't already sent an email for this down event
            should_send = (
                smtp_notifier and
                smtp_notifier.enabled and
                not acknowledged and
                enabled and
                alert_state.should_send_email(event.target_id)
            )

            if should_send:
                try:
                    message = f"Target has failed {event.current_failures} consecutive checks (threshold: {event.failure_threshold})"
                    await smtp_notifier.send_alert(target, 'down', message)
                    # Mark that we've sent the email
                    alert_state.mark_email_sent(event.target_id)
                    logger.info(f"📧 SMTP alert sent for {event.target_name}")
                except Exception as e:
                    logger.error(f"Failed to send SMTP alert: {e}")
            elif smtp_notifier and smtp_notifier.enabled:
                # Log why email was skipped
                if acknowledged:
                    logger.debug(f"Email skipped for {event.target_name}: target is acknowledged")
                elif not enabled:
                    logger.debug(f"Email skipped for {event.target_name}: target is disabled")
                elif not alert_state.should_send_email(event.target_id):
                    logger.debug(f"Email skipped for {event.target_name}: already notified")

        # Evaluate global alert state (manages audio for ALL targets)
        await evaluate_global_alert_state()

    # Handle recovery events
    elif event.event_type == 'recovered':
        # Log recovery with host details
        target_info = f"({target['type']}://{target['address']})" if target else "(unknown)"
        logger.warning(
            f"✅ HOST RECOVERED: {event.target_name} {target_info}"
        )

        # Set recovery state for client polling (new approach)
        audio_behavior = target.get('audio_behavior', 'normal') if target else 'normal'
        if audio_behavior != 'silent':
            # Use custom audio if specified, otherwise use library default
            audio_file = target.get('audio_up_alert') if target else None
            if not audio_file:
                audio_file = audio_library.get_default_up_alert()
            if not audio_file:
                audio_file = 'system_up.mp3'  # Fallback

            await alert_state.set_recovery(
                target_id=event.target_id,
                target_name=event.target_name,
                audio_file=audio_file
            )

        # Send recovery webhook and clear state
        if webhook_notifier and webhook_notifier.enabled:
            try:
                await webhook_notifier.send_recovery(
                    event.target_name,
                    event.target_id
                )
                # Clear webhook state so a new webhook can be sent if target goes down again
                alert_state.clear_webhook_state(event.target_id)
                logger.info(f"📤 Recovery webhook sent for {event.target_name}")
            except Exception as e:
                logger.error(f"Failed to send webhook: {e}")

        # Send SMTP recovery notification and clear state
        if smtp_notifier and smtp_notifier.enabled:
            try:
                message = f"Target has recovered and is now responding normally"
                await smtp_notifier.send_alert(target, 'up', message)
                # Clear email state so a new email can be sent if target goes down again
                alert_state.clear_email_state(event.target_id)
                logger.info(f"📧 SMTP recovery notification sent for {event.target_name}")
            except Exception as e:
                logger.error(f"Failed to send SMTP recovery notification: {e}")

        # Re-evaluate global alert state (stops audio/relay if all targets are up)
        await evaluate_global_alert_state()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global monitor_manager, webhook_notifier, smtp_notifier, backup_manager, backup_scheduler, auth_manager

    logger.info("=" * 60)
    logger.info("🚀 Starting WebStatus...")
    logger.info("=" * 60)

    # Load configuration
    load_config()

    # Detect platform
    platform = detect_platform()
    if platform == "Raspberry Pi":
        logger.info("✅ Running on Raspberry Pi")
    else:
        logger.info("⚠️  Development Mode - Hardware Mocked")

    # Initialize database (includes all tables: monitoring, settings, auth)
    logger.info("💾 Initializing database...")
    await db.initialize()

    # Initialize authentication manager
    logger.info("🔐 Initializing authentication...")
    auth_manager = AuthManager(db)
    auth_routes.set_auth_manager(auth_manager)

    # Set auth manager for middleware
    from auth.middleware import set_auth_manager
    set_auth_manager(auth_manager)

    setup_required = await auth_manager.setup_required()
    if setup_required:
        logger.warning("⚠️  SETUP REQUIRED - Visit /auth/setup to create admin account")
    else:
        logger.info("✅ Authentication configured")

    # Initialize webhook notifier
    logger.info("📤 Initializing webhook notifier...")
    webhook_notifier = WebhookNotifier(
        config.get('webhook_url'),
        config.get('webhook_enabled', False)
    )

    # Initialize SMTP notifier
    logger.info("📧 Initializing SMTP notifier...")
    try:
        smtp_settings = await db.get_settings_by_category('smtp')
        smtp_notifier = SMTPNotifier(smtp_settings)
        if smtp_notifier.enabled:
            logger.info(f"✅ SMTP enabled - Host: {smtp_notifier.host}:{smtp_notifier.port}, Recipients: {len(smtp_notifier.recipients)}")
        else:
            logger.info("⚠️  SMTP notifications disabled")
    except Exception as e:
        logger.warning(f"Failed to initialize SMTP notifier: {e}")
        smtp_notifier = SMTPNotifier({})  # Create disabled instance

    # Initialize backup system
    logger.info("💾 Initializing backup system...")
    try:
        backup_settings = await db.get_settings_by_category('backup')
        backup_manager = BackupManager(backup_settings)

        if backup_manager.enabled:
            backup_scheduler = BackupScheduler(
                backup_manager,
                backup_settings.get('schedule', '0 2 * * *')
            )
            await backup_scheduler.start()
            logger.info(f"✅ Automated backups enabled - Schedule: {backup_settings.get('schedule', '0 2 * * *')}, Retention: {backup_manager.retention_days} days")
        else:
            logger.info("⚠️  Automated backups disabled")
    except Exception as e:
        logger.warning(f"Failed to initialize backup system: {e}")
        backup_manager = BackupManager({})  # Create disabled instance

    # Initialize monitor manager
    logger.info("📡 Initializing monitor manager...")
    monitor_manager = MonitorManager(config)
    monitor_manager.register_alert_callback(handle_alert_event)

    # Set globals in API routes
    routes.set_globals(monitor_manager, config, webhook_notifier)

    # Set callbacks to avoid circular imports
    routes.set_callbacks(
        alert_evaluator=evaluate_global_alert_state,
        presets_provider=get_device_presets
    )

    # Start monitoring
    await monitor_manager.start()

    # Evaluate alert state to restore audio alerts for any down targets (after restart)
    logger.info("🔄 Evaluating alert state after startup...")
    await evaluate_global_alert_state()

    # Print startup info
    port = config.get('web_port', 8000)
    logger.info("=" * 60)
    logger.info("✅ WebStatus Started Successfully")
    logger.info("=" * 60)
    logger.info(f"🌐 Web Interface: http://localhost:{port}")
    logger.info(f"📡 API Docs: http://localhost:{port}/docs")
    logger.info(f"📡 API Endpoint: http://localhost:{port}/api/v1")
    logger.info(f"💾 Database: data/monitoring.db")
    logger.info(f"📍 Config: config.json")
    logger.info(f"🖥️  Platform: {platform}")
    logger.info("=" * 60)

    yield

    # Shutdown
    logger.info("Shutting down WebStatus...")

    # Stop monitoring first
    if monitor_manager:
        await monitor_manager.stop()
        logger.info("✅ Monitor manager stopped")

    # Stop backup scheduler
    if backup_scheduler:
        await backup_scheduler.stop()
        logger.info("✅ Backup scheduler stopped")

    # Close database connection (CRITICAL for preventing corruption)
    try:
        await db.close()
        logger.info("✅ Database connection closed gracefully")
    except Exception as e:
        logger.error(f"Error closing database: {e}")

    # Stop WebSocket manager
    if websocket_manager:
        logger.info("✅ WebSocket connections closed")

    logger.info("✅ Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="WebStatus",
    description="Network Monitoring System with GPIO Relay and Audio Alerts",
    version="1.0.0",
    lifespan=lifespan
)

# Include API routes
app.include_router(routes.router)
app.include_router(public_routes.router)
app.include_router(auth_routes.router)

# Mount static files
app.mount("/static", StaticFiles(directory="web/static"), name="static")
app.mount("/sounds", StaticFiles(directory="sounds"), name="sounds")

# Add security headers middleware
app.add_middleware(SecurityHeadersMiddleware)

# Add authentication middleware (gets auth_manager from global variable)
app.add_middleware(AuthMiddleware)


@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main web interface"""
    with open('web/templates/index.html', 'r') as f:
        return HTMLResponse(content=f.read())


@app.get("/ui-demo", response_class=HTMLResponse)
async def ui_demo():
    """Serve the UI enhancements demo page"""
    with open('web/templates/ui_demo.html', 'r') as f:
        return HTMLResponse(content=f.read())


def main():
    """Main entry point"""
    import os
    config = load_config()
    port = config.get('web_port', 8000)

    # Check if running in development mode (hot reload enabled)
    reload_enabled = os.getenv('UVICORN_RELOAD', 'false').lower() == 'true'

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        log_level="info",
        access_log=True,
        reload=reload_enabled
    )


if __name__ == "__main__":
    main()
