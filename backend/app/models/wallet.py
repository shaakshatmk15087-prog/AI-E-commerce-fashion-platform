from ..extensions import db
from .user import utcnow

CREDIT_TYPES = ("daily", "super")
TRANSACTION_TYPES = ("grant", "purchase", "subscription", "spend", "refund", "expiry", "adjustment", "reservation", "release")


class Wallet(db.Model):
    """Cached balances. The ledger (credit_transactions) is the source of truth; see wallet_service.reconcile."""
    __tablename__ = "wallets"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    daily_balance = db.Column(db.Integer, nullable=False, default=0)
    super_balance = db.Column(db.Integer, nullable=False, default=0)
    daily_expires_at = db.Column(db.DateTime, nullable=True)  # when the current Daily Credits lapse (naive UTC)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    __table_args__ = (
        db.CheckConstraint("daily_balance >= 0", name="ck_wallet_daily_nonneg"),
        db.CheckConstraint("super_balance >= 0", name="ck_wallet_super_nonneg"),
    )


class CreditTransaction(db.Model):
    """Append-only. Never edit or delete rows; correct mistakes with compensating entries."""
    __tablename__ = "credit_transactions"
    id = db.Column(db.Integer, primary_key=True)
    wallet_id = db.Column(db.Integer, db.ForeignKey("wallets.id", ondelete="CASCADE"), nullable=False, index=True)
    credit_type = db.Column(db.String(10), nullable=False)
    transaction_type = db.Column(db.String(20), nullable=False)
    amount = db.Column(db.Integer, nullable=False)  # signed: + adds credits, - removes
    balance_after = db.Column(db.Integer, nullable=False)
    source_type = db.Column(db.String(30), nullable=True)
    source_id = db.Column(db.String(64), nullable=True)
    description = db.Column(db.String(255), nullable=True)
    idempotency_key = db.Column(db.String(120), nullable=True, unique=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="completed")
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow, index=True)

    def to_dict(self):
        return {"id": self.id, "credit_type": self.credit_type, "transaction_type": self.transaction_type,
                "amount": self.amount, "balance_after": self.balance_after, "description": self.description,
                "source_type": self.source_type, "expires_at": self.expires_at.isoformat() + "Z" if self.expires_at else None,
                "created_at": self.created_at.isoformat() + "Z"}


class DailyCreditGrant(db.Model):
    """One row per user per daily period: the unique key is what prevents duplicate grants."""
    __tablename__ = "daily_credit_grants"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    period_date = db.Column(db.Date, nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    __table_args__ = (db.UniqueConstraint("user_id", "period_date", name="uq_daily_grant_user_period"),)


class PlatformSetting(db.Model):
    __tablename__ = "platform_settings"
    key = db.Column(db.String(60), primary_key=True)
    value = db.Column(db.JSON, nullable=False)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class AuditLog(db.Model):
    __tablename__ = "audit_logs"
    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(60), nullable=False, index=True)
    target_type = db.Column(db.String(30), nullable=True)
    target_id = db.Column(db.String(64), nullable=True)
    details = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    def to_dict(self):
        return {"id": self.id, "actor_id": self.actor_id, "action": self.action, "target_type": self.target_type,
                "target_id": self.target_id, "details": self.details, "created_at": self.created_at.isoformat() + "Z"}


class CreditPack(db.Model):
    __tablename__ = "credit_packs"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    credits = db.Column(db.Integer, nullable=False)
    price_minor = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(3), nullable=False, default="INR")
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "credits": self.credits, "price_minor": self.price_minor,
                "currency": self.currency, "is_active": self.is_active}


class SubscriptionPlan(db.Model):
    __tablename__ = "subscription_plans"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    description = db.Column(db.Text, nullable=True)
    price_minor = db.Column(db.Integer, nullable=False)
    currency = db.Column(db.String(3), nullable=False, default="INR")
    billing_interval = db.Column(db.String(10), nullable=False, default="month")  # month | year
    super_credit_amount = db.Column(db.Integer, nullable=False)
    grant_frequency = db.Column(db.String(10), nullable=False, default="renewal")  # renewal | daily
    benefits = db.Column(db.JSON, nullable=False, default=list)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "description": self.description, "price_minor": self.price_minor,
                "currency": self.currency, "billing_interval": self.billing_interval,
                "super_credit_amount": self.super_credit_amount, "grant_frequency": self.grant_frequency,
                "benefits": self.benefits or [], "is_active": self.is_active}


class UserSubscription(db.Model):
    __tablename__ = "user_subscriptions"
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    plan_id = db.Column(db.Integer, db.ForeignKey("subscription_plans.id"), nullable=False)
    provider_subscription_id = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="pending")  # pending|active|cancelled|expired|incomplete
    start_at = db.Column(db.DateTime, nullable=True)
    current_period_start = db.Column(db.DateTime, nullable=True)
    current_period_end = db.Column(db.DateTime, nullable=True)
    cancel_at = db.Column(db.DateTime, nullable=True)  # set when the user cancels; access runs to this date
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    plan = db.relationship("SubscriptionPlan")

    def to_dict(self):
        iso = lambda d: d.isoformat() + "Z" if d else None
        return {"id": self.id, "status": self.status, "plan": self.plan.to_dict(), "start_at": iso(self.start_at),
                "current_period_start": iso(self.current_period_start),
                "current_period_end": iso(self.current_period_end), "cancel_at": iso(self.cancel_at)}
