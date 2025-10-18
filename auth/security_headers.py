"""
Security headers middleware for FastAPI.

Adds security headers to all responses to protect against common attacks.
"""
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Callable


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware to add security headers to responses."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Add security headers to response.

        Args:
            request: FastAPI request
            call_next: Next middleware/route handler

        Returns:
            Response with security headers
        """
        response = await call_next(request)

        # Prevent clickjacking attacks
        response.headers["X-Frame-Options"] = "DENY"

        # Enable XSS protection
        response.headers["X-Content-Type-Options"] = "nosniff"

        # Disable browser MIME type sniffing
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # Content Security Policy
        # Note: Adjust this based on your actual needs
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data: https:; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "media-src 'self'; "
            "object-src 'none'; "
            "frame-ancestors 'none';"
        )

        # Referrer Policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # Permissions Policy (formerly Feature Policy)
        response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"

        return response
