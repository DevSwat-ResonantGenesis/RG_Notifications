"""Email sending functionality."""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional, List
import asyncio
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import settings


class EmailSender:
    """Handles email sending with templates."""
    
    def __init__(self):
        self.smtp_host = settings.SMTP_HOST
        self.smtp_port = settings.SMTP_PORT
        self.smtp_user = settings.SMTP_USER
        self.smtp_password = settings.SMTP_PASSWORD
        self.from_email = settings.EMAIL_FROM
        self.from_name = settings.EMAIL_FROM_NAME
        
        # Setup Jinja2 templates
        try:
            self.jinja_env = Environment(
                loader=FileSystemLoader(settings.TEMPLATE_DIR),
                autoescape=select_autoescape(['html', 'xml'])
            )
        except Exception:
            self.jinja_env = None
    
    async def send_email(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None
    ) -> bool:
        """Send an email asynchronously."""
        return await asyncio.to_thread(
            self._send_email_sync,
            to_email, subject, html_content, text_content, cc, bcc
        )
    
    def _send_email_sync(
        self,
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None
    ) -> bool:
        """Send email synchronously."""
        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{self.from_name} <{self.from_email}>"
            msg['To'] = to_email
            
            if cc:
                msg['Cc'] = ', '.join(cc)
            
            # Add text and HTML parts
            if text_content:
                msg.attach(MIMEText(text_content, 'plain'))
            msg.attach(MIMEText(html_content, 'html'))
            
            # Build recipient list
            recipients = [to_email]
            if cc:
                recipients.extend(cc)
            if bcc:
                recipients.extend(bcc)
            
            # Send
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                if self.smtp_user and self.smtp_password:
                    server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.from_email, recipients, msg.as_string())
            
            return True
        except Exception as e:
            print(f"Email send error: {e}")
            return False
    
    def render_template(self, template_name: str, **context) -> str:
        """Render an email template."""
        if not self.jinja_env:
            return context.get('message', '')
        
        template = self.jinja_env.get_template(template_name)
        return template.render(**context)
    
    async def send_agent_created(self, to_email: str, agent_name: str, agent_id: str):
        """Send agent created notification."""
        html = self.render_template('agent_created.html', 
            agent_name=agent_name,
            agent_id=agent_id,
            dashboard_url=f"https://resonantgenesis.ai/agents/{agent_id}"
        )
        return await self.send_email(to_email, f"Agent Created: {agent_name}", html)
    
    async def send_workflow_completed(self, to_email: str, workflow_name: str, 
                                      workflow_id: str, run_id: str, status: str):
        """Send workflow completed notification."""
        subject = f"Workflow {'Completed' if status == 'success' else 'Failed'}: {workflow_name}"
        html = self.render_template('workflow_completed.html',
            workflow_name=workflow_name,
            workflow_id=workflow_id,
            run_id=run_id,
            status=status,
            dashboard_url=f"https://resonantgenesis.ai/workflows/{workflow_id}/runs/{run_id}"
        )
        return await self.send_email(to_email, subject, html)
    
    async def send_billing_alert(self, to_email: str, alert_type: str, message: str):
        """Send billing alert notification."""
        html = self.render_template('billing_alert.html',
            alert_type=alert_type,
            message=message,
            billing_url="https://resonantgenesis.ai/settings/billing"
        )
        return await self.send_email(to_email, f"Billing Alert: {alert_type}", html)
    
    async def send_password_reset(self, to_email: str, reset_token: str):
        """Send password reset email."""
        reset_url = f"https://resonantgenesis.ai/reset-password?token={reset_token}"
        html = self.render_template('password_reset.html',
            reset_url=reset_url
        )
        return await self.send_email(to_email, "Reset Your Password", html)


email_sender = EmailSender()
