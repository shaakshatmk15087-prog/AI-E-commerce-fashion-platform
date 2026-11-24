from ..extensions import db
from .user import utcnow


class Notification(db.Model):
    __tablename__ = "notifications"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    type = db.Column(db.String(30), nullable=False)
    title = db.Column(db.String(120), nullable=False)
    body = db.Column(db.String(400), nullable=True)
    link = db.Column(db.String(200), nullable=True)
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    dedupe_key = db.Column(db.String(120), nullable=True, unique=True)  # makes reminders idempotent
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    def to_dict(self):
        return {"id": self.id, "type": self.type, "title": self.title, "body": self.body, "link": self.link,
                "is_read": self.is_read, "created_at": self.created_at.isoformat() + "Z"}
