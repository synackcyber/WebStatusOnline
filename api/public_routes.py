"""
Public API routes for token-based status page sharing.
No authentication required for public endpoints - token validation only.
"""
from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from typing import Dict, Any, List, Optional
import secrets
import logging
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import time

from database.db import db
from utils.time_utils import calculate_uptime_percentage

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="web/templates")

# Rate limiting: Simple in-memory rate limiter
# Structure: {token: {timestamp: count}}
_rate_limit_store: Dict[str, Dict[int, int]] = defaultdict(lambda: defaultdict(int))
RATE_LIMIT_REQUESTS = 60  # requests per minute
RATE_LIMIT_WINDOW = 60  # seconds


def check_rate_limit(token: str) -> bool:
    """
    Check if token has exceeded rate limit.
    Returns True if within limit, False if exceeded.
    """
    current_time = int(time.time())
    current_minute = current_time // RATE_LIMIT_WINDOW

    # Clean up old entries (older than 2 minutes)
    old_minutes = [m for m in _rate_limit_store[token] if m < current_minute - 1]
    for old_minute in old_minutes:
        del _rate_limit_store[token][old_minute]

    # Check current minute count
    if _rate_limit_store[token][current_minute] >= RATE_LIMIT_REQUESTS:
        return False

    # Increment counter
    _rate_limit_store[token][current_minute] += 1
    return True


# ============================================================================
# PUBLIC ENDPOINTS (No authentication required)
# ============================================================================

@router.get("/public/{token}", response_class=HTMLResponse)
async def public_status_page(request: Request, token: str):
    """
    Serve public status page HTML for a valid token.
    This page auto-refreshes and displays only public targets.
    """
    try:
        # Validate token format
        if not token or len(token) < 20:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invalid status page"
            )

        # Check rate limit
        if not check_rate_limit(token):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please try again later."
            )

        # Validate token exists and is enabled
        token_data = await db.get_public_token(token)
        if not token_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invalid status page"
            )

        if not token_data.get('enabled', 0):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This status page has been disabled"
            )

        # Track access
        await db.update_token_access(token)

        # Get public targets to check if any exist
        public_targets = await db.get_public_targets()

        # Render template with token and no-index meta tag
        response = templates.TemplateResponse(
            "status.html",
            {
                "request": request,
                "token": token,
                "token_name": token_data.get('name', 'System Status'),
                "has_targets": len(public_targets) > 0,
                "view_mode": token_data.get('view_mode', 'both')
            }
        )

        # Add no-index header for privacy
        response.headers["X-Robots-Tag"] = "noindex, nofollow"

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving public status page: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to load status page"
        )


@router.get("/api/v1/public/{token}/status")
async def get_public_status(token: str) -> Dict[str, Any]:
    """
    Public API endpoint - Returns filtered status data for public targets.
    Only exposes safe information, no credentials or internal details.
    """
    try:
        # Validate token format
        if not token or len(token) < 20:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invalid token"
            )

        # Check rate limit
        if not check_rate_limit(token):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please try again later."
            )

        # Validate token exists and is enabled
        token_data = await db.get_public_token(token)
        if not token_data or not token_data.get('enabled', 0):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invalid token"
            )

        # Track access
        await db.update_token_access(token)

        # Get public targets
        public_targets = await db.get_public_targets()

        # Calculate uptime for each target
        services = []
        all_up = True

        for target in public_targets:
            target_id = target.get('id')

            # Calculate uptime percentage from target's total stats
            total_uptime = target.get('total_uptime', 0)
            total_downtime = target.get('total_downtime', 0)

            # Get current duration if in down state
            current_duration = 0
            if target.get('status') == 'down' and target.get('last_status_change'):
                last_change = datetime.fromisoformat(target['last_status_change'].replace('Z', '+00:00'))
                current_duration = (datetime.now(last_change.tzinfo) - last_change).total_seconds()

            # Calculate uptime percentage
            uptime_pct = calculate_uptime_percentage(
                total_uptime,
                total_downtime,
                current_duration,
                target.get('status', 'unknown')
            )

            # Determine current status
            current_status = target.get('status', 'unknown')
            if current_status != 'up':
                all_up = False

            # Build safe service object (only public-safe fields)
            service = {
                'id': target_id,
                'name': target.get('public_name') or target.get('name', 'Unknown Service'),
                'status': current_status,
                'uptime_percentage': round(uptime_pct, 2),
                'last_status_change': target.get('last_status_change'),
                'last_checked': target.get('last_checked')
            }

            services.append(service)

        # Sort by name
        services.sort(key=lambda s: s['name'].lower())

        # Calculate overall status
        overall_status = 'operational' if all_up else 'partial_outage'
        if not services:
            overall_status = 'no_data'
        elif all(s['status'] == 'down' for s in services):
            overall_status = 'major_outage'

        return {
            'overall_status': overall_status,
            'services': services,
            'last_updated': datetime.now(timezone.utc).isoformat(),
            'service_count': len(services)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching public status: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch status"
        )


