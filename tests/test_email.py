from arq import Worker

from app.config import settings
from app.mail import EmailMessage, enqueue_email
from tests.conftest import DummySESClient


async def test_send_mail_function(
    dummy_ses_client: DummySESClient, arq_worker: Worker
) -> None:
    # Create a sample email message.
    email = EmailMessage(
        subject="Test Email",
        body_text="This is a test email.",
        body_html="<p>This is a test email.</p>",
        to_emails=["to@example.com"],
    )

    # Send the email.
    await enqueue_email(email)

    await arq_worker.async_run()

    # Verify that the dummy SES client recorded the email send.
    assert len(dummy_ses_client.sent_emails) == 1
    sent_email = dummy_ses_client.sent_emails[0]
    assert sent_email["Source"] == settings.aws_ses_from_email
    assert sent_email["Destination"]["ToAddresses"] == ["to@example.com"]
    assert sent_email["Message"]["Subject"]["Data"] == "Test Email"


async def test_send_mails_function(
    dummy_ses_client: DummySESClient, arq_worker: Worker
) -> None:
    # Create multiple email messages.
    emails = [
        EmailMessage(
            subject="Email 1",
            body_text="First email",
            body_html="<p>First email</p>",
            to_emails=["to1@example.com"],
        ),
        EmailMessage(
            subject="Email 2",
            body_text="Second email",
            body_html="<p>Second email</p>",
            to_emails=["to2@example.com"],
        ),
    ]

    await enqueue_email(emails)

    await arq_worker.async_run()

    # Verify that both emails were recorded.
    assert len(dummy_ses_client.sent_emails) == 2
    subjects = [
        email["Message"]["Subject"]["Data"] for email in dummy_ses_client.sent_emails
    ]
    assert "Email 1" in subjects
    assert "Email 2" in subjects
