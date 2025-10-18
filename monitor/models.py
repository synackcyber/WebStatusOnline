"""
Data models for monitoring targets.
"""
from pydantic import BaseModel, Field, validator
from typing import Optional, Literal, Dict, Any
from datetime import datetime, timezone
import uuid


class Target(BaseModel):
    """Target monitoring configuration."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = Field(..., min_length=1, max_length=100)
    type: Literal['ping', 'http', 'https']
    address: str = Field(..., min_length=1)
    device_type: str = Field(default='other')
    check_interval: int = Field(default=60, ge=10, le=3600)
    failure_threshold: int = Field(default=3, ge=1, le=10)
    current_failures: int = Field(default=0, ge=0)
    status: Literal['up', 'down', 'unknown'] = 'unknown'
    last_check: Optional[str] = None
    last_status_change: Optional[str] = None
    total_checks: int = Field(default=0, ge=0)
    failed_checks: int = Field(default=0, ge=0)
    enabled: bool = True
    audio_behavior: Literal['urgent', 'normal', 'silent'] = 'normal'
    audio_down_alert: Optional[str] = None  # Custom sound file for down alerts
    audio_up_alert: Optional[str] = None  # Custom sound file for recovery alerts
    acknowledged: bool = False
    acknowledged_at: Optional[str] = None
    total_uptime: int = Field(default=0, ge=0)  # Total uptime in seconds
    total_downtime: int = Field(default=0, ge=0)  # Total downtime in seconds

    @validator('address')
    def validate_address(cls, v, values):
        """Validate address format based on type."""
        # Trim whitespace from address
        v = v.strip() if v else v

        if not v:
            raise ValueError('Address cannot be empty')

        target_type = values.get('type')

        if target_type == 'ping':
            # For ping, allow IP addresses or hostnames
            # Basic validation - can be enhanced
            if len(v) < 1:
                raise ValueError('Invalid ping address')

        elif target_type in ['http', 'https']:
            # For HTTP/HTTPS, ensure it looks like a URL
            if not (v.startswith('http://') or v.startswith('https://')):
                # Auto-prepend protocol if missing
                protocol = 'https://' if target_type == 'https' else 'http://'
                return protocol + v

        return v

    class Config:
        json_schema_extra = {
            "example": {
                "name": "Production Server",
                "type": "ping",
                "address": "192.168.1.100",
                "check_interval": 60,
                "failure_threshold": 3,
                "enabled": True
            }
        }


class TargetCreate(BaseModel):
    """Model for creating a new target."""
    name: str = Field(..., min_length=1, max_length=100)
    type: Literal['ping', 'http', 'https']
    address: str = Field(..., min_length=1)
    device_type: Optional[str] = Field(default='other')
    check_interval: Optional[int] = Field(default=60, ge=10, le=3600)
    failure_threshold: Optional[int] = Field(default=3, ge=1, le=10)
    enabled: Optional[bool] = True
    audio_behavior: Optional[Literal['urgent', 'normal', 'silent']] = 'normal'
    audio_down_alert: Optional[str] = None
    audio_up_alert: Optional[str] = None

    @validator('address')
    def validate_address(cls, v, values):
        """Validate address format based on type."""
        # Trim whitespace from address
        v = v.strip() if v else v

        if not v:
            raise ValueError('Address cannot be empty')

        target_type = values.get('type')

        if target_type in ['http', 'https']:
            # For HTTP/HTTPS, ensure it looks like a URL
            if not (v.startswith('http://') or v.startswith('https://')):
                # Auto-prepend protocol if missing
                protocol = 'https://' if target_type == 'https' else 'http://'
                return protocol + v

        return v


class TargetUpdate(BaseModel):
    """Model for updating a target."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    type: Optional[Literal['ping', 'http', 'https']] = None
    address: Optional[str] = Field(None, min_length=1)
    device_type: Optional[str] = None
    check_interval: Optional[int] = Field(None, ge=10, le=3600)
    failure_threshold: Optional[int] = Field(None, ge=1, le=10)
    enabled: Optional[bool] = None
    audio_behavior: Optional[Literal['urgent', 'normal', 'silent']] = None
    audio_down_alert: Optional[str] = None
    audio_up_alert: Optional[str] = None

    @validator('address')
    def validate_address(cls, v):
        """Trim whitespace from address."""
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError('Address cannot be empty')
        return v


class CheckResult(BaseModel):
    """Result of a monitoring check."""
    target_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: Literal['up', 'down']
    response_time: Optional[float] = None  # in seconds
    error_message: Optional[str] = None


class AlertEvent(BaseModel):
    """Alert event model."""
    target_id: str
    target_name: str
    event_type: Literal['threshold_reached', 'recovered', 'alert_repeat']
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    message: str
    current_failures: int
    failure_threshold: int


class SystemStatus(BaseModel):
    """Overall system status."""
    total_targets: int
    enabled_targets: int
    targets_up: int
    targets_down: int
    targets_unknown: int
    alerts_active: int
    last_update: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
