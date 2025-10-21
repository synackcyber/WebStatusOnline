"""
Simple in-memory rate limiter for API endpoints.
Uses a sliding window approach to track request counts.
"""
import time
from collections import defaultdict
from typing import Dict, Tuple
import logging

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    In-memory rate limiter using sliding window algorithm.

    Thread-safe for async operations within a single process.
    For multi-process deployments, consider Redis-based rate limiting.
    """

    def __init__(self):
        # Structure: {key: [(timestamp, count), ...]}
        self._requests: Dict[str, list] = defaultdict(list)
        self._cleanup_interval = 300  # Clean up old entries every 5 minutes
        self._last_cleanup = time.time()

    def is_allowed(
        self,
        identifier: str,
        max_requests: int,
        window_seconds: int
    ) -> Tuple[bool, dict]:
        """
        Check if a request is allowed based on rate limit.

        Args:
            identifier: Unique identifier (IP address, API key, user ID, etc.)
            max_requests: Maximum number of requests allowed
            window_seconds: Time window in seconds

        Returns:
            Tuple of (allowed: bool, info: dict)
            info contains: {
                'allowed': bool,
                'current_count': int,
                'limit': int,
                'window': int,
                'retry_after': int (seconds until limit resets, only if blocked)
            }
        """
        current_time = time.time()
        window_start = current_time - window_seconds

        # Clean up old requests for this identifier
        if identifier in self._requests:
            self._requests[identifier] = [
                ts for ts in self._requests[identifier]
                if ts > window_start
            ]

        # Count recent requests
        request_count = len(self._requests[identifier])

        # Check if allowed
        allowed = request_count < max_requests

        # Build response info
        info = {
            'allowed': allowed,
            'current_count': request_count,
            'limit': max_requests,
            'window': window_seconds
        }

        if allowed:
            # Add this request to the log
            self._requests[identifier].append(current_time)
            info['current_count'] += 1
        else:
            # Calculate retry_after (when oldest request falls out of window)
            if self._requests[identifier]:
                oldest_request = self._requests[identifier][0]
                info['retry_after'] = int(oldest_request + window_seconds - current_time) + 1
            else:
                info['retry_after'] = window_seconds

        # Periodic cleanup
        self._maybe_cleanup()

        return allowed, info

    def _maybe_cleanup(self):
        """Remove expired entries to prevent memory bloat."""
        current_time = time.time()

        if current_time - self._last_cleanup > self._cleanup_interval:
            # Remove identifiers with no recent requests (last 1 hour)
            cutoff = current_time - 3600
            identifiers_to_remove = [
                identifier for identifier, requests in self._requests.items()
                if not requests or (requests and all(ts < cutoff for ts in requests))
            ]

            for identifier in identifiers_to_remove:
                del self._requests[identifier]

            self._last_cleanup = current_time

            if identifiers_to_remove:
                logger.debug(f"Rate limiter cleanup: removed {len(identifiers_to_remove)} expired identifiers")

    def reset(self, identifier: str):
        """Reset rate limit for a specific identifier."""
        if identifier in self._requests:
            del self._requests[identifier]

    def get_stats(self) -> dict:
        """Get current rate limiter statistics."""
        return {
            'active_identifiers': len(self._requests),
            'total_requests_tracked': sum(len(reqs) for reqs in self._requests.values()),
            'last_cleanup': self._last_cleanup
        }


# Global rate limiter instance
rate_limiter = RateLimiter()
