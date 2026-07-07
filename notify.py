"""Failure emails: the pipeline heals itself, so mail only says what broke
and whether it needs a human. Off until NOTIFY_* is set in .env — never
raises, a broken mail setup must not break posting."""

import smtplib
from email.message import EmailMessage

import config


def send_failure(subject: str, body: str) -> bool:
    if not (config.NOTIFY_EMAIL_TO and config.NOTIFY_SMTP_USER
            and config.NOTIFY_SMTP_PASSWORD):
        return False
    msg = EmailMessage()
    msg["Subject"] = f"[autoTiktok] {subject}"
    msg["From"] = config.NOTIFY_SMTP_USER
    msg["To"] = config.NOTIFY_EMAIL_TO
    msg.set_content(body)
    try:
        with smtplib.SMTP(config.NOTIFY_SMTP_HOST, config.NOTIFY_SMTP_PORT,
                          timeout=30) as smtp:
            smtp.starttls()
            smtp.login(config.NOTIFY_SMTP_USER, config.NOTIFY_SMTP_PASSWORD)
            smtp.send_message(msg)
        return True
    except Exception as exc:
        print(f"warning: failure email not sent "
              f"({exc.__class__.__name__}: {exc})")
        return False
