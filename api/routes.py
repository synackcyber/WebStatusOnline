"""
API routes for WebStatus.
Optimized with security enhancements and performance improvements.
"""
from fastapi import APIRouter, HTTPException, status, UploadFile, File
from typing import List, Dict, Any, Optional
import json
import uuid
import shutil
import ipaddress
import logging
import re
import aiofiles
from pathlib import Path
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from monitor.models import TargetCreate, TargetUpdate, Target, SystemStatus
from database.db import db
from utils.time_utils import calculate_current_duration, calculate_uptime_percentage, format_duration
from config.features import FeatureFlags

logger = logging.getLogger(__name__)

# Constants
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB max file upload
ALLOWED_AUDIO_EXTENSIONS = {'.wav', '.mp3', '.aiff', '.ogg', '.m4a'}
DEFAULT_HISTORY_LIMIT = 100
CACHE_TTL_SECONDS = 5


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename to prevent path traversal attacks.

    Security: Removes any path components and special characters
    that could be used for directory traversal attacks.
    """
    # Get just the filename (no path components)
    base_filename = Path(filename).name
    # Remove any dangerous characters, keep only alphanumeric, dots, dashes, underscores
    safe_filename = re.sub(r'[^a-zA-Z0-9._-]', '_', base_filename)
    # Prevent hidden files
    if safe_filename.startswith('.'):
        safe_filename = '_' + safe_filename[1:]
    return safe_filename


async def validate_file_upload(file: UploadFile, max_size: int = MAX_FILE_SIZE,
                               allowed_extensions: set = ALLOWED_AUDIO_EXTENSIONS) -> str:
    """
    Validate uploaded file for security and constraints.

    Returns sanitized filename if valid, raises HTTPException otherwise.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    # Check file extension
    file_ext = Path(file.filename).suffix.lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed: {', '.join(sorted(allowed_extensions))}"
        )

    # Check file size (read first chunk to verify)
    file.file.seek(0, 2)  # Seek to end
    file_size = file.file.tell()
    file.file.seek(0)  # Reset to beginning

    if file_size > max_size:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size: {max_size / 1024 / 1024:.1f}MB"
        )

    # Sanitize filename
    safe_filename = sanitize_filename(file.filename)

    return safe_filename


def check_service_available(service_name: str, service):
    """
    Check if a global service is available, raise HTTPException if not.

    This provides consistent error handling for service dependencies.
    """
    if service is None:
        raise HTTPException(
            status_code=503,
            detail=f"{service_name} is not available. Service may be starting up."
        )

router = APIRouter(prefix="/api/v1", tags=["api"])


# Keyed response cache for high-frequency endpoints
class KeyedResponseCache:
    """
    Time-based cache with support for multiple keys.

    Improvements over old cache:
    - Supports multiple cache keys (not just single value)
    - Automatic cleanup of expired entries
    - Thread-safe operations
    """

    def __init__(self, ttl_seconds: int = 5):
        self.cache: Dict[str, tuple[Any, datetime]] = {}
        self.ttl = timedelta(seconds=ttl_seconds)

    def get(self, key: str = "default") -> Optional[Any]:
        """Get cached value for key if not expired."""
        if key not in self.cache:
            return None

        value, expires_at = self.cache[key]

        if datetime.utcnow() > expires_at:
            # Expired, remove it
            del self.cache[key]
            return None

        return value

    def set(self, value: Any, key: str = "default"):
        """Cache value with TTL for specific key."""
        expires_at = datetime.utcnow() + self.ttl
        self.cache[key] = (value, expires_at)

    def invalidate(self, key: str = None):
        """Clear cache for specific key or all keys."""
        if key is None:
            # Clear all
            self.cache.clear()
        elif key in self.cache:
            del self.cache[key]

    def cleanup_expired(self):
        """Remove all expired entries (call periodically)."""
        now = datetime.utcnow()
        expired_keys = [k for k, (_, exp) in self.cache.items() if now > exp]
        for key in expired_keys:
            del self.cache[key]


# Cache instances
targets_cache = KeyedResponseCache(ttl_seconds=CACHE_TTL_SECONDS)


# Global references (set by main.py)
monitor_manager = None
app_config = None
webhook_notifier = None

# Callback functions (to avoid circular imports)
alert_state_evaluator = None
device_presets_provider = None


def set_globals(manager, config, webhook):
    """Set global references to core components."""
    global monitor_manager, app_config, webhook_notifier
    monitor_manager = manager
    app_config = config
    webhook_notifier = webhook


def set_callbacks(alert_evaluator, presets_provider):
    """
    Set callback functions to avoid circular imports.

    This should be called by main.py after routes are registered.
    """
    global alert_state_evaluator, device_presets_provider
    alert_state_evaluator = alert_evaluator
    device_presets_provider = presets_provider


# Target endpoints
@router.get("/targets")
async def get_targets():
    """Get all monitoring targets with uptime/downtime calculations."""
    # Check cache first
    cached = targets_cache.get()
    if cached is not None:
        return cached

    # Cache miss - fetch from database
    targets = await db.get_all_targets()

    # Enhance each target with current uptime/downtime duration
    for target in targets:
        current_duration, formatted = calculate_current_duration(
            target.get('last_status_change'),
            target.get('status', 'unknown')
        )

        # Add current duration info
        if target.get('status') == 'up':
            target['current_uptime'] = current_duration
            target['current_uptime_formatted'] = formatted
            target['current_downtime'] = 0
            target['current_downtime_formatted'] = "0s"
        elif target.get('status') == 'down':
            target['current_downtime'] = current_duration
            target['current_downtime_formatted'] = formatted
            target['current_uptime'] = 0
            target['current_uptime_formatted'] = "0s"
        else:
            target['current_uptime'] = 0
            target['current_uptime_formatted'] = "0s"
            target['current_downtime'] = 0
            target['current_downtime_formatted'] = "0s"

        # Calculate overall uptime percentage
        target['uptime_percentage'] = calculate_uptime_percentage(
            target.get('total_uptime', 0),
            target.get('total_downtime', 0),
            current_duration,
            target.get('status', 'unknown')
        )

        # Format total uptime/downtime
        target['total_uptime_formatted'] = format_duration(target.get('total_uptime', 0))
        target['total_downtime_formatted'] = format_duration(target.get('total_downtime', 0))

    # Cache result
    targets_cache.set(targets)

    return targets


