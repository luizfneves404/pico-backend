import logging

import boto3
from fastapi import BackgroundTasks
from pydantic import BaseModel
from shared.validation import LowercaseEmailStr

from app.config import settings

logger = logging.getLogger(__name__)


class EmailMessage(BaseModel):
    subject: str
    body_text: str | None = None
    body_html: str | None = None
    to_emails: list[LowercaseEmailStr]
    cc_emails: list[LowercaseEmailStr] | None = None
    bcc_emails: list[LowercaseEmailStr] | None = None


def _send_email(email: EmailMessage):
    client = boto3.client("ses", region_name=settings.aws_ses_region_name)

    destination = {"ToAddresses": email.to_emails}
    if email.cc_emails:
        destination["CcAddresses"] = email.cc_emails
    if email.bcc_emails:
        destination["BccAddresses"] = email.bcc_emails

    message = {"Subject": {"Data": email.subject}, "Body": {}}
    if email.body_text:
        message["Body"]["Text"] = {"Data": email.body_text}
    if email.body_html:
        message["Body"]["Html"] = {"Data": email.body_html}

    response = client.send_email(
        Source=settings.aws_ses_from_email, Destination=destination, Message=message
    )
    logger.info(f"Email sent: MessageId {response.get('MessageId')}")
    return True


def send_email(
    background_tasks: BackgroundTasks, email: EmailMessage | list[EmailMessage]
):
    if isinstance(email, list):
        for single_email in email:
            background_tasks.add_task(_send_email, single_email)

        logger.info(f"Emails scheduled to be sent: {len(email)}")
    else:
        background_tasks.add_task(_send_email, email)
        logger.info("Email scheduled to be sent")
