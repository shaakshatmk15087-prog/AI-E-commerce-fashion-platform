from ..extensions import db
from .user import utcnow

LIST_FIELDS = ("preferred_styles", "preferred_colors", "preferred_brands", "preferred_categories", "occasion_preferences")


class FashionProfile(db.Model):
    __tablename__ = "fashion_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    preferred_styles = db.Column(db.JSON, nullable=False, default=list)
    preferred_colors = db.Column(db.JSON, nullable=False, default=list)
    preferred_brands = db.Column(db.JSON, nullable=False, default=list)
    preferred_categories = db.Column(db.JSON, nullable=False, default=list)
    occasion_preferences = db.Column(db.JSON, nullable=False, default=list)
    budget_min_minor = db.Column(db.Integer, nullable=True)  # paise
    budget_max_minor = db.Column(db.Integer, nullable=True)
    fit_preferences = db.Column(db.String(255), nullable=True)
    size_preferences = db.Column(db.JSON, nullable=False, default=dict)  # optional, user-provided
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)

    def to_dict(self):
        d = {f: getattr(self, f) or [] for f in LIST_FIELDS}
        d.update(
            budget_min_minor=self.budget_min_minor,
            budget_max_minor=self.budget_max_minor,
            fit_preferences=self.fit_preferences,
            size_preferences=self.size_preferences or {},
        )
        return d