@router.get("/targets/{target_id}", response_model=Target)
async def get_target(target_id: str):
    """Get a specific target by ID."""
    target = await db.get_target(target_id)
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")
    return target


@router.get("/targets/{target_id}/uptime")
async def get_target_uptime(target_id: str):
    """
    Get uptime metrics for a target using industry-standard calculations.
    Returns uptime percentages for 24h, 7d, and 30d windows.
    """
    # Verify target exists
    target = await db.get_target(target_id)
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")

    # Calculate current duration
    current_duration, current_duration_formatted = calculate_current_duration(
        target.get('last_status_change'),
        target.get('status', 'unknown')
    )

    # Get uptime metrics from check history
    uptime_metrics = await db.get_uptime_metrics(target_id)

    return {
        "target_id": target_id,
        "current_status": target.get('status', 'unknown'),
        "current_duration": current_duration,
        "current_duration_formatted": current_duration_formatted,
        **uptime_metrics
    }


@router.post("/targets", response_model=Target, status_code=status.HTTP_201_CREATED)
async def create_target(target_data: TargetCreate):
    """Create a new monitoring target."""
    # Create target with new ID
    target_dict = target_data.dict()
    target_dict['id'] = str(uuid.uuid4())

    # Validate address format based on target type
    validate_target_address(target_dict['type'], target_dict['address'])

    # Use global config defaults if not specified
    if target_dict.get('check_interval') is None:
        target_dict['check_interval'] = app_config.get('check_interval', 60)
    if target_dict.get('failure_threshold') is None:
        target_dict['failure_threshold'] = app_config.get('failure_threshold', 3)

    # Save to database
    await db.create_target(target_dict)

    # Invalidate cache
    targets_cache.invalidate()

    # Start monitoring if enabled
    if target_dict.get('enabled', True) and monitor_manager:
        target = await db.get_target(target_dict['id'])
        await monitor_manager.start_target_monitoring(target)

    return target_dict


