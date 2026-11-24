from ..extensions import db
from .user import utcnow


class RewardAccount(db.Model):
    """Cached reward-point balance (the ledger is reward_transactions). Points are NOT credits and have no cash value."""
    __tablename__ = "reward_accounts"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    balance = db.Column(db.Integer, nullable=False, default=0)
    __table_args__ = (db.CheckConstraint("balance >= 0", name="ck_reward_balance_nonneg"),)


class RewardTransaction(db.Model):
    __tablename__ = "reward_transactions"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    transaction_type = db.Column(db.String(20), nullable=False)  # earn | redeem | adjustment | reversal
    points = db.Column(db.Integer, nullable=False)               # signed
    balance_after = db.Column(db.Integer, nullable=False)
    source_type = db.Column(db.String(30), nullable=True)        # order | referral | offer | admin
    source_id = db.Column(db.String(64), nullable=True)
    description = db.Column(db.String(255), nullable=True)
    idempotency_key = db.Column(db.String(120), nullable=True, unique=True)
    status = db.Column(db.String(20), nullable=False, default="completed")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    def to_dict(self):
        return {"id": self.id, "transaction_type": self.transaction_type, "points": self.points,
                "balance_after": self.balance_after, "description": self.description,
                "created_at": self.created_at.isoformat() + "Z"}


class RewardOffer(db.Model):
    """What points can be redeemed for. Placeholder: Super Credits. No cash value is promised anywhere."""
    __tablename__ = "reward_offers"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    points_cost = db.Column(db.Integer, nullable=False)
    super_credits = db.Column(db.Integer, nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "points_cost": self.points_cost, "super_credits": self.super_credits,
                "is_active": self.is_active}


class Referral(db.Model):
    """One row per referred user (unique), so a person can be referred only once."""
    __tablename__ = "referrals"
    id = db.Column(db.Integer, primary_key=True)
    referrer_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    referred_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    status = db.Column(db.String(12), nullable=False, default="pending")  # pending | rewarded
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    rewarded_at = db.Column(db.DateTime, nullable=True)
    __table_args__ = (db.CheckConstraint("referrer_id <> referred_id", name="ck_no_self_referral"),)
