"""
Utility functions for time calculations and formatting.
"""
from datetime import datetime, timezone
from typing import Tuple


def format_duration(seconds: int) -> str:
    """
    Format a duration in seconds to a human-readable string.
    Handles short durations (seconds/minutes) up to very long durations (years).

    Examples:
        - 45 seconds -> "45s"
        - 90 seconds -> "1m 30s"
        - 3661 seconds -> "1h 1m"
        - 86400 seconds -> "1d"
        - 31536000 seconds -> "1y"
        - 63158400 seconds -> "2y 1mo"
    """
    if seconds == 0:
        return "0s"

    if seconds < 60:
        return f"{seconds}s"

    minutes = seconds // 60
    remaining_seconds = seconds % 60

    if minutes < 60:
        if remaining_seconds > 0:
            return f"{minutes}m {remaining_seconds}s"
        return f"{minutes}m"

    hours = minutes // 60
    remaining_minutes = minutes % 60

    if hours < 24:
        if remaining_minutes > 0:
            return f"{hours}h {remaining_minutes}m"
        return f"{hours}h"

    days = hours // 24
    remaining_hours = hours % 24

    if days < 30:
        if remaining_hours > 0:
            return f"{days}d {remaining_hours}h"
        return f"{days}d"

    # For longer durations, use months and years
    months = days // 30
    remaining_days = days % 30

    if months < 12:
        if remaining_days > 0:
            return f"{months}mo {remaining_days}d"
        return f"{months}mo"

    years = months // 12
    remaining_months = months % 12

    if remaining_months > 0:
        return f"{years}y {remaining_months}mo"
    return f"{years}y"


def calculate_current_duration(last_status_change: str, status: str) -> Tuple[int, str]:
    """
    Calculate how long the target has been in its current status.

    Args:
        last_status_change: ISO format timestamp of last status change
        status: Current status ('up' or 'down')

    Returns:
        Tuple of (duration_seconds, formatted_string)
    """
    if not last_status_change:
        return 0, "0s"

    try:
        last_change = datetime.fromisoformat(last_status_change)
        # Remove timezone info to compare with naive datetime
        if last_change.tzinfo is not None:
            last_change = last_change.replace(tzinfo=None)

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        duration_seconds = int((now - last_change).total_seconds())

        # Handle negative durations (clock skew)
        if duration_seconds < 0:
            duration_seconds = 0

        formatted = format_duration(duration_seconds)
        return duration_seconds, formatted
    except Exception as e:
        # Return 0 on any error
        return 0, "0s"


def calculate_uptime_percentage(total_uptime: int, total_downtime: int,
                                current_duration: int, current_status: str) -> float:
    """
    Calculate the uptime percentage including current status duration.

    Args:
        total_uptime: Total accumulated uptime in seconds
        total_downtime: Total accumulated downtime in seconds
        current_duration: How long in current status (seconds)
        current_status: Current status ('up' or 'down')

    Returns:
        Uptime percentage (0-100)
    """
    # Add current duration to appropriate total
    if current_status == 'up':
        total_up = total_uptime + current_duration
        total_down = total_downtime
    elif current_status == 'down':
        total_up = total_uptime
        total_down = total_downtime + current_duration
    else:
        total_up = total_uptime
        total_down = total_downtime

    total_time = total_up + total_down

    if total_time == 0:
        return 100.0  # No data means assume 100% uptime

    return round((total_up / total_time) * 100, 2)
