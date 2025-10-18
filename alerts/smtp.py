"""
SMTP Email Notifications
Sends email alerts when targets go down or recover.
"""
import aiosmtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class SMTPNotifier:
    """Send email notifications via SMTP"""

    def __init__(self, config: dict):
        self.enabled = config.get('enabled', False)
        self.host = config.get('host')
        self.port = config.get('port', 587)
        self.use_tls = config.get('use_tls', True)
        self.username = config.get('username')
        self.password = config.get('password')
        self.from_address = config.get('from_address')
        self.from_name = config.get('from_name', 'WebStatus')
        self.recipients = config.get('recipients', [])

    async def send_alert(self, target: dict, status: str, message: str = ""):
        """
        Send email alert for target status change (async).

        Args:
            target: Target dict with name, address, etc.
            status: 'down' or 'up'
            message: Optional error/status message
        """
        if not self.enabled or not self.recipients:
            logger.debug("SMTP not enabled or no recipients configured")
            return

        try:
            subject = self._build_subject(target, status)
            body_text = self._build_text_body(target, status, message)
            body_html = self._build_html_body(target, status, message)

            await self._send_email(
                recipients=self.recipients,
                subject=subject,
                body_text=body_text,
                body_html=body_html
            )

            logger.info(f"✉️  Email alert sent for {target['name']} ({status})")

        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")

    async def send_test_email(self, recipient: str):
        """Send test email to verify SMTP configuration (async)"""
        subject = "WebStatus - Test Email"
        body_text = """
This is a test email from WebStatus.

Your SMTP configuration is working correctly!

--
WebStatus
Automated Monitoring System
        """

        body_html = """
<!DOCTYPE html>
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; margin: 0; padding: 20px; }
        .test-box {
            border: 2px solid #28a745;
            border-radius: 8px;
            padding: 20px;
            background: #f0fff4;
            max-width: 600px;
        }
        .header { color: #28a745; font-size: 24px; margin-bottom: 10px; }
    </style>
</head>
<body>
    <div class="test-box">
        <div class="header">✅ Test Email</div>
        <p>This is a test email from <strong>WebStatus</strong>.</p>
        <p>Your SMTP configuration is working correctly!</p>
        <hr>
        <p style="color: #666; font-size: 12px;">
            WebStatus - Automated Monitoring System
        </p>
    </div>
</body>
</html>
        """

        try:
            await self._send_email([recipient], subject, body_text, body_html)
            logger.info(f"Test email sent to {recipient}")
            return True
        except Exception as e:
            logger.error(f"Test email failed: {e}")
            raise

    def _build_subject(self, target: dict, status: str) -> str:
        """Build email subject line"""
        name = target.get('name', 'Unknown Target')

        if status == 'down':
            return f"🔴 ALERT: {name} is DOWN"
        elif status == 'up':
            return f"✅ RECOVERED: {name} is UP"
        else:
            return f"⚠️ Status Change: {name}"

    def _build_text_body(self, target: dict, status: str, message: str) -> str:
        """Build plain text email body"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if status == 'down':
            body = f"""
ALERT: Target is DOWN
{'=' * 50}

Target:   {target.get('name', 'Unknown')}
Type:     {target.get('type', 'unknown')}
Address:  {target.get('address', 'N/A')}
Status:   DOWN
Time:     {timestamp}

Error: {message or 'No additional information'}

{'=' * 50}
WebStatus - Automated Monitoring System
            """
        else:  # up/recovered
            body = f"""
RECOVERED: Target is UP
{'=' * 50}

Target:   {target.get('name', 'Unknown')}
Type:     {target.get('type', 'unknown')}
Address:  {target.get('address', 'N/A')}
Status:   UP
Time:     {timestamp}

The target has recovered and is now responding normally.

{'=' * 50}
WebStatus - Automated Monitoring System
            """

        return body

    def _build_html_body(self, target: dict, status: str, message: str) -> str:
        """Build HTML email body"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        if status == 'down':
            color = '#dc3545'
            bg_color = '#fff5f5'
            icon = '🔴'
            title = 'Target is DOWN'
        else:
            color = '#28a745'
            bg_color = '#f0fff4'
            icon = '✅'
            title = 'Target RECOVERED'

        html = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; }}
        .alert-box {{
            border: 2px solid {color};
            border-radius: 8px;
            padding: 20px;
            background: {bg_color};
            max-width: 600px;
        }}
        .header {{ color: {color}; font-size: 24px; margin-bottom: 15px; }}
        .details {{ margin: 20px 0; }}
        .detail-row {{ margin: 8px 0; }}
        .label {{ font-weight: bold; color: #333; }}
        .value {{ color: #666; }}
        .footer {{
            margin-top: 20px;
            padding-top: 15px;
            border-top: 1px solid #ddd;
            font-size: 12px;
            color: #666;
        }}
    </style>
</head>
<body>
    <div class="alert-box">
        <div class="header">{icon} {title}</div>
        <div class="details">
            <div class="detail-row">
                <span class="label">Target:</span>
                <span class="value">{target.get('name', 'Unknown')}</span>
            </div>
            <div class="detail-row">
                <span class="label">Type:</span>
                <span class="value">{target.get('type', 'unknown').upper()}</span>
            </div>
            <div class="detail-row">
                <span class="label">Address:</span>
                <span class="value">{target.get('address', 'N/A')}</span>
            </div>
            <div class="detail-row">
                <span class="label">Status:</span>
                <span class="value" style="color: {color}; font-weight: bold;">{status.upper()}</span>
            </div>
            <div class="detail-row">
                <span class="label">Time:</span>
                <span class="value">{timestamp}</span>
            </div>
        """

        if message and status == 'down':
            html += f"""
            <div class="detail-row" style="margin-top: 15px;">
                <span class="label">Error:</span><br>
                <span class="value">{message}</span>
            </div>
            """

        html += """
        </div>
        <div class="footer">
            WebStatus - Automated Monitoring System
        </div>
    </div>
</body>
</html>
        """

        return html

    async def _send_email(
        self,
        recipients: List[str],
        subject: str,
        body_text: str,
        body_html: Optional[str] = None
    ):
        """Send email using SMTP (async)"""
        # Create message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = f"{self.from_name} <{self.from_address}>"
        msg['To'] = ', '.join(recipients)

        # Add text part
        part_text = MIMEText(body_text, 'plain')
        msg.attach(part_text)

        # Add HTML part if provided
        if body_html:
            part_html = MIMEText(body_html, 'html')
            msg.attach(part_html)

        # Send email using async SMTP
        async with aiosmtplib.SMTP(hostname=self.host, port=self.port, timeout=10) as server:
            if self.use_tls:
                await server.starttls()

            if self.username and self.password:
                await server.login(self.username, self.password)

            await server.send_message(msg)
