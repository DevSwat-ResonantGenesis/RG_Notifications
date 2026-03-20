"""
EMAIL DELIVERY SERVICE
======================

Handles email delivery for Resonant Genesis.
Supports multiple providers: SendGrid, SES, SMTP.

Features:
- Template-based emails
- HTML and plain text
- Attachments
- Async delivery
- Retry logic
"""

import os
import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone
import asyncio

logger = logging.getLogger(__name__)


class EmailProvider(Enum):
    SENDGRID = "sendgrid"
    SES = "ses"
    SMTP = "smtp"


class EmailStatus(Enum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    BOUNCED = "bounced"


@dataclass
class EmailMessage:
    """Email message structure."""
    to: List[str]
    subject: str
    html_content: Optional[str] = None
    text_content: Optional[str] = None
    from_email: Optional[str] = None
    from_name: Optional[str] = None
    reply_to: Optional[str] = None
    cc: List[str] = field(default_factory=list)
    bcc: List[str] = field(default_factory=list)
    attachments: List[Dict[str, Any]] = field(default_factory=list)
    headers: Dict[str, str] = field(default_factory=dict)
    template_id: Optional[str] = None
    template_data: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)


@dataclass
class DeliveryResult:
    """Result of email delivery attempt."""
    success: bool
    message_id: Optional[str] = None
    provider: Optional[str] = None
    error: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class SendGridProvider:
    """SendGrid email provider."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self._client = None
    
    @property
    def client(self):
        if self._client is None:
            try:
                from sendgrid import SendGridAPIClient
                self._client = SendGridAPIClient(self.api_key)
            except ImportError:
                raise ImportError("sendgrid not installed. Run: pip install sendgrid")
        return self._client
    
    async def send(self, message: EmailMessage) -> DeliveryResult:
        """Send email via SendGrid."""
        try:
            from sendgrid.helpers.mail import Mail, Attachment, FileContent, FileName, FileType
            
            mail = Mail(
                from_email=(message.from_email, message.from_name),
                to_emails=message.to,
                subject=message.subject,
            )
            
            if message.html_content:
                mail.add_content(message.html_content, "text/html")
            if message.text_content:
                mail.add_content(message.text_content, "text/plain")
            
            # Add CC/BCC
            for cc in message.cc:
                mail.add_cc(cc)
            for bcc in message.bcc:
                mail.add_bcc(bcc)
            
            # Add attachments
            for att in message.attachments:
                attachment = Attachment(
                    FileContent(att.get("content", "")),
                    FileName(att.get("filename", "attachment")),
                    FileType(att.get("type", "application/octet-stream")),
                )
                mail.add_attachment(attachment)
            
            # Add categories/tags
            for tag in message.tags:
                mail.add_category(tag)
            
            # Use template if specified
            if message.template_id:
                mail.template_id = message.template_id
                mail.dynamic_template_data = message.template_data
            
            # Send async
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.send(mail)
            )
            
            return DeliveryResult(
                success=response.status_code in [200, 201, 202],
                message_id=response.headers.get("X-Message-Id"),
                provider="sendgrid",
            )
            
        except Exception as e:
            logger.error(f"SendGrid delivery failed: {e}")
            return DeliveryResult(
                success=False,
                provider="sendgrid",
                error=str(e),
            )


class SESProvider:
    """AWS SES email provider."""
    
    def __init__(self, region: str = None):
        self.region = region or os.getenv("AWS_REGION", "us-east-1")
        self._client = None
    
    @property
    def client(self):
        if self._client is None:
            try:
                import boto3
                self._client = boto3.client("ses", region_name=self.region)
            except ImportError:
                raise ImportError("boto3 not installed. Run: pip install boto3")
        return self._client
    
    async def send(self, message: EmailMessage) -> DeliveryResult:
        """Send email via AWS SES."""
        try:
            body = {}
            if message.html_content:
                body["Html"] = {"Charset": "UTF-8", "Data": message.html_content}
            if message.text_content:
                body["Text"] = {"Charset": "UTF-8", "Data": message.text_content}
            
            params = {
                "Source": f"{message.from_name} <{message.from_email}>" if message.from_name else message.from_email,
                "Destination": {
                    "ToAddresses": message.to,
                    "CcAddresses": message.cc,
                    "BccAddresses": message.bcc,
                },
                "Message": {
                    "Subject": {"Charset": "UTF-8", "Data": message.subject},
                    "Body": body,
                },
            }
            
            if message.reply_to:
                params["ReplyToAddresses"] = [message.reply_to]
            
            # Send async
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.send_email(**params)
            )
            
            return DeliveryResult(
                success=True,
                message_id=response.get("MessageId"),
                provider="ses",
            )
            
        except Exception as e:
            logger.error(f"SES delivery failed: {e}")
            return DeliveryResult(
                success=False,
                provider="ses",
                error=str(e),
            )


class SMTPProvider:
    """SMTP email provider."""
    
    def __init__(
        self,
        host: str,
        port: int = 587,
        username: str = None,
        password: str = None,
        use_tls: bool = True,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_tls = use_tls
    
    async def send(self, message: EmailMessage) -> DeliveryResult:
        """Send email via SMTP."""
        try:
            import aiosmtplib
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText
            from email.mime.base import MIMEBase
            from email import encoders
            
            msg = MIMEMultipart("alternative")
            msg["Subject"] = message.subject
            msg["From"] = f"{message.from_name} <{message.from_email}>" if message.from_name else message.from_email
            msg["To"] = ", ".join(message.to)
            
            if message.cc:
                msg["Cc"] = ", ".join(message.cc)
            if message.reply_to:
                msg["Reply-To"] = message.reply_to
            
            # Add content
            if message.text_content:
                msg.attach(MIMEText(message.text_content, "plain"))
            if message.html_content:
                msg.attach(MIMEText(message.html_content, "html"))
            
            # Add attachments
            for att in message.attachments:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(att.get("content", b""))
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f'attachment; filename="{att.get("filename", "attachment")}"',
                )
                msg.attach(part)
            
            # All recipients
            recipients = message.to + message.cc + message.bcc
            
            # Send
            await aiosmtplib.send(
                msg,
                hostname=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                start_tls=self.use_tls,
                recipients=recipients,
            )
            
            return DeliveryResult(
                success=True,
                provider="smtp",
            )
            
        except Exception as e:
            logger.error(f"SMTP delivery failed: {e}")
            return DeliveryResult(
                success=False,
                provider="smtp",
                error=str(e),
            )


class EmailDeliveryService:
    """
    Main email delivery service.
    
    Handles provider selection, retries, and fallbacks.
    """
    
    DEFAULT_FROM_EMAIL = "info@dev-swat.com"
    DEFAULT_FROM_NAME = "DevSwat"
    MAX_RETRIES = 3
    
    def __init__(self):
        self.providers: Dict[str, Any] = {}
        self.primary_provider: Optional[str] = None
        self._init_providers()
    
    def _init_providers(self):
        """Initialize available providers."""
        # SendGrid
        sendgrid_key = os.getenv("SENDGRID_API_KEY")
        if sendgrid_key:
            self.providers["sendgrid"] = SendGridProvider(sendgrid_key)
            self.primary_provider = "sendgrid"
        
        # SES
        if os.getenv("AWS_ACCESS_KEY_ID") or os.getenv("AWS_ROLE_ARN"):
            self.providers["ses"] = SESProvider()
            if not self.primary_provider:
                self.primary_provider = "ses"
        
        # SMTP
        smtp_host = os.getenv("SMTP_HOST")
        if smtp_host:
            self.providers["smtp"] = SMTPProvider(
                host=smtp_host,
                port=int(os.getenv("SMTP_PORT", "587")),
                username=os.getenv("SMTP_USER"),
                password=os.getenv("SMTP_PASSWORD"),
            )
            if not self.primary_provider:
                self.primary_provider = "smtp"
        
        if not self.providers:
            logger.warning("No email providers configured")
    
    async def send(
        self,
        to: List[str],
        subject: str,
        html_content: str = None,
        text_content: str = None,
        from_email: str = None,
        from_name: str = None,
        template_id: str = None,
        template_data: Dict[str, Any] = None,
        **kwargs,
    ) -> DeliveryResult:
        """
        Send an email.
        
        Args:
            to: List of recipient emails
            subject: Email subject
            html_content: HTML body
            text_content: Plain text body
            from_email: Sender email
            from_name: Sender name
            template_id: Template ID (provider-specific)
            template_data: Template variables
        
        Returns:
            DeliveryResult with success status
        """
        if not self.providers:
            return DeliveryResult(
                success=False,
                error="No email providers configured",
            )
        
        message = EmailMessage(
            to=to if isinstance(to, list) else [to],
            subject=subject,
            html_content=html_content,
            text_content=text_content,
            from_email=from_email or os.getenv("FROM_EMAIL", self.DEFAULT_FROM_EMAIL),
            from_name=from_name or os.getenv("FROM_NAME", self.DEFAULT_FROM_NAME),
            template_id=template_id,
            template_data=template_data or {},
            **kwargs,
        )
        
        # Try primary provider first
        if self.primary_provider:
            result = await self._send_with_retry(self.primary_provider, message)
            if result.success:
                return result
        
        # Fallback to other providers
        for provider_name, provider in self.providers.items():
            if provider_name == self.primary_provider:
                continue
            
            result = await self._send_with_retry(provider_name, message)
            if result.success:
                return result
        
        return DeliveryResult(
            success=False,
            error="All providers failed",
        )
    
    async def _send_with_retry(
        self,
        provider_name: str,
        message: EmailMessage,
    ) -> DeliveryResult:
        """Send with retry logic."""
        provider = self.providers.get(provider_name)
        if not provider:
            return DeliveryResult(success=False, error=f"Provider {provider_name} not found")
        
        last_error = None
        for attempt in range(self.MAX_RETRIES):
            result = await provider.send(message)
            if result.success:
                return result
            
            last_error = result.error
            if attempt < self.MAX_RETRIES - 1:
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
        
        return DeliveryResult(
            success=False,
            provider=provider_name,
            error=last_error,
        )
    
    async def send_welcome_email(self, to: str, name: str) -> DeliveryResult:
        """Send welcome email to new user."""
        return await self.send(
            to=[to],
            subject="Welcome to Resonant Genesis!",
            html_content=f"""
            <h1>Welcome, {name}!</h1>
            <p>Thank you for joining Resonant Genesis.</p>
            <p>Get started by exploring our autonomous AI agents.</p>
            <a href="https://resonantgenesis.ai/dashboard">Go to Dashboard</a>
            """,
            text_content=f"Welcome, {name}! Thank you for joining Resonant Genesis.",
            tags=["welcome", "onboarding"],
        )
    
    async def send_password_reset(self, to: str, reset_link: str) -> DeliveryResult:
        """Send password reset email."""
        return await self.send(
            to=[to],
            subject="Reset Your Password - Resonant Genesis",
            html_content=f"""
            <h2>Password Reset Request</h2>
            <p>Click the link below to reset your password:</p>
            <a href="{reset_link}">Reset Password</a>
            <p>This link expires in 1 hour.</p>
            <p>If you didn't request this, please ignore this email.</p>
            """,
            text_content=f"Reset your password: {reset_link}",
            tags=["password-reset", "security"],
        )
    
    async def send_notification(
        self,
        to: str,
        title: str,
        message: str,
        action_url: str = None,
    ) -> DeliveryResult:
        """Send a notification email."""
        html = f"<h2>{title}</h2><p>{message}</p>"
        if action_url:
            html += f'<a href="{action_url}">View Details</a>'
        
        return await self.send(
            to=[to],
            subject=title,
            html_content=html,
            text_content=message,
            tags=["notification"],
        )


# Singleton instance
_service: Optional[EmailDeliveryService] = None


def get_email_service() -> EmailDeliveryService:
    """Get or create email delivery service."""
    global _service
    if _service is None:
        _service = EmailDeliveryService()
    return _service