# ============================================================================
# ADMIN ENDPOINTS (Requires authentication - to be added to main routes)
# ============================================================================

@router.post("/api/v1/sharing/tokens")
async def generate_public_token(request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate a new public access token.
    Request body: { "name": "Optional token name", "view_mode": "both|timeline|cards" }
    """
    try:
        token_name = request.get('name', '').strip()
        view_mode = request.get('view_mode', 'both').strip().lower()

        # Validate view_mode
        if view_mode not in ['both', 'timeline', 'cards']:
            view_mode = 'both'

        # Generate cryptographically secure random token
        token = secrets.token_urlsafe(32)

        # Create token in database
        token_data = await db.create_public_token(token, token_name or None, view_mode)

        logger.info(f"Generated new public token: {token_name or 'Unnamed'} (view_mode: {view_mode})")

        return {
            'success': True,
            'token': token_data['token'],
            'name': token_data['name'],
            'view_mode': token_data['view_mode'],
            'url': f"/public/{token}",
            'created_at': token_data['created_at']
        }

    except Exception as e:
        logger.error(f"Error generating token: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate token"
        )


@router.get("/api/v1/sharing/tokens")
async def list_public_tokens() -> Dict[str, Any]:
    """
    List all public tokens with their metadata.
    """
    try:
        tokens = await db.get_all_public_tokens()

        # Add full URL to each token
        for token in tokens:
            token['url'] = f"/public/{token['token']}"

        return {
            'success': True,
            'tokens': tokens,
            'count': len(tokens)
        }

    except Exception as e:
        logger.error(f"Error listing tokens: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve tokens"
        )


@router.patch("/api/v1/sharing/tokens/{token}")
async def update_token(token: str, request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update token properties.
    Request body: { "enabled": true/false, "name": "...", "view_mode": "..." }
    """
    try:
        # Handle enabled toggle
        if 'enabled' in request:
            enabled = request.get('enabled')
            enabled_int = 1 if enabled else 0
            success = await db.toggle_token_enabled(token, enabled_int)

            if not success:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Token not found"
                )

            action = "enabled" if enabled else "disabled"
            logger.info(f"Token {action}: {token[:8]}...")

            return {
                'success': True,
                'token': token,
                'enabled': enabled,
                'message': f"Token {action} successfully"
            }

        # Handle name/view_mode update
        if 'name' in request or 'view_mode' in request:
            name = request.get('name')
            view_mode = request.get('view_mode')

            success = await db.update_token_details(token, name, view_mode)

            if not success:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Token not found"
                )

            logger.info(f"Token updated: {token[:8]}... (name: {name}, view_mode: {view_mode})")

            return {
                'success': True,
                'token': token,
                'message': "Token updated successfully"
            }

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No valid fields provided for update"
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error toggling token: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update token"
        )


@router.delete("/api/v1/sharing/tokens/{token}")
async def revoke_token(token: str) -> Dict[str, Any]:
    """
    Permanently delete a public token.
    This action cannot be undone.
    """
    try:
        success = await db.delete_public_token(token)

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Token not found"
            )

        logger.info(f"Token revoked: {token[:8]}...")

        return {
            'success': True,
            'message': "Token revoked successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error revoking token: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to revoke token"
        )


