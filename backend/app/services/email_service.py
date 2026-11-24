"""Transactional email. Dev/test: messages are logged and kept in `outbox`.
Swap `send_email` for a real provider (SES, SendGrid, ...) before production."""
import logging

log = logging.getLogger(__name__)
outbox: list[dict] = []


def send_email(to: str, subject: str, body: str) -> None:
    outbox.append({"to": to, "subject": subject, "body": body})
    log.warning("EMAIL to=%s subject=%s\n%s", to, subject, body)
