"""
Pydantic models for authentication API requests and responses.
"""
from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import datetime


class SetupRequest(BaseModel):
    """Request model for initial setup."""
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=8, max_length=128)

    @field_validator('username')
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Validate username format."""
        if not v.replace('_', '').replace('-', '').isalnum():
            raise ValueError('Username can only contain letters, numbers, hyphens, and underscores')
        return v.lower()


class LoginRequest(BaseModel):
    """Request model for login."""
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class LoginResponse(BaseModel):
    """Response model for successful login."""
    success: bool
    message: str
    user: Optional[dict] = None


class LogoutResponse(BaseModel):
    """Response model for logout."""
    success: bool
    message: str


class StatusResponse(BaseModel):
    """Response model for authentication status."""
    authenticated: bool
    setup_required: bool
    user: Optional[dict] = None


class ErrorResponse(BaseModel):
    """Response model for errors."""
    success: bool = False
    message: str
    code: Optional[str] = None
