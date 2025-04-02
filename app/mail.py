import asyncio
import logging
import traceback
from typing import Any, Sequence

import boto3
from jinja2 import Template
from pydantic import BaseModel

import app.mail as mail
from app.arq_client import enqueue_job
from app.config import settings
from app.shared.validation import LowercaseEmailStr
from app.users.models import User
from app.users.service import logger

HTML_TEMPLATE = Template("""
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

logger = logging.getLogger(__name__)


class EmailMessage(BaseModel):
    subject: str
    body_text: str | None = None
    body_html: str | None = None
    to_emails: list[LowercaseEmailStr]
    cc_emails: list[LowercaseEmailStr] | None = None
    bcc_emails: list[LowercaseEmailStr] | None = None


async def task_send_email(ctx: dict[Any, Any], email: EmailMessage) -> bool:
    """
    Task function to write an email to a file instead of sending it.
    This function is meant to be called by Arq workers.

    Args:
        ctx: The Arq context object
        email: The email message to write to file

    Returns:
        bool: True if the email was written successfully
    """
    client = boto3.client("ses", region_name=settings.aws_ses_region_name)

    destination: dict[str, Sequence[str]] = {"ToAddresses": email.to_emails}
    if email.cc_emails:
        destination["CcAddresses"] = email.cc_emails
    if email.bcc_emails:
        destination["BccAddresses"] = email.bcc_emails

    message: dict[str, dict[str, str | dict[str, str]]] = {
        "Subject": {"Data": email.subject},
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
    return True


async def enqueue_email(email: EmailMessage | list[EmailMessage]) -> None:
    """
    Enqueue one or more emails to be sent asynchronously using Arq.
    """
    if isinstance(email, list):
        for single_email in email:
            await enqueue_job("task_send_email", single_email)
        logger.info(f"Enqueued {len(email)} emails to be sent")
    else:
        await enqueue_job("task_send_email", email)
        logger.info("Enqueued email to be sent")


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
    def emit(self, record: logging.LogRecord) -> None:
        # Prevent infinite recursion by checking if the error is from this module
        # or if the error is from the task_send_email function
        if (
            record.name == __name__
            or record.pathname.endswith("mail.py")
            or (
                hasattr(record, "exc_info")
                and record.exc_info
                and any(
                    "task_send_email" in part.strip()
                    for part in traceback.format_exception(*record.exc_info)
                )
            )
        ):
            logger.info("Skipping email for this record to avoid infinite recursion")
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
        html_content = HTML_TEMPLATE.render(
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
            to_emails=settings.admins,
        )

        # Schedule the email directly using the task function to avoid asyncio issues
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(enqueue_email(email_message))
        else:
            asyncio.run(enqueue_email(email_message))
