"""Background maintenance. Every job is idempotent (safe to run twice, concurrently, or never): correctness does not
depend on the scheduler because wallets also self-heal lazily on access. The scheduler just keeps things tidy
(expiry entries appear on time, users who never log in still get their grant recorded, unpaid orders release stock)."""
from datetime import timedelta

from flask import current_app

from ..extensions import db
from ..models import ChatSession, Notification, TokenBlocklist, User
from ..services import consultation_service, order_service, subscription_service, wallet_service


def credit_maintenance(now=None):
    """Expire stale Daily Credits and grant the current period's credits (daily allowance + daily subscriptions)."""
    ids = [i for (i,) in db.session.query(User.id).filter_by(role="customer", is_active=True).order_by(User.id)]
    done = failed = 0
    for uid in ids:
        try:
            wallet_service.ensure_current(uid, now)
            db.session.commit()
            done += 1
        except Exception:  # one bad wallet must not block the rest
            db.session.rollback()
            current_app.logger.exception("credit maintenance failed for user %s", uid)
            failed += 1
    return {"wallets": done, "failed": failed}


def subscription_maintenance(now=None):
    n = subscription_service.expire_due(now)
    db.session.commit()
    return {"subscriptions_closed": n}


def consultation_maintenance(now=None):
    expired = consultation_service.expire_stale(now)
    reminders = consultation_service.send_reminders(now)
    db.session.commit()
    return {"consultations_expired": expired, "reminders": reminders}


def retention_maintenance(now=None):
    """Data-retention: purge what no longer needs to exist (expired revoked-token ids, old AI chats, old read notifications)."""
    now = now or wallet_service.now_utc()
    ttl = current_app.config["JWT_ACCESS_TOKEN_EXPIRES"]
    tokens = TokenBlocklist.query.filter(TokenBlocklist.created_at < now - ttl - timedelta(hours=1)).delete(synchronize_session=False)
    chat_cutoff = now - timedelta(days=current_app.config["CHAT_RETENTION_DAYS"])
    chats = 0
    for s in ChatSession.query.filter(ChatSession.session_type == "ai", ChatSession.updated_at < chat_cutoff).all():
        db.session.delete(s)
        chats += 1
    notes = Notification.query.filter(Notification.is_read.is_(True), Notification.created_at < now - timedelta(days=90)).delete(synchronize_session=False)
    db.session.commit()
    return {"revoked_tokens_purged": tokens, "ai_chats_purged": chats, "notifications_purged": notes}


def order_maintenance():
    return {"orders_released": order_service.release_expired_orders()}


def run_all(now=None):
    results = {}
    for name, fn in (("credits", lambda: credit_maintenance(now)), ("subscriptions", lambda: subscription_maintenance(now)),
                     ("consultations", lambda: consultation_maintenance(now)), ("retention", lambda: retention_maintenance(now)),
                     ("orders", order_maintenance)):
        try:
            results[name] = fn()
        except Exception:
            db.session.rollback()
            current_app.logger.exception("job %s failed", name)
            results[name] = {"error": True}
    current_app.logger.info("maintenance: %s", results)
    return results
