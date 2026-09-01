
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import asyncio
from backend.config.config import settings
from backend.config.logger import logger


async def send_email(to: str, subject: str, body: str, html: bool = False):
    """
    Send email using Gmail SMTP + App Password (async)
    """

    "imhc vrnt rnau snof"

    sender_email = settings.EMAIL_FROM
    smtp_server = "smtp.gmail.com"
    smtp_port = 587
    smtp_username = settings.SMTP_USERNAME
    smtp_password = settings.SMTP_PASSWORD 

    # Build MIME message
    message = MIMEMultipart("alternative")
    message["From"] = sender_email
    message["To"] = to
    message["Subject"] = subject

    mime_type = "html" if html else "plain"
    message.attach(MIMEText(body, mime_type, "utf-8"))

    # Run sync I/O in thread pool
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        _send_sync,
        smtp_server,
        smtp_port,
        smtp_username,
        smtp_password,
        sender_email,
        to,
        message,
    )


def _send_sync(smtp_server, smtp_port, smtp_username, smtp_password, sender_email, to, message):
    """
    Blocking email send using Gmail SMTP
    """
    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_username, smtp_password)
            server.sendmail(sender_email, to, message.as_string())

        logger.info(f"✅ Email sent successfully to {to}")

    except Exception as e:
        logger.error(f"❌ Failed to send email to {to}: {e}")
        raise