@router.patch("/api/v1/targets/{target_id}/visibility")
async def update_target_visibility(target_id: str, request: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update target's public visibility and public name.
    Request body: { "public_visible": true/false, "public_name": "Display Name" }
    """
    try:
        public_visible = request.get('public_visible')
        public_name = request.get('public_name') or ''

        # Handle None or empty string
        if isinstance(public_name, str):
            public_name = public_name.strip()
        else:
            public_name = ''

        if public_visible is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="'public_visible' field is required"
            )

        # Convert to integer (SQLite stores as INTEGER)
        visible_int = 1 if public_visible else 0

        # Use None if public_name is empty
        public_name_value = public_name if public_name else None

        success = await db.update_target_visibility(
            target_id,
            visible_int,
            public_name_value
        )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Target not found"
            )

        visibility = "visible" if public_visible else "hidden"
        logger.info(f"Target {target_id} set to {visibility} with public name: {public_name_value}")

        return {
            'success': True,
            'target_id': target_id,
            'public_visible': public_visible,
            'public_name': public_name_value,
            'message': f"Target visibility updated to {visibility}"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating target visibility: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update target visibility"
        )


@router.get("/public/{token}/dashboard", response_class=HTMLResponse)
async def public_dashboard_page(request: Request, token: str):
    """
    Serve public dashboard page HTML for a valid token.
    Provides Dashboard and Timeline views as alternatives to the simple status page.
    """
    try:
        # Validate token format
        if not token or len(token) < 20:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invalid dashboard page"
            )

        # Check rate limit
        if not check_rate_limit(token):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please try again later."
            )

        # Validate token exists and is enabled
        token_data = await db.get_public_token(token)
        if not token_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invalid dashboard page"
            )

        if not token_data.get('enabled', 0):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="This dashboard page has been disabled"
            )

        # Track access
        await db.update_token_access(token)

        # Get public targets to check if any exist
        public_targets = await db.get_public_targets()

        # Render template with token and no-index meta tag
        response = templates.TemplateResponse(
            "public_dashboard.html",
            {
                "request": request,
                "token": token,
                "token_name": token_data.get('name', 'System Status'),
                "has_targets": len(public_targets) > 0
            }
        )

        # Add no-index header for privacy
        response.headers["X-Robots-Tag"] = "noindex, nofollow"

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error serving public dashboard page: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to load dashboard page"
        )


def aggregate_history_into_buckets(history_records: List[Dict], start_time: datetime, end_time: datetime, bucket_minutes: int) -> List[Dict]:
    """
    Aggregate history records into time buckets for cleaner visualization.

    Args:
        history_records: List of history records with timestamp and status
        start_time: Start of time range
        end_time: End of time range
        bucket_minutes: Size of each bucket in minutes

    Returns:
        List of bucketed history points with aggregated status
    """
    if not history_records:
        return []

    # Create time buckets
    buckets = []
    current_bucket_start = start_time

    while current_bucket_start < end_time:
        bucket_end = min(current_bucket_start + timedelta(minutes=bucket_minutes), end_time)
        buckets.append({
            'start': current_bucket_start,
            'end': bucket_end,
            'records': []
        })
        current_bucket_start = bucket_end

    # Assign records to buckets
    for record in history_records:
        try:
            record_time = datetime.fromisoformat(record['timestamp'].replace('Z', '+00:00'))
            if record_time.tzinfo is None:
                record_time = record_time.replace(tzinfo=start_time.tzinfo or None)

            # Find appropriate bucket
            for bucket in buckets:
                if bucket['start'] <= record_time < bucket['end']:
                    bucket['records'].append(record)
                    break
        except (ValueError, KeyError):
            continue

    # Aggregate bucket status (conservative: any down = bucket down)
    result = []
    for bucket in buckets:
        if not bucket['records']:
            # No data in this bucket - mark as unknown
            status = 'unknown'
        else:
            # If any record is down, mark bucket as down
            statuses = [r.get('status', 'unknown') for r in bucket['records']]
            if 'down' in statuses:
                status = 'down'
            elif 'up' in statuses:
                status = 'up'
            else:
                status = 'unknown'

        result.append({
            'timestamp': bucket['start'].isoformat(),
            'end_timestamp': bucket['end'].isoformat(),
            'status': status,
            'checks_count': len(bucket['records'])
        })

    return result


@router.get("/api/v1/public/{token}/incidents")
async def get_public_incidents(token: str, days: int = 7) -> Dict[str, Any]:
    """
    Public API endpoint - Returns recent incidents from the alert log.

    Query parameters:
    - days: Number of days to look back (default: 7, max: 90)

    Returns list of incidents with start time, duration, and status.
    """
    try:
        # Validate token format
        if not token or len(token) < 20:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invalid token"
            )

        # Check rate limit
        if not check_rate_limit(token):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please try again later."
            )

        # Validate token exists and is enabled
        token_data = await db.get_public_token(token)
        if not token_data or not token_data.get('enabled', 0):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invalid token"
            )

        # Track access
        await db.update_token_access(token)

        # Limit days parameter
        days = max(1, min(days, 90))

        # Calculate time range
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=days)

        # Get alert logs for public targets only
        public_targets = await db.get_public_targets()
        public_target_ids = {t['id'] for t in public_targets}

        # Get all recent alerts
        all_alerts = await db.get_alert_log(limit=1000)

        # Filter to public targets and time range, and build incident list
        # Process alerts in chronological order (oldest first) to properly pair incidents
        incidents_list = []
        current_incidents = {}  # Track ongoing incidents per target

        # Reverse the list to process oldest first
        for alert in reversed(all_alerts):
            # Skip if not a public target
            if alert['target_id'] not in public_target_ids:
                continue

            # Parse timestamp
            try:
                alert_time = datetime.fromisoformat(alert['timestamp'].replace('Z', '+00:00'))
                if alert_time.tzinfo is None:
                    alert_time = alert_time.replace(tzinfo=None)

                # Skip if outside time range
                if alert_time < cutoff_time:
                    continue
            except (ValueError, KeyError):
                continue

            # Get target name
            target = next((t for t in public_targets if t['id'] == alert['target_id']), None)
            if not target:
                continue

            target_name = target.get('public_name') or target.get('name', 'Unknown Service')
            target_id = alert['target_id']
            event_type = alert.get('event_type', '')

            if event_type == 'threshold_reached':
                # Check if target already has an ongoing incident
                if target_id not in current_incidents or current_incidents[target_id].get('resolved_at'):
                    # Start a new incident for this target
                    incident = {
                        'id': alert.get('id'),
                        'target_id': target_id,
                        'target_name': target_name,
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
        for incident in incidents_list:
            started_at = datetime.fromisoformat(incident['started_at'].replace('Z', '+00:00'))

            if incident['resolved_at']:
                resolved_at = datetime.fromisoformat(incident['resolved_at'].replace('Z', '+00:00'))
                duration_seconds = (resolved_at - started_at).total_seconds()
            else:
                # Still ongoing
                duration_seconds = (datetime.now(timezone.utc).replace(tzinfo=started_at.tzinfo) - started_at).total_seconds()
                incident['status'] = 'ongoing'

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
                'started_at': incident['started_at'],
                'resolved_at': incident['resolved_at'],
                'duration': duration_str,
                'status': incident['status']
            })

        return {
            'success': True,
            'incidents': formatted_incidents,
            'count': len(formatted_incidents),
            'days': days
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching public incidents: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch incidents"
        )


@router.get("/api/v1/public/{token}/history")
async def get_public_history(token: str, range: str = "24h") -> Dict[str, Any]:
    """
    Public API endpoint - Returns uptime history data for timeline visualization.

    Query parameters:
    - range: Time range (24h, 7d, 30d, 90d) - defaults to 24h

    Returns bucketed/aggregated data for cleaner pill-shaped visualizations.
    """
    try:
        # Validate token format
        if not token or len(token) < 20:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invalid token"
            )

        # Check rate limit
        if not check_rate_limit(token):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please try again later."
            )

        # Validate token exists and is enabled
        token_data = await db.get_public_token(token)
        if not token_data or not token_data.get('enabled', 0):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Invalid token"
            )

        # Track access
        await db.update_token_access(token)

        # Parse range parameter with adaptive bucket sizes
        range_config = {
            '24h': {'hours': 24, 'bucket_minutes': 30},    # 30-min buckets = ~48 pills
            '7d': {'hours': 168, 'bucket_minutes': 240},   # 4-hour buckets = ~42 pills
            '30d': {'hours': 720, 'bucket_minutes': 720},  # 12-hour buckets = ~60 pills
            '90d': {'hours': 2160, 'bucket_minutes': 2880} # 2-day buckets = ~45 pills
        }
        config = range_config.get(range, range_config['24h'])
        hours = config['hours']
        bucket_minutes = config['bucket_minutes']

        # Calculate time range (database timestamps are in UTC format)
        end_time = datetime.now(timezone.utc)
        start_time = end_time - timedelta(hours=hours)

        # Get public targets
        public_targets = await db.get_public_targets()

        # Build history data for each target
        targets_history = []

        for target in public_targets:
            target_id = target.get('id')
            target_name = target.get('public_name') or target.get('name', 'Unknown Service')

            # Get uptime history from database
            history_records = await db.get_target_history(
                target_id,
                start_time.isoformat(),
                end_time.isoformat()
            )

            # Calculate uptime percentage
            total_uptime = target.get('total_uptime', 0)
            total_downtime = target.get('total_downtime', 0)
            current_duration = 0

            if target.get('status') == 'down' and target.get('last_status_change'):
                last_change = datetime.fromisoformat(target['last_status_change'].replace('Z', '+00:00'))
                current_duration = (datetime.now(last_change.tzinfo) - last_change).total_seconds()

            # Calculate uptime percentage
            uptime_pct = calculate_uptime_percentage(
                total_uptime,
                total_downtime,
                current_duration,
                target.get('status', 'unknown')
            )

            # Aggregate history into time buckets for cleaner visualization
            bucketed_history = aggregate_history_into_buckets(
                history_records,
                start_time,
                end_time,
                bucket_minutes
            )

            targets_history.append({
                'id': target_id,
                'name': target_name,
                'uptime_percentage': round(uptime_pct, 2),
                'history': bucketed_history
            })

        # Sort by name
        targets_history.sort(key=lambda t: t['name'].lower())

        return {
            'success': True,
            'range': range,
            'start_time': start_time.isoformat(),
            'end_time': end_time.isoformat(),
            'targets': targets_history,
            'count': len(targets_history)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching public history: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unable to fetch history data"
        )