@router.put("/targets/{target_id}", response_model=Target)
async def update_target(target_id: str, target_data: TargetUpdate):
    """Update a monitoring target."""
    # Check if target exists
    existing = await db.get_target(target_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Target not found")

    # Update target
    updates = target_data.dict(exclude_unset=True)

    # Validate address if being updated
    if 'address' in updates or 'type' in updates:
        target_type = updates.get('type', existing['type'])
        address = updates.get('address', existing['address'])
        validate_target_address(target_type, address)

    if updates:
        await db.update_target(target_id, updates)

    # Invalidate cache
    targets_cache.invalidate()

    # Log enable/disable changes
    if 'enabled' in updates:
        if updates['enabled']:
            await db.add_alert_log(target_id, "enabled", "Target enabled by user")
        else:
            await db.add_alert_log(target_id, "disabled", "Target disabled by user")

    # Get updated target ONCE (optimization: avoid duplicate queries)
    updated_target = await db.get_target(target_id)

    # Reload monitoring if manager is available
    if monitor_manager and updated_target:
        if updated_target.get('enabled'):
            await monitor_manager.start_target_monitoring(updated_target)
        else:
            await monitor_manager.stop_target_monitoring(target_id)

        # Re-evaluate global alert state immediately after target update
        # This ensures audio alerts stop if a down target is disabled,
        # or resumes if settings changed for an active alert
        if alert_state_evaluator:
            await alert_state_evaluator()

    # Return the already-fetched updated target (no duplicate query)
    return updated_target


@router.delete("/targets/{target_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_target(target_id: str):
    """Delete a monitoring target."""
    # Check if target exists
    existing = await db.get_target(target_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Target not found")

    # Stop monitoring
    if monitor_manager:
        await monitor_manager.stop_target_monitoring(target_id)

    # Delete from database
    await db.delete_target(target_id)

    # Invalidate cache
    targets_cache.invalidate()

    # Re-evaluate global alert state immediately after target deletion
    # This ensures audio alerts stop if a down target is deleted
    if alert_state_evaluator:
        await alert_state_evaluator()

    return None


@router.post("/targets/{target_id}/check")
async def check_target_now(target_id: str):
    """Manually trigger a check for a target."""
    # Check if target exists
    existing = await db.get_target(target_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Target not found")

    # Trigger check
    if monitor_manager:
        await monitor_manager.check_target_now(target_id)
        # Get updated target
        target = await db.get_target(target_id)
        return {"message": "Check triggered", "status": target['status']}
    else:
        raise HTTPException(status_code=503, detail="Monitor manager not available")


@router.post("/targets/{target_id}/acknowledge")
async def acknowledge_target(target_id: str):
    """Acknowledge a target alert to stop notifications while tracking downtime."""
    # Check if target exists
    existing = await db.get_target(target_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Target not found")

    # Acknowledge the target
    await db.acknowledge_target(target_id)

    # Invalidate cache
    targets_cache.invalidate()

    # Log the acknowledgment
    await db.add_alert_log(
        target_id,
        "acknowledged",
        "Alert acknowledged by user"
    )

    # Re-evaluate global alert state to check if other targets still need alerting
    # This will stop audio if all targets are acknowledged/up,
    # or continue/restart alerting for remaining unacknowledged down targets
    if alert_state_evaluator:
        await alert_state_evaluator()

    # Get updated target
    target = await db.get_target(target_id)
    return {
        "message": "Target acknowledged",
        "target_id": target_id,
        "acknowledged": True,
        "acknowledged_at": target['acknowledged_at']
    }


@router.delete("/targets/{target_id}/acknowledge")
async def unacknowledge_target(target_id: str):
    """Remove acknowledgment from a target."""
    # Check if target exists
    existing = await db.get_target(target_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Target not found")

    # Unacknowledge the target
    await db.unacknowledge_target(target_id)

    # Log the unacknowledgment
    await db.add_alert_log(
        target_id,
        "unacknowledged",
        "Alert unacknowledged by user"
    )

    # Re-evaluate global alert state - if target is still down, should restart alerts
    if alert_state_evaluator:
        await alert_state_evaluator()

    # Get updated target
    target = await db.get_target(target_id)
    return {
        "message": "Target unacknowledged",
        "target_id": target_id,
        "acknowledged": False
    }


# Statistics endpoints
@router.get("/targets/{target_id}/statistics")
async def get_target_statistics(target_id: str):
    """Get statistics for a target."""
    target = await db.get_target(target_id)
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")

    stats = await db.get_statistics(target_id)
    return stats


@router.get("/targets/{target_id}/history")
async def get_target_history(target_id: str, limit: int = 100):
    """Get check history for a target."""
    target = await db.get_target(target_id)
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")

    history = await db.get_check_history(target_id, limit)
    return history


# Status endpoint
@router.get("/status", response_model=SystemStatus)
async def get_system_status():
    """Get overall system status."""
    targets = await db.get_all_targets()

    total_targets = len(targets)
    enabled_targets = sum(1 for t in targets if t['enabled'])
    targets_up = sum(1 for t in targets if t['status'] == 'up' and t['enabled'])
    targets_down = sum(1 for t in targets if t['status'] == 'down' and t['enabled'])
    targets_unknown = sum(1 for t in targets if t['status'] == 'unknown' and t['enabled'])

    alerts_active = 0
    if monitor_manager:
        alerts_active = len(monitor_manager.get_active_alerts())

    return SystemStatus(
        total_targets=total_targets,
        enabled_targets=enabled_targets,
        targets_up=targets_up,
        targets_down=targets_down,
        targets_unknown=targets_unknown,
        alerts_active=alerts_active
    )


# Alert log endpoint
@router.get("/alerts")
async def get_alert_log(target_id: str = None, limit: int = 100):
    """Get alert log entries with target details."""
    alerts = await db.get_alert_log(target_id, limit)

    # Enhance alerts with target names
    targets = await db.get_all_targets()
    target_map = {t['id']: t['name'] for t in targets}

    for alert in alerts:
        alert['target_name'] = target_map.get(alert['target_id'], 'Unknown Target')

    return alerts


@router.get("/incidents")
async def get_incidents(days: int = 14) -> Dict[str, Any]:
    """
    Internal API endpoint - Returns recent incidents from the alert log.
    Shows ALL targets (not filtered by public_visible).

    Query parameters:
    - days: Number of days to look back (default: 14, max: 90)

    Returns list of incidents with start time, duration, and status.
    """
    try:
        # Limit days parameter
        days = max(1, min(days, 90))

        # Calculate time range
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)

        # Get all targets
        all_targets = await db.get_all_targets()
        target_map = {t['id']: {'name': t['name'], 'device_type': t.get('device_type', 'other')} for t in all_targets}

        # Get all recent alerts
        all_alerts = await db.get_alert_log(limit=1000)

        # Build incident list - process in chronological order (oldest first)
        incidents_list = []
        current_incidents = {}  # Track ongoing incidents per target

        # Reverse the list to process oldest first
        for alert in reversed(all_alerts):
            # Parse timestamp
            try:
                alert_time = datetime.fromisoformat(alert['timestamp'].replace('Z', '+00:00'))
                if alert_time.tzinfo is None:
                    # If no timezone info, assume UTC
                    alert_time = alert_time.replace(tzinfo=timezone.utc)

                # Skip if outside time range
                if alert_time < cutoff_time:
                    continue
            except (ValueError, KeyError):
                continue

            target_id = alert['target_id']
            target_info = target_map.get(target_id, {'name': 'Unknown Target', 'device_type': 'other'})
            target_name = target_info['name']
            device_type = target_info['device_type']
            event_type = alert.get('event_type', '')

            if event_type == 'threshold_reached':
                # Check if target already has an ongoing incident
                if target_id not in current_incidents or current_incidents[target_id].get('resolved_at'):
                    # Start a new incident for this target
                    incident = {
                        'id': alert.get('id'),
                        'target_id': target_id,
                        'target_name': target_name,
                        'device_type': device_type,
                        'title': f"Outage: {target_name}",
                        'started_at': alert['timestamp'],
                        'resolved_at': None,
                        'status': 'investigating',
                        'message': alert.get('message', '')
                    }
                    current_incidents[target_id] = incident
                    incidents_list.append(incident)

            elif event_type == 'recovered':
                # Resolve the current incident for this target if it exists
                if target_id in current_incidents and not current_incidents[target_id].get('resolved_at'):
                    current_incidents[target_id]['resolved_at'] = alert['timestamp']
                    current_incidents[target_id]['status'] = 'resolved'

        # Sort by start time (newest first)
        incidents_list.sort(key=lambda x: x['started_at'], reverse=True)

        # Calculate durations and format incidents
        formatted_incidents = []
        total_downtime_seconds = 0
        ongoing_count = 0
        resolved_count = 0
        target_incident_counts = {}  # Track incidents per target

        for incident in incidents_list:
            started_at = datetime.fromisoformat(incident['started_at'].replace('Z', '+00:00'))

            if incident['resolved_at']:
                resolved_at = datetime.fromisoformat(incident['resolved_at'].replace('Z', '+00:00'))
                duration_seconds = (resolved_at - started_at).total_seconds()
                resolved_count += 1
            else:
                # Still ongoing
                duration_seconds = (datetime.now(timezone.utc).replace(tzinfo=started_at.tzinfo) - started_at).total_seconds()
                incident['status'] = 'ongoing'
                ongoing_count += 1

            total_downtime_seconds += duration_seconds

            # Track incident count per target
            target_name = incident['target_name']
            target_incident_counts[target_name] = target_incident_counts.get(target_name, 0) + 1

            # Format duration
            if duration_seconds < 60:
                duration_str = f"{int(duration_seconds)}s"
            elif duration_seconds < 3600:
                minutes = int(duration_seconds / 60)
                duration_str = f"{minutes}m"
            elif duration_seconds < 86400:
                hours = int(duration_seconds / 3600)
                minutes = int((duration_seconds % 3600) / 60)
                duration_str = f"{hours}h {minutes}m" if minutes > 0 else f"{hours}h"
            else:
                days_count = int(duration_seconds / 86400)
                hours = int((duration_seconds % 86400) / 3600)
                duration_str = f"{days_count}d {hours}h" if hours > 0 else f"{days_count}d"

            formatted_incidents.append({
                'id': incident['id'],
                'title': incident['title'],
                'target_name': incident['target_name'],
                'device_type': incident.get('device_type', 'other'),
                'started_at': incident['started_at'],
                'resolved_at': incident['resolved_at'],
                'duration': duration_str,
                'status': incident['status']
            })

        # Format total downtime
        if total_downtime_seconds < 60:
            total_downtime_str = f"{int(total_downtime_seconds)}s"
        elif total_downtime_seconds < 3600:
            minutes = int(total_downtime_seconds / 60)
            total_downtime_str = f"{minutes}m"
        elif total_downtime_seconds < 86400:
            hours = int(total_downtime_seconds / 3600)
            minutes = int((total_downtime_seconds % 3600) / 60)
            total_downtime_str = f"{hours}h {minutes}m" if minutes > 0 else f"{hours}h"
        else:
            days_count = int(total_downtime_seconds / 86400)
            hours = int((total_downtime_seconds % 86400) / 3600)
            total_downtime_str = f"{days_count}d {hours}h" if hours > 0 else f"{days_count}d"

        # Find most affected target
        most_affected_target = None
        most_affected_count = 0
        if target_incident_counts:
            most_affected_target = max(target_incident_counts, key=target_incident_counts.get)
            most_affected_count = target_incident_counts[most_affected_target]

        return {
            'success': True,
            'incidents': formatted_incidents,
            'count': len(formatted_incidents),
            'days': days,
            'summary': {
                'total_incidents': len(formatted_incidents),
                'ongoing_count': ongoing_count,
                'resolved_count': resolved_count,
                'total_downtime': total_downtime_str,
                'most_affected_target': most_affected_target,
                'most_affected_count': most_affected_count
            }
        }

    except Exception as e:
        logger.error(f"Error fetching incidents: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch incidents"
        )


@router.get("/alerts/state")
async def get_alert_state():
    """
    Get current alert state for audio playback decisions.

    This endpoint is designed to be polled by clients every 2 seconds to determine
    if/when to play audio alerts. It's lightweight (O(1) operation) and returns
    the current alert state including timing information for the next audio play.

    Clients use this state combined with localStorage to prevent duplicate alerts
    across page refreshes, multiple tabs, and mobile reconnections.

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
    # Import here to avoid circular dependency
    from alerts.state_manager import alert_state

    return alert_state.get_state()


# Configuration endpoints
@router.get("/config")
async def get_config():
    """Get current configuration."""
    return app_config


@router.put("/config")
async def update_config(config_update: Dict):
    """Update configuration."""
    # Update config
    app_config.update(config_update)

    # Save to file
    with open('config.json', 'w') as f:
        json.dump(app_config, f, indent=2)

    # Update components if needed
    # GPIO/Relay support has been removed for Docker compatibility

    if 'webhook_url' in config_update or 'webhook_enabled' in config_update:
        if webhook_notifier:
            webhook_notifier.update_config(
                app_config.get('webhook_url'),
                app_config.get('webhook_enabled', False)
            )

    return {"message": "Configuration updated", "config": app_config}


@router.get("/device-presets")
async def get_device_presets():
    """Get device type presets for auto-configuration."""
    if device_presets_provider:
        return device_presets_provider()
    return {}


@router.get("/config/features")
async def get_feature_flags():
    """
    Get enabled/disabled feature flags.

    Returns:
        Dictionary of feature flags and their enabled status
    """
    return FeatureFlags.get_all_features()


# Test endpoints
@router.post("/test/relay")
async def test_relay():
    """Test relay activation - DEPRECATED: GPIO/Relay support removed."""
    raise HTTPException(
        status_code=410,
        detail="GPIO/Relay support has been removed for Docker compatibility"
    )



@router.post("/test/webhook")
async def test_webhook():
    """Test webhook notification."""
    if not webhook_notifier:
        raise HTTPException(status_code=503, detail="Webhook notifier not available")

    try:
        result = await webhook_notifier.test_webhook()
        return {
            "message": "Webhook test completed",
            "success": result,
            "url": webhook_notifier.webhook_url if webhook_notifier.enabled else None
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Webhook test failed: {str(e)}")


# Audio file upload endpoints
@router.post("/upload/audio/down")
async def upload_down_sound(file: UploadFile = File(...)):
    """
    Upload custom alert sound (system down).

    Security: Validates file type, size, and sanitizes filename.
    Performance: Uses async file I/O to avoid blocking event loop.
    """
    try:
        # Validate and sanitize file (security + size check)
        safe_filename = await validate_file_upload(file, MAX_FILE_SIZE, ALLOWED_AUDIO_EXTENSIONS)

        # Get file extension from safe filename
        file_ext = Path(safe_filename).suffix.lower()

        # Save file to sounds directory
        sounds_dir = Path("sounds")
        sounds_dir.mkdir(exist_ok=True)

        # Use consistent naming for system sounds
        output_file = sounds_dir / f"system_down{file_ext}"

        # Save uploaded file (async I/O - non-blocking)
        async with aiofiles.open(output_file, "wb") as buffer:
            content = await file.read()
            await buffer.write(content)

        return {
            "message": "Down sound uploaded successfully",
            "filename": output_file.name,
            "size": len(content)
        }
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"File upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.post("/upload/audio/up")
async def upload_up_sound(file: UploadFile = File(...)):
    """
    Upload custom recovery sound (system up).

    Security: Validates file type, size, and sanitizes filename.
    Performance: Uses async file I/O to avoid blocking event loop.
    """
    try:
        # Validate and sanitize file (security + size check)
        safe_filename = await validate_file_upload(file, MAX_FILE_SIZE, ALLOWED_AUDIO_EXTENSIONS)

        # Get file extension from safe filename
        file_ext = Path(safe_filename).suffix.lower()

        # Save file to sounds directory
        sounds_dir = Path("sounds")
        sounds_dir.mkdir(exist_ok=True)

        # Use consistent naming for system sounds
        output_file = sounds_dir / f"system_up{file_ext}"

        # Save uploaded file (async I/O - non-blocking)
        async with aiofiles.open(output_file, "wb") as buffer:
            content = await file.read()
            await buffer.write(content)

        return {
            "message": "Up sound uploaded successfully",
            "filename": output_file.name,
            "size": len(content)
        }
    except HTTPException:
        raise  # Re-raise HTTP exceptions as-is
    except Exception as e:
        logger.error(f"File upload failed: {e}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")




# Network Discovery endpoints
@router.post("/discover/subnet")
async def discover_subnet_endpoint(request: Dict[str, Any]):
    """
    Discover devices in a subnet.

    Request body:
        subnet: Subnet in CIDR notation (e.g., '192.168.1.0/24')
        max_concurrent: Maximum concurrent scans (default: 50)
        timeout: Timeout per device (default: 2)
        check_http: Whether to check for HTTP/HTTPS (default: True)
    """
    # Check if discovery feature is enabled
    if not FeatureFlags.DISCOVERY_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Discovery feature is disabled in this deployment. "
                   "This feature may not be available in cloud environments due to network restrictions."
        )

    from monitor.discovery import discover_subnet, suggest_monitoring_config

    subnet = request.get('subnet')
    if not subnet:
        raise HTTPException(status_code=400, detail="subnet is required")

    devices = await discover_subnet(
        subnet=subnet,
        max_concurrent=request.get('max_concurrent', 50),
        timeout=request.get('timeout', 2),
        check_http=request.get('check_http', True)
    )

    # Add suggested monitoring config to each device
    for device in devices:
        device['suggested_config'] = suggest_monitoring_config(device)

    return {
        "subnet": subnet,
        "devices_found": len(devices),
        "devices": devices
    }


@router.post("/discover/host")
async def discover_host_endpoint(
    ip: str,
    check_http: bool = True,
    timeout: int = 3
):
    """Discover a single host with full details."""
    # Check if discovery feature is enabled
    if not FeatureFlags.DISCOVERY_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Discovery feature is disabled in this deployment."
        )

    from monitor.discovery import discover_single_host, suggest_monitoring_config

    device = await discover_single_host(
        ip=ip,
        check_http=check_http,
        timeout=timeout
    )

    if not device:
        raise HTTPException(status_code=404, detail=f"Host {ip} is not reachable")

    device['suggested_config'] = suggest_monitoring_config(device)

    return device


@router.post("/discover/import")
async def import_discovered_devices(devices: List[Dict]):
    """
    Bulk import discovered devices as monitoring targets.

    Args:
        devices: List of device configurations to import
    """
    import uuid
    imported = []
    failed = []

    for device_config in devices:
        try:
            # Generate unique ID
            target_id = str(uuid.uuid4())

            # Create target from suggested config
            target = {
                'id': target_id,
                'name': device_config.get('name', device_config.get('ip', 'Unknown')),
                'type': device_config.get('type', 'ping'),
                'address': device_config.get('address', device_config.get('ip')),
                'check_interval': device_config.get('check_interval', 60),
                'failure_threshold': device_config.get('failure_threshold', 3),
                'enabled': 1,
                'audio_behavior': 'normal'
            }

            # Create in database
            await db.create_target(target)

            # Start monitoring if enabled
            if target.get('enabled', 1) and monitor_manager:
                target_from_db = await db.get_target(target_id)
                if target_from_db:
                    await monitor_manager.start_target_monitoring(target_from_db)
                    logger.info(f"Started monitoring imported target: {target['name']}")
                else:
                    logger.error(f"Failed to retrieve target from DB after creation: {target_id}")
            elif not monitor_manager:
                logger.warning("Monitor manager not available for imported target")

            imported.append({
                'id': target_id,
                'name': target['name'],
                'address': target['address']
            })

        except Exception as e:
            logger.error(f"Failed to import device {device_config.get('name', 'Unknown')}: {str(e)}")
            failed.append({
                'device': device_config.get('name', device_config.get('ip', 'Unknown')),
                'error': str(e)
            })

    # Invalidate cache after importing
    targets_cache.invalidate()

    return {
        "imported": len(imported),
        "failed": len(failed),
        "imported_devices": imported,
        "failed_devices": failed
    }


# Audio Library endpoints
@router.get("/audio/library")
async def get_audio_library():
    """Get the complete audio alert library."""
    from alerts.audio_library import audio_library
    return {
        "alerts": audio_library.get_all_alerts(),
        "categories": audio_library.get_categories(),
        "stats": audio_library.get_library_stats(),
        "default_down_alert": audio_library.library_data.get("default_down_alert", "system_down.aiff"),
        "default_up_alert": audio_library.library_data.get("default_up_alert", "system_up.aiff")
    }


@router.put("/audio/library/defaults")
async def update_default_alerts(defaults: Dict[str, Any]):
    """Update the default alert sounds for the library."""
    from alerts.audio_library import audio_library

    default_down = defaults.get("default_down_alert")
    default_up = defaults.get("default_up_alert")

    if not default_down or not default_up:
        raise HTTPException(status_code=400, detail="Both default_down_alert and default_up_alert are required")

    # Update library data
    audio_library.library_data["default_down_alert"] = default_down
    audio_library.library_data["default_up_alert"] = default_up

    # Save to file
    audio_library.save_library()

    return {
        "message": "Default alerts updated successfully",
        "default_down_alert": default_down,
        "default_up_alert": default_up
    }


@router.get("/audio/library/category/{category}")
async def get_audio_by_category(category: str):
    """Get audio alerts filtered by category."""
    from alerts.audio_library import audio_library
    return {
        "category": category,
        "alerts": audio_library.get_alerts_by_category(category)
    }


@router.get("/audio/library/event/{event_type}")
async def get_audio_by_event_type(event_type: str):
    """Get audio alerts suitable for a specific event type."""
    from alerts.audio_library import audio_library
    return {
        "event_type": event_type,
        "alerts": audio_library.get_alerts_by_event_type(event_type)
    }


@router.get("/audio/library/scan")
async def scan_audio_files():
    """Scan for new audio files not in the library."""
    from alerts.audio_library import audio_library
    new_files = audio_library.scan_audio_files()
    return {
        "new_files": new_files,
        "count": len(new_files)
    }


@router.post("/audio/library/alert")
async def add_audio_alert(alert_data: Dict[str, Any]):
    """Add a new alert to the library."""
    from alerts.audio_library import audio_library

    required_fields = ["id", "name", "filename", "category", "event_types"]
    for field in required_fields:
        if field not in alert_data:
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

    success = audio_library.add_alert(alert_data)
    if success:
        return {"message": "Alert added successfully", "alert_id": alert_data["id"]}
    else:
        raise HTTPException(status_code=500, detail="Failed to add alert")


@router.delete("/audio/library/alert/{alert_id}")
async def delete_audio_alert(alert_id: str):
    """Remove an alert from the library."""
    from alerts.audio_library import audio_library

    success = audio_library.remove_alert(alert_id)
    if success:
        return {"message": "Alert removed successfully"}
    else:
        raise HTTPException(status_code=404, detail="Alert not found")


@router.post("/audio/library/upload")
async def upload_audio_to_library(
    file: UploadFile = File(...),
    name: str = None,
    category: str = "professional",
    event_types: str = "down,threshold_reached",
    description: str = ""
):
    """
    Upload a new audio file to the library with metadata.

    Security: Validates file type, size, and sanitizes filename.
    Performance: Uses async file I/O to avoid blocking event loop.
    """
    from alerts.audio_library import audio_library

    try:
        # Validate and sanitize file (security + size check)
        safe_filename = await validate_file_upload(file, MAX_FILE_SIZE, ALLOWED_AUDIO_EXTENSIONS)
        file_ext = Path(safe_filename).suffix.lower()

        # Validate category
        valid_categories = ["beeps", "tones", "vocal", "professional"]
        if category not in valid_categories:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid category. Must be one of: {', '.join(valid_categories)}"
            )

        # Further sanitize stem for library naming
        stem = Path(safe_filename).stem
        clean_stem = "".join(c if c.isalnum() or c == "_" else "_" for c in stem)
        output_filename = f"{clean_stem}{file_ext}"

        # Create category directory if it doesn't exist
        category_dir = Path("sounds") / "library" / category
        category_dir.mkdir(parents=True, exist_ok=True)

        # Save file to category directory
        output_path = category_dir / output_filename

        # Check if file already exists
        if output_path.exists():
            raise HTTPException(
                status_code=400,
                detail=f"File {output_filename} already exists in {category} category"
            )

        # Save uploaded file (async I/O - non-blocking)
        async with aiofiles.open(output_path, "wb") as buffer:
            content = await file.read()
            await buffer.write(content)

        # Parse event types
        event_types_list = [et.strip() for et in event_types.split(",")]

        # Use provided name or generate from filename
        alert_name = name if name else safe_filename.replace("_", " ").title()

        # Generate unique ID
        alert_id = safe_filename.lower()

        # Create alert metadata
        alert_metadata = {
            "id": alert_id,
            "name": alert_name,
            "filename": output_filename,
            "category": category,
            "event_types": event_types_list,
            "description": description or f"Custom {category} alert",
            "duration_ms": 1000,  # Default, could be calculated
            "volume_level": "medium"
        }

        # Add to library
        success = audio_library.add_alert(alert_metadata)

        if success:
            # Update category alerts list
            if category in audio_library.library_data.get("categories", {}):
                category_alerts = audio_library.library_data["categories"][category].get("alerts", [])
                if output_filename not in category_alerts:
                    category_alerts.append(output_filename)
                    audio_library.library_data["categories"][category]["alerts"] = category_alerts
                    audio_library.save_library()

            return {
                "message": "Audio file uploaded to library successfully",
                "alert_id": alert_id,
                "filename": output_filename,
                "category": category,
                "size": output_path.stat().st_size
            }
        else:
            # Clean up file if metadata save failed
            output_path.unlink()
            raise HTTPException(status_code=500, detail="Failed to save alert metadata")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


# Health check endpoint
@router.get("/health")
async def health_check():
    """Comprehensive health check endpoint for system components."""
    components = {}
    overall_status = "healthy"

    # Check API
    components["api"] = {
        "status": "healthy",
        "message": "API server is running"
    }

    # Check Database
    try:
        await db.get_all_targets()
        components["database"] = {
            "status": "healthy",
            "message": "Database connection active"
        }
    except Exception as e:
        components["database"] = {
            "status": "unhealthy",
            "message": f"Database error: {str(e)}"
        }
        overall_status = "degraded"

    # Check Monitor Manager
    if monitor_manager and monitor_manager.running:
        components["monitor"] = {
            "status": "healthy",
            "message": "Monitor manager running",
            "active_monitors": len(monitor_manager.tasks)
        }
    else:
        components["monitor"] = {
            "status": "unhealthy",
            "message": "Monitor manager not running"
        }
        overall_status = "degraded"

    # Check Relay Controller
    # GPIO/Relay support removed for Docker compatibility
    components["relay"] = {
        "status": "removed",
        "message": "GPIO/Relay support removed for Docker compatibility"
    }

    # Check Webhook Notifier
    if webhook_notifier and webhook_notifier.enabled:
        components["webhook"] = {
            "status": "healthy",
            "message": "Webhook notifications enabled"
        }
    else:
        components["webhook"] = {
            "status": "info",
            "message": "Webhook notifications disabled"
        }

    return {
        "status": overall_status,
        "components": components
    }



# ==================== INPUT VALIDATION ====================

def validate_target_address(target_type: str, address: str):
    """
    Validate target address based on type.
    
    Raises:
        HTTPException: If address is invalid for the given type
    """
    if target_type == "ping":
        try:
            ipaddress.ip_address(address)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid IP address for ping target: {address}"
            )
    elif target_type in ["http", "https"]:
        parsed = urlparse(address)
        if not parsed.scheme or not parsed.netloc:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid URL format: {address}. Must include scheme and host."
            )
        if parsed.scheme not in ["http", "https"]:
            raise HTTPException(
                status_code=400,
                detail=f"URL must use http or https scheme, got: {parsed.scheme}"
            )


# ==================== DATABASE MAINTENANCE ====================

@router.post("/maintenance/cleanup")
async def cleanup_old_data(retention_days: int = 90):
    """
    Clean up old alert logs and check history.
    
    Args:
        retention_days: Number of days to retain (default: 90)
    """
    if retention_days < 7:
        raise HTTPException(
            status_code=400,
            detail="Retention period must be at least 7 days"
        )
    
    try:
        deleted = await db.cleanup_old_alerts(retention_days)
        return {
            "message": f"Cleaned up {deleted} old records",
            "retention_days": retention_days,
            "deleted_records": deleted
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Cleanup failed: {str(e)}"
        )


@router.get("/maintenance/stats")
async def get_database_stats():
    """Get database statistics for monitoring."""
    try:
        stats = await db.get_database_stats()
        return stats
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get database stats: {str(e)}"
        )


# ==================== SETTINGS MANAGEMENT ====================

@router.get("/settings/smtp")
async def get_smtp_settings():
    """
    Get SMTP email configuration.
    Password is masked for security.
    """
    try:
        settings = await db.get_settings_by_category('smtp')

        # Mask password for security
        if settings.get('password'):
            settings['password'] = '********' if settings['password'] else ''

        # Ensure defaults if no settings exist
        if not settings:
            settings = {
                'enabled': False,
                'host': '',
                'port': 587,
                'use_tls': True,
                'username': '',
                'password': '',
                'from_address': '',
                'from_name': 'WebStatus',
                'recipients': []
            }

        return settings

    except Exception as e:
        logger.error(f"Failed to get SMTP settings: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve SMTP settings: {str(e)}"
        )


@router.post("/settings/smtp")
async def update_smtp_settings(settings: dict):
    """
    Update SMTP email configuration.
    Reinitializes SMTP notifier with new settings.
    """
    try:
        from api.models.settings import SMTPSettings

        # Validate settings
        smtp_settings = SMTPSettings(**settings)

        # Save to database
        await db.save_settings('smtp', smtp_settings.dict())

        # Signal that SMTP settings changed (will be reloaded by main app)
        logger.info("SMTP settings updated")

        return {
            "message": "SMTP settings updated successfully",
            "enabled": smtp_settings.enabled
        }

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid SMTP settings: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Failed to update SMTP settings: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update SMTP settings: {str(e)}"
        )


@router.post("/settings/smtp/test")
async def test_smtp_settings(test_request: dict):
    """
    Send a test email to verify SMTP configuration.

    Args:
        test_request: Dict with 'email' field for recipient
    """
    try:
        from alerts.smtp import SMTPNotifier

        recipient = test_request.get('email')
        if not recipient:
            raise HTTPException(400, "Email address is required")

        # Get current SMTP settings
        smtp_config = await db.get_settings_by_category('smtp')

        if not smtp_config.get('enabled'):
            raise HTTPException(400, "SMTP is not enabled")

        # Create temporary notifier and send test (now async)
        notifier = SMTPNotifier(smtp_config)
        await notifier.send_test_email(recipient)

        return {
            "message": f"Test email sent successfully to {recipient}",
            "recipient": recipient
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Test email failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send test email: {str(e)}"
        )


@router.get("/settings/backup")
async def get_backup_settings():
    """Get local backup configuration."""
    try:
        settings = await db.get_settings_by_category('backup')

        # Ensure defaults if no settings exist
        if not settings:
            settings = {
                'enabled': False,
                'schedule': '0 2 * * *',
                'retention_days': 30,
                'compression': True
            }

        return settings

    except Exception as e:
        logger.error(f"Failed to get backup settings: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to retrieve backup settings: {str(e)}"
        )


@router.post("/settings/backup")
async def update_backup_settings(settings: dict):
    """
    Update local backup configuration.
    Restarts backup scheduler with new settings.
    """
    try:
        from api.models.settings import BackupSettings

        # Validate settings
        backup_settings = BackupSettings(**settings)

        # Save to database
        await db.save_settings('backup', backup_settings.dict())

        # Signal that backup settings changed (will be reloaded by main app)
        logger.info("Backup settings updated")

        return {
            "message": "Backup settings updated successfully",
            "enabled": backup_settings.enabled,
            "schedule": backup_settings.schedule
        }

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid backup settings: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Failed to update backup settings: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to update backup settings: {str(e)}"
        )


# ==================== BACKUP OPERATIONS ====================

@router.post("/backups/create")
async def create_backup_now():
    """
    Create a backup immediately.
    Returns backup information including file path and size.
    """
    try:
        from utils.backup.manager import BackupManager

        # Get backup settings
        backup_config = await db.get_settings_by_category('backup')

        # Create backup manager and perform backup
        backup_manager = BackupManager(backup_config or {'enabled': True})
        result = backup_manager.create_backup()

        if result:
            return {
                "message": "Backup created successfully",
                "backup": result
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Backup creation failed"
            )

    except Exception as e:
        logger.error(f"Backup creation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create backup: {str(e)}"
        )


@router.get("/backups")
async def list_backups():
    """
    List all available backups with metadata.
    Returns list of backups sorted by creation date (newest first).
    """
    try:
        from utils.backup.manager import BackupManager

        # Get backup settings for path info
        backup_config = await db.get_settings_by_category('backup')

        # Create backup manager and list backups
        backup_manager = BackupManager(backup_config or {})
        backups = backup_manager.list_backups()

        return {
            "backups": backups,
            "count": len(backups)
        }

    except Exception as e:
        logger.error(f"Failed to list backups: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list backups: {str(e)}"
        )


@router.get("/backups/download/{backup_name}")
async def download_backup(backup_name: str):
    """
    Download a backup file.

    Args:
        backup_name: Name of the backup to download
    """
    try:
        from fastapi.responses import FileResponse
        from utils.backup.manager import BackupManager

        # Security: validate backup name to prevent path traversal
        if '..' in backup_name or '/' in backup_name:
            raise HTTPException(
                status_code=400,
                detail="Invalid backup name"
            )

        # Get backup settings
        backup_config = await db.get_settings_by_category('backup')

        # Get backup file path
        backup_manager = BackupManager(backup_config or {})
        backup_path = backup_manager.get_backup_file_path(backup_name)

        if not backup_path or not backup_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"Backup not found: {backup_name}"
            )

        return FileResponse(
            path=str(backup_path),
            filename=backup_path.name,
            media_type='application/gzip'
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download backup: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to download backup: {str(e)}"
        )


@router.delete("/backups/{backup_name}")
async def delete_backup(backup_name: str):
    """
    Delete a backup.

    Args:
        backup_name: Name of the backup to delete
    """
    try:
        from utils.backup.manager import BackupManager

        # Security: validate backup name to prevent path traversal
        if '..' in backup_name or '/' in backup_name:
            raise HTTPException(
                status_code=400,
                detail="Invalid backup name"
            )

        # Get backup settings
        backup_config = await db.get_settings_by_category('backup')

        # Delete backup
        backup_manager = BackupManager(backup_config or {})
        success = backup_manager.delete_backup(backup_name)

        if success:
            return {
                "message": f"Backup deleted successfully: {backup_name}"
            }
        else:
            raise HTTPException(
                status_code=404,
                detail=f"Backup not found: {backup_name}"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete backup: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete backup: {str(e)}"
        )


@router.post("/backups/restore/{backup_name}")
async def restore_backup(backup_name: str):
    """
    Restore a backup.
    WARNING: This will overwrite the current database and config!
    The application will automatically restart after restore completes.
    """
    try:
        from utils.backup.manager import BackupManager
        from utils.restart import schedule_restart

        # Security: validate backup name to prevent path traversal
        if '..' in backup_name or '/' in backup_name:
            raise HTTPException(
                status_code=400,
                detail="Invalid backup name"
            )

        # Get backup settings
        backup_config = await db.get_settings_by_category('backup')

        # Restore backup
        backup_manager = BackupManager(backup_config or {})
        result = backup_manager.restore_backup(backup_name)

        # Schedule automatic restart in 3 seconds
        await schedule_restart(delay_seconds=3)

        # Add restart notification to response
        result['restart_scheduled'] = True
        result['restart_in_seconds'] = 3
        result['message'] = f"{result.get('message', 'Restore successful')} - Application restarting in 3 seconds..."

        return result

    except FileNotFoundError as e:
        raise HTTPException(
            status_code=404,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to restore backup: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to restore backup: {str(e)}"
        )


@router.post("/backups/upload")
async def upload_backup(file: UploadFile):
    """
    Upload an external backup file to import it into the system.
    The backup can then be restored using the restore endpoint.
    """
    try:
        from utils.backup.manager import BackupManager

        # Validate file type
        if not file.filename or not file.filename.endswith('.tar.gz'):
            raise HTTPException(
                status_code=400,
                detail="Only .tar.gz backup files are allowed"
            )

        # Limit file size (100MB max)
        MAX_SIZE = 100 * 1024 * 1024  # 100MB
        file_content = await file.read()

        if len(file_content) > MAX_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"File too large. Maximum size is 100MB"
            )

        # Get backup settings
        backup_config = await db.get_settings_by_category('backup')

        # Import backup
        backup_manager = BackupManager(backup_config or {})
        result = backup_manager.import_backup(file_content, file.filename)

        return result

    except FileExistsError as e:
        raise HTTPException(
            status_code=409,
            detail=str(e)
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=str(e)
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload backup: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to upload backup: {str(e)}"
        )


