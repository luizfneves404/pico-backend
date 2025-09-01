import asyncio
import json
import logging
import re
import traceback
from asyncio import Task
from collections.abc import Sequence
from datetime import datetime, timedelta
from io import BytesIO
from typing import Any, Protocol

import boto3
from fastapi import Request
from jinja2 import Template
from pydantic import BaseModel

import app.mail as mail
from app.arq_client import enqueue_job
from app.config import Environment, settings
from app.files.storage import storage
from app.shared.validation import LowercaseEmailStr
from app.users.models import User

email_tasks: list[Task[None]] = []

logger = logging.getLogger(__name__)
ERROR_EMAIL_HTML_TEMPLATE = Template("""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
            .container { padding: 20px; max-width: 800px; margin: 0 auto; }
            .header { background: #f44336; color: white; padding: 15px; border-radius: 4px; }
            .section { margin: 20px 0; }
            .section-title { color: #333; border-bottom: 2px solid #eee; padding-bottom: 5px; }
            .metadata-item { margin: 5px 0; }
            .key { color: #666; }
            .message { background: #f5f5f5; padding: 15px; border-radius: 4px; }
            .traceback { background: #272822; color: #f8f8f2; padding: 15px; border-radius: 4px; 
                        font-family: monospace; white-space: pre-wrap; }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>⚠️ Error Alert</h2>
            </div>
            
            <div class="section">
                <h3 class="section-title">📊 Metadata</h3>
                <div class="metadata-item"><span class="key">Severity:</span> {{ level }}</div>
                <div class="metadata-item"><span class="key">Logger:</span> {{ logger }}</div>
                <div class="metadata-item"><span class="key">Location:</span> {{ location }}</div>
                <div class="metadata-item"><span class="key">Function:</span> {{ function }}</div>
                {% if timestamp %}
                <div class="metadata-item"><span class="key">Timestamp:</span> {{ timestamp }}</div>
                {% endif %}
            </div>

            <div class="section">
                <h3 class="section-title">📝 Error Message</h3>
                <div class="message">{{ message }}</div>
            </div>

            {% if traceback %}
            <div class="section">
                <h3 class="section-title">🔍 Traceback</h3>
                <div class="traceback">{{ traceback }}</div>
            </div>
            {% endif %}
        </div>
    </body>
    </html>
    """)


class EmailMessage(BaseModel):
    subject: str
    body_text: str | None = None
    body_html: str | None = None
    to_emails: list[LowercaseEmailStr]
    cc_emails: list[LowercaseEmailStr] | None = None
    bcc_emails: list[LowercaseEmailStr] | None = None


class FileBasedEmailClient:
    """Email client that stores emails as files using the configured storage backend."""

    def send_email(
        self,
        Source: str,
        Destination: dict[str, Sequence[str]],
        Message: dict[str, dict[str, str | dict[str, str]]],
    ) -> dict[str, str]:
        email_data = {"Source": Source, "Destination": Destination, "Message": Message}

        email_json = json.dumps(email_data, indent=2)
        file_obj = BytesIO(email_json.encode("utf-8"))

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        file_name = f"email_{timestamp}.json"

        # Upload to storage
        file_id = storage.upload(file_obj, file_name)

        return {"MessageId": file_id}


class SESClient(Protocol):
    def send_email(
        self,
        Source: str,
        Destination: dict[str, Sequence[str]],
        Message: dict[str, dict[str, str | dict[str, str]]],
    ) -> dict[str, str]: ...


client: SESClient = (
    boto3.client("ses", region_name=settings.aws_ses_region_name)
    if settings.environment == Environment.PROD
    else FileBasedEmailClient()
)


def inject_client(ses_client: SESClient) -> None:
    global client
    client = ses_client


def sanitize_subject(subject: str) -> str:
    # Remove control characters (except TAB if desired)
    return re.sub(r"[\x00-\x1F\x7F]", "", subject)


