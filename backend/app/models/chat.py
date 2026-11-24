from ..extensions import db
from .user import utcnow


class ChatSession(db.Model):
    __tablename__ = "chat_sessions"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    session_type = db.Column(db.String(20), nullable=False, default="ai")  # ai | stylist (Phase 5)
    title = db.Column(db.String(120), nullable=True)
    consultation_id = db.Column(db.Integer, db.ForeignKey("consultations.id", ondelete="CASCADE"), nullable=True, unique=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    messages = db.relationship("ChatMessage", backref="session", cascade="all, delete-orphan",
                               order_by="ChatMessage.id")


class ChatMessage(db.Model):
    __tablename__ = "chat_messages"
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    sender_type = db.Column(db.String(20), nullable=False)  # user | assistant
    message_text = db.Column(db.Text, nullable=False)
    # [{"id": product_id, "reason": str}] - ids only; prices/stock are always re-read from the catalogue.
    picks = db.Column(db.JSON, nullable=False, default=list)
    # Usage monitoring for assistant turns: {"mode": "ai"|"fallback", "model", "input_tokens", "output_tokens", "llm_calls"}
    meta = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)
