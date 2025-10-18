"""
Settings data models for WebStatus.
"""
from pydantic import BaseModel, Field, validator
from typing import List
import re


class SMTPSettings(BaseModel):
    """SMTP email configuration"""
    enabled: bool = False
    host: str = Field(default="")
    port: int = Field(default=587, ge=1, le=65535)
    use_tls: bool = True
    username: str = Field(default="")
    password: str = Field(default="")
    from_address: str = Field(default="")
    from_name: str = Field(default="WebStatus")
    recipients: List[str] = Field(default_factory=list)

    @validator('recipients')
    def validate_emails(cls, v):
        """Validate email addresses"""
        if not v:
            return v
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        for email in v:
            if not re.match(email_pattern, email):
                raise ValueError(f'Invalid email address: {email}')
        return v

    @validator('host', 'from_address', 'username')
    def required_if_enabled(cls, v, values):
        """Require fields when SMTP is enabled"""
        if values.get('enabled') and not v:
            raise ValueError('This field is required when SMTP is enabled')
        return v

    @validator('password')
    def password_required_if_enabled(cls, v, values):
        """Require password when SMTP is enabled (security requirement)"""
        if values.get('enabled') and not v:
            raise ValueError('Password is required when SMTP is enabled')
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "enabled": True,
                "host": "smtp.gmail.com",
                "port": 587,
                "use_tls": True,
                "username": "alerts@example.com",
                "password": "app_password",
                "from_address": "alerts@example.com",
                "from_name": "WebStatus Alerts",
                "recipients": ["admin@example.com", "ops@example.com"]
            }
        }


class BackupSettings(BaseModel):
    """Local backup configuration"""
    enabled: bool = False
    schedule: str = Field(default="0 2 * * *")  # Daily at 2 AM (cron format)
    retention_days: int = Field(default=30, ge=1, le=365)
    compression: bool = True

    @validator('schedule')
    def validate_cron(cls, v):
        """Basic cron expression validation"""
        parts = v.split()
        if len(parts) != 5:
            raise ValueError('Invalid cron expression (must have 5 parts: minute hour day month weekday)')

        # Validate each part is either a number, *, or contains allowed characters
        allowed_chars = set('0123456789*,-/')
        for part in parts:
            if not all(c in allowed_chars for c in part):
                raise ValueError(f'Invalid cron expression part: {part}')

        return v

    class Config:
        json_schema_extra = {
            "example": {
                "enabled": True,
                "schedule": "0 2 * * *",
                "retention_days": 30,
                "compression": True
            }
        }