async def task_send_email(ctx: dict[Any, Any], email: EmailMessage) -> None:
    """
    Task function to write an email to a file instead of sending it.
    This function is meant to be called by Arq workers.

    Args:
        ctx: The Arq context object
        email: The email message to write to file

    Returns:
        bool: True if the email was written successfully
    """
    send_email(email)


def send_email(email: EmailMessage) -> None:
    """Send an email synchronously."""
    try:
        destination: dict[str, Sequence[str]] = {"ToAddresses": email.to_emails}
        if email.cc_emails:
            destination["CcAddresses"] = email.cc_emails
        if email.bcc_emails:
            destination["BccAddresses"] = email.bcc_emails

        subject = sanitize_subject(email.subject)
        message: dict[str, dict[str, str | dict[str, str]]] = {
            "Subject": {"Data": subject},
            "Body": {},
        }
        if email.body_text:
            message["Body"]["Text"] = {"Data": email.body_text}
        if email.body_html:
            message["Body"]["Html"] = {"Data": email.body_html}

        response = client.send_email(
            Source=settings.aws_ses_from_email, Destination=destination, Message=message
        )
        logger.info(f"Email sent: MessageId {response.get('MessageId')}")
    except Exception as e:
        logger.warning(
            f"Not sending error email to avoid infinite recursion. Error inside task_send_email was: {e}",
            exc_info=True,
        )


async def enqueue_email(email: EmailMessage | list[EmailMessage]) -> None:
    """
    Enqueue one or more emails to be sent asynchronously using Arq.
    """
    try:
        if isinstance(email, list):
            for single_email in email:
                await enqueue_job("task_send_email", single_email)
            logger.info(f"Enqueued {len(email)} emails to be sent")
        else:
            await enqueue_job("task_send_email", email)
            logger.info("Enqueued email to be sent")
    except Exception as e:
        logger.warning(
            f"Error when trying to enqueue email. Startup has probably not finished yet. Error was: {e}",
        )


async def send_bulk_email(
    users: list[User],
    subject: str,
    html_string: str,
    id_zero_padding: int = 0,
) -> None:
    messages: list[mail.EmailMessage] = []
    for user in users:
        # Replace template markers with user data
        personalized_html = (
            html_string.replace(
                "%%id%%",
                (
                    str(user.id).zfill(id_zero_padding)
                    if id_zero_padding
                    else str(user.id)
                ),
            )
            .replace("%%username%%", user.username)
            .replace("%%email%%", user.email)
        )
        messages.append(
            mail.EmailMessage(
                subject=subject,
                body_html=personalized_html,
                to_emails=[user.email],
            )
        )
    await mail.enqueue_email(messages)
    logger.info(f"Sent bulk email to {len(users)} users")


class AdminEmailHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.last_email_time = {}  # Track last email time by error type
        self.email_cooldown = timedelta(
            minutes=15
        )  # 15 minute cooldown between similar errors
        # Circuit breaker for email failures
        self.email_failures = 0
        self.last_failure_time = None
        self.circuit_breaker_threshold = 5  # After 5 failures
        self.circuit_breaker_timeout = timedelta(minutes=30)  # Wait 30 minutes

    def _get_error_key(self, record: logging.LogRecord) -> str:
        """Generate a key to identify similar errors for rate limiting."""
        return f"{record.name}:{record.funcName}:{record.getMessage()[:50]}"

    def _should_send_email(self, error_key: str) -> bool:
        """Check if we should send an email based on rate limiting."""
        now = datetime.now()
        last_time = self.last_email_time.get(error_key)

        if last_time is None or now - last_time > self.email_cooldown:
            self.last_email_time[error_key] = now
            return True
        return False

    def _is_circuit_breaker_open(self) -> bool:
        """Check if circuit breaker is open (too many recent failures)."""
        if self.email_failures < self.circuit_breaker_threshold:
            return False

        if self.last_failure_time is None:
            return False

        time_since_failure = datetime.now() - self.last_failure_time
        if time_since_failure > self.circuit_breaker_timeout:
            # Reset circuit breaker after timeout
            self.email_failures = 0
            self.last_failure_time = None
            return False

        return True

    def emit(self, record: logging.LogRecord) -> None:
        try:
            # Check if error emails are enabled
            if not settings.enable_error_emails:
                logger.debug("Error emails are disabled, skipping email notification")
                return

            # Check circuit breaker
            if self._is_circuit_breaker_open():
                logger.debug("Email circuit breaker is open, skipping error email")
                return

            # Check rate limiting to avoid quota issues
            error_key = self._get_error_key(record)
            if not self._should_send_email(error_key):
                # Log that we're skipping this email due to rate limiting
                logger.debug(f"Skipping error email due to rate limiting: {error_key}")
                return
            # Prepare the plain text version (as fallback)
            text_parts: list[str] = [
                "ERROR DETAILS",
                "═══════════════",
                "",
                "Metadata:",
                f"  • Severity: {record.levelname}",
                f"  • Logger: {record.name}",
                f"  • Location: {record.pathname}:{record.lineno}",
                f"  • Function: {record.funcName}",
            ]

            if hasattr(record, "asctime"):
                text_parts.append(f"  • Timestamp: {record.asctime}")

            text_parts.extend(
                ["", "Error Message:", "─────────────────", record.getMessage(), ""]
            )

            traceback_text = None
            if record.exc_info:
                traceback_text = "".join(traceback.format_exception(*record.exc_info))
                text_parts.extend(["Traceback:", "────────────", traceback_text])

            # Generate HTML version
            html_content = ERROR_EMAIL_HTML_TEMPLATE.render(
                level=record.levelname,
                logger=record.name,
                location=f"{record.pathname}:{record.lineno}",
                function=record.funcName,
                timestamp=getattr(record, "asctime", None),
                message=record.getMessage(),
                traceback=traceback_text,
            )

            subject = f"[{record.levelname}] Error in {record.name}: {record.getMessage()[:50]}..."

            email_message = EmailMessage(
                subject=subject,
                body_text="\n".join(text_parts),  # Fallback plain text version
                body_html=html_content,  # HTML version
                to_emails=settings.admin_emails,
            )

            # Schedule the email directly using the task function to avoid asyncio issues
            loop = asyncio.get_event_loop()
            if loop.is_running():
                task = loop.create_task(enqueue_email(email_message))
                task.add_done_callback(lambda t: email_tasks.remove(t))
                email_tasks.append(task)
            else:
                asyncio.run(enqueue_email(email_message))
        except Exception as e:
            logger.warning(
                f"Not sending error email to avoid infinite recursion. Error inside AdminEmailHandler.emit was: {e}",
                exc_info=True,
            )


PASSWORD_RESET_EMAIL_TEMPLATE = """
    <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto;">
            <h2>Password Reset Request</h2>
            <p>Click the button below to reset your password:</p>
            
            <div style="text-align: center; margin: 30px 0;">
                <a href="{reset_link}" 
                   style="background-color: #007AFF; color: white; padding: 15px 30px; 
                          text-decoration: none; border-radius: 8px; display: inline-block;
                          font-weight: bold;">
                    Reset Password
                </a>
            </div>
            
            <p style="color: #666; font-size: 12px;">
                This link will expire in 15 minutes.<br>
                If you didn't request this, please ignore this email.
            </p>
        </body>
    </html>
"""


async def send_password_reset_email(
    request: Request,
    email: str,
    token: str,
):
    """Send password reset email"""
    # Email content
    reset_link = request.url_for("password_reset_page", token=token)
    subject = "Password Reset Request"
    html_body = PASSWORD_RESET_EMAIL_TEMPLATE.format(reset_link=str(reset_link))

    email_message = EmailMessage(
        subject=subject,
        body_html=html_body,
        to_emails=[email],
    )

    await enqueue_email(email_message)
