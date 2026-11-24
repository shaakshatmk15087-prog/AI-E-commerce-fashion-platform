from ..extensions import db
from .user import utcnow

CONSULTATION_STATUSES = ("requested", "accepted", "declined", "cancelled", "expired", "completed")


class Stylist(db.Model):
    __tablename__ = "stylists"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    bio = db.Column(db.Text, nullable=True)
    expertise = db.Column(db.JSON, nullable=False, default=list)
    languages = db.Column(db.JSON, nullable=False, default=list)
    consultation_types = db.Column(db.JSON, nullable=False, default=lambda: ["text"])  # voice/video arrive later
    price_credits_text = db.Column(db.Integer, nullable=True)  # per-stylist override; null = platform setting
    is_approved = db.Column(db.Boolean, nullable=False, default=False)
    is_available = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    user = db.relationship("User")

    def to_dict(self, price=None):
        return {"id": self.id, "name": self.user.name, "bio": self.bio, "expertise": self.expertise or [],
                "languages": self.languages or [], "consultation_types": self.consultation_types or [],
                "is_approved": self.is_approved, "is_available": self.is_available,
                "price_credits_text": self.price_credits_text, "price_credits": price}


class StylistAvailability(db.Model):
    """A bookable slot. `status` flips open -> booked with an atomic conditional UPDATE, so a slot can't be double-booked."""
    __tablename__ = "stylist_availability"
    id = db.Column(db.Integer, primary_key=True)
    stylist_id = db.Column(db.Integer, db.ForeignKey("stylists.id", ondelete="CASCADE"), nullable=False, index=True)
    start_at = db.Column(db.DateTime, nullable=False, index=True)  # naive UTC
    end_at = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(10), nullable=False, default="open")  # open | booked

    def to_dict(self):
        return {"id": self.id, "start_at": self.start_at.isoformat() + "Z", "end_at": self.end_at.isoformat() + "Z",
                "status": self.status}


class Consultation(db.Model):
    __tablename__ = "consultations"
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    stylist_id = db.Column(db.Integer, db.ForeignKey("stylists.id"), nullable=False, index=True)
    slot_id = db.Column(db.Integer, db.ForeignKey("stylist_availability.id"), nullable=True)
    consultation_type = db.Column(db.String(10), nullable=False, default="text")
    scheduled_start = db.Column(db.DateTime, nullable=False)
    scheduled_end = db.Column(db.DateTime, nullable=False)
    credit_cost = db.Column(db.Integer, nullable=False)          # snapshot of the price at booking
    refunded_credits = db.Column(db.Integer, nullable=False, default=0)
    stylist_payout_credits = db.Column(db.Integer, nullable=True)  # set at settlement (records only, no money moves)
    status = db.Column(db.String(12), nullable=False, default="requested", index=True)
    customer_notes = db.Column(db.String(500), nullable=True)
    cancelled_by = db.Column(db.String(10), nullable=True)       # customer | stylist | system
    meeting_reference = db.Column(db.String(255), nullable=True)  # reserved for voice/video; never exposed to others
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    accepted_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)
    stylist = db.relationship("Stylist")
    customer = db.relationship("User")

    def to_dict(self):
        iso = lambda d: d.isoformat() + "Z" if d else None
        return {"id": self.id, "status": self.status, "consultation_type": self.consultation_type,
                "scheduled_start": iso(self.scheduled_start), "scheduled_end": iso(self.scheduled_end),
                "credit_cost": self.credit_cost, "refunded_credits": self.refunded_credits,
                "stylist": {"id": self.stylist.id, "name": self.stylist.user.name},
                "customer": {"id": self.customer.id, "name": self.customer.name},
                "customer_notes": self.customer_notes, "cancelled_by": self.cancelled_by,
                "created_at": iso(self.created_at), "completed_at": iso(self.completed_at)}
