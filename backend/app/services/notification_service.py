from ..extensions import db
from ..models import Notification


def notify(user_id, type_, title, body=None, link=None, dedupe_key=None):
    """Queue an in-app notification. A `dedupe_key` makes it idempotent (used for reminders)."""
    if dedupe_key and Notification.query.filter_by(dedupe_key=dedupe_key).first():
        return None
    n = Notification(user_id=user_id, type=type_, title=title[:120], body=(body or "")[:400] or None, link=link,
                     dedupe_key=dedupe_key)
    db.session.add(n)
    return n
