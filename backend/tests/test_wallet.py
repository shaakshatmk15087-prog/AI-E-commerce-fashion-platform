import json
import os
import threading
import time
from datetime import datetime, timedelta

import pytest
from sqlalchemy.exc import OperationalError

from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.models import (AuditLog, CreditPack, CreditTransaction, DailyCreditGrant, SubscriptionPlan, User,
                        UserSubscription, Wallet)
from app.services import ai_service, payment_service, settings_service, subscription_service, wallet_service
from app.services.ai_service import AIUnavailable
from app.services.wallet_service import InsufficientCredits
from app.tasks import jobs

T0 = datetime(2026, 11, 23, 10, 0)  # 15:30 IST on 23 Nov; the IST day ends at 18:30 UTC


@pytest.fixture()
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def clock(monkeypatch):
    t = [T0]
    monkeypatch.setattr(wallet_service, "now_utc", lambda: t[0])
    return t


def register(client, email="w@example.com"):
    r = client.post("/api/v1/auth/register", json={"name": "W", "email": email, "password": "Passw0rdX"})
    return {"Authorization": f"Bearer {r.json['access_token']}"}, r.json["user"]["id"]


def make_admin(client, email="boss@example.com"):
    h, uid = register(client, email)
    User.query.filter_by(id=uid).update({"role": "admin"})
    db.session.commit()
    return h


def balances(uid):
    db.session.expire_all()
    w = Wallet.query.filter_by(user_id=uid).first()
    return (w.daily_balance, w.super_balance) if w else (0, 0)


def ledger(uid, ctype=None):
    w = Wallet.query.filter_by(user_id=uid).first()
    q = CreditTransaction.query.filter_by(wallet_id=w.id)
    if ctype:
        q = q.filter_by(credit_type=ctype)
    return q.order_by(CreditTransaction.id).all()


def set_cfg(**kw):
    cfg = settings_service.validate_credit_settings(kw)
    settings_service.save_credit_settings(cfg)
    db.session.commit()


def give_super(uid, n, key=None):
    wallet_service.grant(uid, "super", n, "grant", source_type="test", source_id=1, key=key or f"t:{uid}:{n}:{time.time_ns()}",
                         description="test grant")
    db.session.commit()


def no_llm(*a, **k):
    raise AIUnavailable("test")


# ---- daily periods ---------------------------------------------------------------------------------------
def test_period_boundaries_follow_configured_timezone_and_hour(app):
    cfg = settings_service.get_credit_settings()
    d, start, end = wallet_service.period_for(datetime(2026, 11, 23, 18, 29), cfg)       # 23:59 IST
    assert str(d) == "2026-11-23" and end == datetime(2026, 11, 23, 18, 30)
    d, _, _ = wallet_service.period_for(datetime(2026, 11, 23, 18, 30), cfg)             # 00:00 IST next day
    assert str(d) == "2026-11-24"
    six = {**cfg, "reset_hour": 6}
    assert str(wallet_service.period_for(datetime(2026, 11, 23, 0, 29), six)[0]) == "2026-11-22"   # 05:59 IST
    assert str(wallet_service.period_for(datetime(2026, 11, 23, 0, 30), six)[0]) == "2026-11-23"   # 06:00 IST
    utc = {**cfg, "reset_timezone": "UTC"}
    assert wallet_service.period_for(datetime(2026, 11, 23, 23, 59), utc)[2] == datetime(2026, 11, 24, 0, 0)


def test_one_daily_grant_per_period_and_unused_credits_expire(client, clock):
    _, uid = register(client)
    for _ in range(3):
        wallet_service.ensure_current(uid, clock[0])
    db.session.commit()
    assert balances(uid) == (10, 0) and DailyCreditGrant.query.count() == 1
    assert [t.transaction_type for t in ledger(uid)] == ["grant"]

    wallet_service.spend(uid, "ai_chat", source_type="t", source_id=1, key="x")        # cost 0 => free, no ledger noise
    set_cfg(services={"ai_chat": {"cost": 3}})
    wallet_service.spend(uid, "ai_chat", source_type="t", source_id=1, key="k1")
    db.session.commit()
    assert balances(uid) == (7, 0)

    clock[0] = T0 + timedelta(hours=9)                                                   # after 18:30 UTC => next period
    wallet_service.ensure_current(uid, clock[0])
    wallet_service.ensure_current(uid, clock[0])
    db.session.commit()
    assert balances(uid) == (10, 0)                                                      # 7 lapsed, fresh 10 (no accumulation)
    kinds = [(t.transaction_type, t.amount) for t in ledger(uid, "daily")]
    assert kinds == [("grant", 10), ("spend", -3), ("expiry", -7), ("grant", 10)]
    assert DailyCreditGrant.query.count() == 2
    assert wallet_service.reconcile(Wallet.query.filter_by(user_id=uid).first()) == {}


def test_expiry_without_new_grant_when_allowance_is_zero(client, clock):
    _, uid = register(client)
    wallet_service.ensure_current(uid, clock[0])
    db.session.commit()
    set_cfg(daily_allowance=0)
    clock[0] = T0 + timedelta(days=1)
    wallet_service.ensure_current(uid, clock[0])
    db.session.commit()
    assert balances(uid) == (0, 0)


def test_super_credits_do_not_expire_and_accumulate(client, clock):
    _, uid = register(client)
    give_super(uid, 20)
    give_super(uid, 5)
    clock[0] = T0 + timedelta(days=10)
    wallet_service.ensure_current(uid, clock[0])
    db.session.commit()
    assert balances(uid)[1] == 25


def test_only_active_customers_get_daily_credits(client, clock):
    h, admin_id = register(client, "adm@example.com")
    User.query.filter_by(id=admin_id).update({"role": "admin"})
    _, inactive = register(client, "off@example.com")
    User.query.filter_by(id=inactive).update({"is_active": False})
    db.session.commit()
    for uid in (admin_id, inactive):
        wallet_service.ensure_current(uid, clock[0])
    db.session.commit()
    assert balances(admin_id) == (0, 0) and balances(inactive) == (0, 0)


def test_grant_is_idempotent_by_key(client):
    _, uid = register(client)
    assert wallet_service.grant(uid, "super", 5, "grant", source_type="t", source_id=1, key="same", description="d") is True
    assert wallet_service.grant(uid, "super", 5, "grant", source_type="t", source_id=1, key="same", description="d") is False
    db.session.commit()
    assert balances(uid)[1] == 5 and len(ledger(uid)) == 1


# ---- spending --------------------------------------------------------------------------------------------
def test_spend_priority_and_breakdown(client, clock):
    _, uid = register(client)
    give_super(uid, 5)
    wallet_service.ensure_current(uid, clock[0])
    set_cfg(services={"ai_chat": {"cost": 12}})
    q = wallet_service.quote(uid, "ai_chat")
    assert q["sufficient"] and q["breakdown"] == {"daily": 10, "super": 2} and q["balances_after"] == {"daily": 0, "super": 3}
    assert wallet_service.spend(uid, "ai_chat", source_type="t", source_id=1, key="a")["breakdown"] == {"daily": 10, "super": 2}
    db.session.commit()
    assert balances(uid) == (0, 3)
    assert [t.amount for t in ledger(uid) if t.transaction_type == "spend"] == [-10, -2]

    set_cfg(spend_priority="super_first", services={"ai_chat": {"cost": 4}})
    db.session.commit()
    give_super(uid, 5)                                                                   # super 8, daily 0
    assert wallet_service.spend(uid, "ai_chat", source_type="t", source_id=2, key="b")["breakdown"] == {"super": 4}


def test_super_only_service_ignores_daily_credits(client, clock):
    _, uid = register(client)
    wallet_service.ensure_current(uid, clock[0])
    set_cfg(services={"ai_chat": {"cost": 2, "credit_types": ["super"]}})
    q = wallet_service.quote(uid, "ai_chat")
    assert q["sufficient"] is False and q["available"] == 0
    with pytest.raises(InsufficientCredits):
        wallet_service.spend(uid, "ai_chat", source_type="t", source_id=1, key="s")
    db.session.rollback()
    assert balances(uid)[0] == 10                                                        # nothing was taken


def test_insufficient_spend_changes_nothing(client, clock):
    _, uid = register(client)
    wallet_service.ensure_current(uid, clock[0])
    db.session.commit()
    set_cfg(services={"ai_chat": {"cost": 50}})
    before = len(ledger(uid))
    with pytest.raises(InsufficientCredits) as e:
        wallet_service.spend(uid, "ai_chat", source_type="t", source_id=1, key="n")
    assert e.value.status == 402 and e.value.details == {"needed": 50, "available": 10}
    db.session.rollback()
    assert balances(uid) == (10, 0) and len(ledger(uid)) == before


def test_spend_is_idempotent(client, clock):
    _, uid = register(client)
    wallet_service.ensure_current(uid, clock[0])
    set_cfg(services={"ai_chat": {"cost": 4}})
    r1 = wallet_service.spend(uid, "ai_chat", source_type="t", source_id=1, key="dup")
    r2 = wallet_service.spend(uid, "ai_chat", source_type="t", source_id=1, key="dup")
    db.session.commit()
    assert r1["idempotent"] is False and r2["idempotent"] is True
    assert balances(uid) == (6, 0) and len([t for t in ledger(uid) if t.transaction_type == "spend"]) == 1


def test_concurrent_spends_never_overdraw(tmp_path):
    """10 simultaneous spends against 5 credits: exactly 5 succeed, balance never negative, ledger reconciles."""
    class FileConfig(TestConfig):
        SQLALCHEMY_DATABASE_URI = os.getenv("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'c.db'}"

    app = create_app(FileConfig)
    with app.app_context():
        db.create_all()
        c = app.test_client()
        _, uid = register(c)
        set_cfg(daily_allowance=0, services={"ai_chat": {"cost": 1, "credit_types": ["super"]}})
        give_super(uid, 5)
    results = []

    def worker(i):
        with app.app_context():
            for _ in range(40):                      # client-side retry when SQLite reports the database busy
                try:
                    wallet_service.spend(uid, "ai_chat", source_type="t", source_id=i, key=f"race:{i}")
                    db.session.commit()
                    results.append(True)
                    return
                except InsufficientCredits:
                    db.session.rollback()
                    results.append(False)
                    return
                except OperationalError:
                    db.session.rollback()
                    time.sleep(0.05)
            results.append(None)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    with app.app_context():
        w = Wallet.query.filter_by(user_id=uid).first()
        assert results.count(True) == 5 and results.count(False) == 5 and None not in results
        assert w.super_balance == 0 and wallet_service.reconcile(w) == {}
        db.session.remove()
        db.drop_all()


def test_refund_restores_credits_but_not_expired_daily(client, clock):
    _, uid = register(client)
    wallet_service.ensure_current(uid, clock[0])
    give_super(uid, 5)
    set_cfg(services={"ai_chat": {"cost": 12}})
    wallet_service.spend(uid, "ai_chat", source_type="t", source_id=1, key="r1")
    db.session.commit()
    assert balances(uid) == (0, 3)
    assert wallet_service.refund_spend("r1") == {"daily": 10, "super": 2}
    assert wallet_service.refund_spend("r1") == {}                                       # second refund is a no-op
    db.session.commit()
    assert balances(uid) == (10, 5)

    wallet_service.spend(uid, "ai_chat", source_type="t", source_id=2, key="r2")
    db.session.commit()
    clock[0] = T0 + timedelta(days=1)                                                    # daily period has ended
    assert wallet_service.refund_spend("r2") == {"super": 2}                             # expired daily credits stay gone
    db.session.commit()
    assert wallet_service.reconcile(Wallet.query.filter_by(user_id=uid).first()) == {}


# ---- API + AI chat integration -----------------------------------------------------------------------------
def test_wallet_endpoints_and_isolation(client):
    h1, u1 = register(client, "a@example.com")
    h2, _ = register(client, "b@example.com")
    r = client.get("/api/v1/wallet", headers=h1)
    w = r.json["wallet"]
    assert w["daily"]["balance"] == 10 and w["super"]["balance"] == 0 and w["daily"]["next_reset_at"].endswith("Z")
    assert w["daily"]["timezone"] == "Asia/Kolkata" and r.json["subscription"] is None
    give_super(u1, 7)
    tx = client.get("/api/v1/wallet/transactions", headers=h1).json
    assert tx["total"] == 2 and {t["credit_type"] for t in tx["transactions"]} == {"daily", "super"}
    client.get("/api/v1/wallet", headers=h2)                                              # grants apply on first access
    assert client.get("/api/v1/wallet/transactions", headers=h2).json["total"] == 1      # only their own daily grant
    assert len(client.get("/api/v1/wallet/transactions?credit_type=super", headers=h1).json["transactions"]) == 1
    assert client.get("/api/v1/wallet").status_code == 401
    costs = client.get("/api/v1/wallet/credit-costs").json
    assert costs["services"][0]["service"] == "ai_chat" and costs["services"][0]["cost"] == 0


def test_quote_endpoint(client):
    h, uid = register(client)
    set_cfg(services={"ai_chat": {"cost": 4}})
    q = client.post("/api/v1/wallet/transactions/quote", json={"service": "ai_chat"}, headers=h).json["quote"]
    assert q["cost"] == 4 and q["sufficient"] and q["breakdown"] == {"daily": 4}
    assert client.post("/api/v1/wallet/transactions/quote", json={"service": "nope"}, headers=h).status_code == 400
    assert client.post("/api/v1/wallet/transactions/quote", json={"service": "ai_chat"}).status_code == 401
    assert balances(uid) == (10, 0)                                                      # a quote never spends


def _chat(client, h, text="formal shirt"):
    return client.post("/api/v1/ai/chat", json={"message": text}, headers=h)


def test_ai_chat_charges_credits_and_refunds_when_ai_not_used(client, monkeypatch):
    h, uid = register(client)
    set_cfg(services={"ai_chat": {"cost": 2}})
    monkeypatch.setattr(ai_service, "_call_llm", no_llm)                                 # fallback => must be free
    r = _chat(client, h)
    assert r.status_code == 201 and r.json["credits"] == {"charged": {}, "refunded": {"daily": 2}}
    assert balances(uid) == (10, 0)

    intent = dict(action="recommend", reply="", keywords=["formal"], category="", min_price_inr=0, max_price_inr=0,
                  colors=[], sizes=[], brands=[], occasion="", styles=[], outfit=False)
    seq = iter([intent])

    def fake(system, messages, schema, max_tokens=1500):
        try:
            return next(seq), {"input_tokens": 1, "output_tokens": 1}
        except StopIteration:
            raise AIUnavailable("no catalogue in this test")                              # explain step falls back

    monkeypatch.setattr(ai_service, "_call_llm", fake)
    # AI understood the request but the catalogue is empty => no recommendations delivered => not charged
    r = _chat(client, h)
    assert r.json["message"]["mode"] == "ai" and r.json["message"]["products"] == []
    assert r.json["credits"] == {"charged": {}, "refunded": {"daily": 2}} and balances(uid) == (10, 0)


def test_ai_chat_charged_when_ai_mode_and_blocked_when_broke(client, monkeypatch):
    from app.models import Category, Product, ProductImage, ProductVariant
    cat = Category(name="Tops")
    db.session.add(cat)
    db.session.flush()
    p = Product(category_id=cat.id, name="Oxford Shirt", brand="Acme", price_minor=100000, tags=["formal"], description="d")
    p.variants.append(ProductVariant(sku="X1", size="M", color="white", stock_quantity=3))
    db.session.add(p)
    db.session.commit()
    h, uid = register(client)
    set_cfg(services={"ai_chat": {"cost": 4}})
    intent = dict(action="recommend", reply="", keywords=["formal"], category="", min_price_inr=0, max_price_inr=0,
                  colors=[], sizes=[], brands=[], occasion="", styles=[], outfit=False)
    outs = iter([intent, {"message": "Nice picks.", "picks": [{"product_id": p.id, "why": "Classic formal shirt."}]}] * 5)
    monkeypatch.setattr(ai_service, "_call_llm", lambda *a, **k: (next(outs), {"input_tokens": 1, "output_tokens": 1}))
    r = _chat(client, h)
    assert r.json["message"]["ai_generated"] and r.json["credits"]["charged"] == {"daily": 4}
    assert balances(uid) == (6, 0)
    assert _chat(client, h).status_code == 201 and balances(uid) == (2, 0)
    r = _chat(client, h)                                                                  # 2 left, cost 4
    assert r.status_code == 402 and r.json["details"] == {"needed": 4, "available": 2}
    assert balances(uid) == (2, 0)
    sessions = client.get("/api/v1/ai/sessions", headers=h).json["sessions"]
    assert len(sessions) == 2                                                             # only the two paid chats; the blocked one left no trace


# ---- credit packs ------------------------------------------------------------------------------------------
def _pack(credits=50, price=19900, name="Starter"):
    p = CreditPack(name=name, credits=credits, price_minor=price)
    db.session.add(p)
    db.session.commit()
    return p


def _pay(client, h, provider_order_id, outcome="success"):
    return client.post("/api/v1/payments/mock/pay", json={"provider_order_id": provider_order_id, "outcome": outcome}, headers=h)


def test_pack_purchase_grants_once_after_verified_payment(client):
    h, uid = register(client)
    pack = _pack()
    assert client.get("/api/v1/wallet/packs").json["packs"][0]["credits"] == 50
    pay = client.post(f"/api/v1/wallet/packs/{pack.id}/purchase", headers=h).json["payment"]
    assert pay["purpose"] == "credit_pack" and pay["amount_minor"] == 19900
    assert balances(uid)[1] == 0                                                          # nothing before payment
    assert _pay(client, h, pay["provider_order_id"]).json["result"] == "paid"
    assert balances(uid)[1] == 50
    assert _pay(client, h, pay["provider_order_id"]).status_code == 409                  # no pending payment left
    tx = [t for t in ledger(uid, "super")]
    assert len(tx) == 1 and tx[0].transaction_type == "purchase" and tx[0].amount == 50


def test_pack_webhook_signature_duplicates_failures_and_snapshot(client):
    from app.models import Payment
    h, uid = register(client)
    pack = _pack(credits=50, price=19900)
    pay = client.post(f"/api/v1/wallet/packs/{pack.id}/purchase", headers=h).json["payment"]
    p = Payment.query.filter_by(provider_order_id=pay["provider_order_id"]).first()
    sign = payment_service.get_provider().sign

    def ev(eid, etype="payment.captured", amount=None):
        return json.dumps({"id": eid, "type": etype, "data": {"provider_order_id": p.provider_order_id, "provider_payment_id": "x",
                                                              "amount_minor": amount or p.amount_minor, "currency": "INR"}}).encode()

    raw = ev("e1")
    assert client.post("/api/v1/payments/webhook", data=raw, headers={"X-Signature": "bad"}).status_code == 400
    bad = ev("e2", amount=100)
    assert client.post("/api/v1/payments/webhook", data=bad, headers={"X-Signature": sign(bad)}).json["result"] == "amount_mismatch"
    fail = ev("e3", etype="payment.failed")
    assert client.post("/api/v1/payments/webhook", data=fail, headers={"X-Signature": sign(fail)}).json["result"] == "failed"
    assert balances(uid)[1] == 0                                                          # none of the above granted credits

    pack.credits = 999                                                                    # admin edits the pack after purchase
    db.session.commit()
    retry = client.post(f"/api/v1/wallet/packs/{pack.id}/purchase", headers=h).json["payment"]
    p2 = Payment.query.filter_by(provider_order_id=retry["provider_order_id"]).first()
    pack.credits = 1
    db.session.commit()
    raw2 = json.dumps({"id": "e4", "type": "payment.captured", "data": {
        "provider_order_id": p2.provider_order_id, "provider_payment_id": "y", "amount_minor": p2.amount_minor, "currency": "INR"}}).encode()
    for _ in range(3):
        client.post("/api/v1/payments/webhook", data=raw2, headers={"X-Signature": sign(raw2)})
    assert balances(uid)[1] == 999                                                        # snapshot at purchase, granted once


# ---- subscriptions -----------------------------------------------------------------------------------------
def _plan(freq="renewal", credits=100, price=49900, interval="month", name="Plus"):
    p = SubscriptionPlan(name=name, price_minor=price, billing_interval=interval, super_credit_amount=credits,
                         grant_frequency=freq, benefits=["x"])
    db.session.add(p)
    db.session.commit()
    return p


def _subscribe(client, h, plan, outcome="success"):
    r = client.post("/api/v1/subscriptions/checkout", json={"plan_id": plan.id}, headers=h)
    assert r.status_code == 201, r.json
    return _pay(client, h, r.json["payment"]["provider_order_id"], outcome)


def test_subscription_activation_only_after_verified_payment(client, clock):
    h, uid = register(client)
    plan = _plan()
    r = client.post("/api/v1/subscriptions/checkout", json={"plan_id": plan.id}, headers=h)
    assert client.get("/api/v1/subscriptions/me", headers=h).json["subscription"] is None      # pending is not active
    assert balances(uid)[1] == 0
    _pay(client, h, r.json["payment"]["provider_order_id"], "failure")
    assert UserSubscription.query.one().status == "incomplete" and balances(uid)[1] == 0
    assert _subscribe(client, h, plan).json["result"] == "paid"
    sub = client.get("/api/v1/subscriptions/me", headers=h).json["subscription"]
    assert sub["status"] == "active" and sub["plan"]["name"] == "Plus"
    assert balances(uid)[1] == 100 and [t.transaction_type for t in ledger(uid, "super")] == ["subscription"]
    assert UserSubscription.query.count() == 1                                                    # reused the same row


def test_subscription_renewal_extends_and_blocks_plan_switch(client, clock):
    h, uid = register(client)
    plus, pro = _plan(), _plan(name="Pro", credits=300, price=99900)
    _subscribe(client, h, plus)
    end1 = UserSubscription.query.one().current_period_end
    assert client.post("/api/v1/subscriptions/checkout", json={"plan_id": pro.id}, headers=h).status_code == 409
    _subscribe(client, h, plus)                                                                   # renew early
    db.session.expire_all()
    sub = UserSubscription.query.one()
    assert sub.current_period_end == end1 + timedelta(days=30) and balances(uid)[1] == 200       # +100 per paid period
    assert client.post("/api/v1/subscriptions/checkout", json={"plan_id": 9999}, headers=h).status_code == 404


def test_cancel_keeps_access_until_period_end_then_closes(client, clock):
    h, uid = register(client)
    _subscribe(client, h, _plan())
    sub = client.post("/api/v1/subscriptions/cancel", headers=h).json["subscription"]
    assert sub["status"] == "active" and sub["cancel_at"] == sub["current_period_end"]
    assert subscription_service.expire_due(clock[0] + timedelta(days=10)) == 0
    clock[0] = T0 + timedelta(days=31)
    assert jobs.subscription_maintenance(clock[0]) == {"subscriptions_closed": 1}
    assert UserSubscription.query.one().status == "cancelled"
    assert client.get("/api/v1/subscriptions/me", headers=h).json["subscription"] is None
    assert client.post("/api/v1/subscriptions/cancel", headers=h).status_code == 404


def test_daily_subscription_grants_once_per_period_until_it_ends(client, clock):
    _, uid = register(client)
    plan = _plan(freq="daily", credits=20)
    h = {"Authorization": client.post("/api/v1/auth/login", json={"email": "w@example.com", "password": "Passw0rdX"}).json["access_token"]}
    h = {"Authorization": f"Bearer {h['Authorization']}"}
    _subscribe(client, h, plan)
    assert balances(uid)[1] == 20                                                                 # today's grant on activation
    for _ in range(3):
        wallet_service.ensure_current(uid, clock[0])
    db.session.commit()
    assert balances(uid)[1] == 20
    clock[0] = T0 + timedelta(days=1)
    wallet_service.ensure_current(uid, clock[0])
    wallet_service.ensure_current(uid, clock[0])
    db.session.commit()
    assert balances(uid)[1] == 40                                                                 # accumulates, one per day
    clock[0] = T0 + timedelta(days=45)                                                            # subscription over
    wallet_service.ensure_current(uid, clock[0])
    db.session.commit()
    assert balances(uid)[1] == 40
    assert wallet_service.reconcile(Wallet.query.filter_by(user_id=uid).first()) == {}


def test_subscription_webhook_duplicate_does_not_double_grant(client, clock):
    from app.models import Payment
    h, uid = register(client)
    plan = _plan()
    pay = client.post("/api/v1/subscriptions/checkout", json={"plan_id": plan.id}, headers=h).json["payment"]
    p = Payment.query.filter_by(provider_order_id=pay["provider_order_id"]).first()
    raw = json.dumps({"id": "same-event", "type": "payment.captured", "data": {
        "provider_order_id": p.provider_order_id, "provider_payment_id": "z", "amount_minor": p.amount_minor, "currency": "INR"}}).encode()
    sig = payment_service.get_provider().sign(raw)
    results = [client.post("/api/v1/payments/webhook", data=raw, headers={"X-Signature": sig}).json["result"] for _ in range(3)]
    assert results == ["paid", "duplicate", "duplicate"] and balances(uid)[1] == 100


# ---- admin -------------------------------------------------------------------------------------------------
def test_admin_endpoints_are_admin_only(client):
    h, _ = register(client)
    for method, url, body in [("get", "/api/v1/admin/settings/credits", None), ("put", "/api/v1/admin/settings/credits", {}),
                              ("post", "/api/v1/admin/credit-packs", {}), ("post", "/api/v1/admin/plans", {}),
                              ("get", "/api/v1/admin/audit-logs", None), ("post", "/api/v1/admin/users/1/wallet/adjust", {}),
                              ("get", "/api/v1/admin/users/1/wallet", None)]:
        assert getattr(client, method)(url, json=body, headers=h).status_code == 403, url


def test_admin_credit_settings_validation_persistence_and_audit(client, clock):
    admin = make_admin(client)
    _, uid = register(client, "u@example.com")
    bad = client.put("/api/v1/admin/settings/credits", headers=admin, json={
        "daily_allowance": -1, "reset_timezone": "Mars/Base", "reset_hour": 24, "spend_priority": "x",
        "services": {"ai_chat": {"cost": "free", "credit_types": ["gold"]}, "nope": {"cost": 1}}, "extra": 1})
    assert bad.status_code == 400 and len(bad.json["details"]) == 8
    ok = client.put("/api/v1/admin/settings/credits", headers=admin, json={
        "daily_allowance": 5, "reset_timezone": "UTC", "reset_hour": 0, "spend_priority": "super_first",
        "services": {"ai_chat": {"cost": 2, "credit_types": ["super"]}}})
    assert ok.status_code == 200
    s = client.get("/api/v1/admin/settings/credits", headers=admin).json["settings"]
    assert s["daily_allowance"] == 5 and s["services"]["ai_chat"] == {"cost": 2, "credit_types": ["super"]}
    wallet_service.ensure_current(uid, clock[0])                                                  # new allowance applies to new grants
    db.session.commit()
    assert balances(uid)[0] == 5
    log = AuditLog.query.filter_by(action="settings.credits.update").one()
    assert log.details["before"]["daily_allowance"] == 10 and log.details["after"]["daily_allowance"] == 5


def test_admin_manages_packs_and_plans_with_validation(client):
    admin = make_admin(client)
    assert client.post("/api/v1/admin/credit-packs", headers=admin, json={"name": "A", "credits": 0, "price_minor": 1}).status_code == 400
    pid = client.post("/api/v1/admin/credit-packs", headers=admin, json={"name": "Big", "credits": 500, "price_minor": 79900}).json["pack"]["id"]
    assert client.put(f"/api/v1/admin/credit-packs/{pid}", headers=admin, json={"name": "Big", "credits": 500, "price_minor": 79900, "is_active": False}).json["pack"]["is_active"] is False
    assert client.get("/api/v1/wallet/packs").json["packs"] == []                                 # inactive packs are hidden
    plan = {"name": "Gold", "price_minor": 99900, "super_credit_amount": 30, "grant_frequency": "daily", "billing_interval": "year"}
    assert client.post("/api/v1/admin/plans", headers=admin, json={**plan, "grant_frequency": "hourly"}).status_code == 400
    assert client.post("/api/v1/admin/plans", headers=admin, json=plan).status_code == 201
    assert client.get("/api/v1/subscriptions/plans").json["plans"][0]["name"] == "Gold"
    assert AuditLog.query.filter(AuditLog.action.like("pack.%") | AuditLog.action.like("plan.%")).count() == 3


def test_admin_wallet_adjustment_is_audited_and_safe(client, clock):
    admin = make_admin(client)
    _, uid = register(client, "t@example.com")
    url = f"/api/v1/admin/users/{uid}/wallet/adjust"
    assert client.post(url, headers=admin, json={"credit_type": "super", "amount": 25, "reason": ""}).status_code == 400
    assert client.post(url, headers=admin, json={"credit_type": "super", "amount": 0, "reason": "none"}).status_code == 400
    assert client.post(url, headers=admin, json={"credit_type": "super", "amount": -1, "reason": "oops"}).status_code == 409   # would go negative
    r = client.post(url, headers=admin, json={"credit_type": "super", "amount": 25, "reason": "Goodwill for delay"})
    assert r.status_code == 201 and r.json["transaction"]["transaction_type"] == "adjustment"
    assert client.post(url, headers=admin, json={"credit_type": "super", "amount": -5, "reason": "Correction"}).status_code == 201
    assert balances(uid)[1] == 20
    view = client.get(f"/api/v1/admin/users/{uid}/wallet", headers=admin).json
    assert view["ledger_mismatch"] == {} and view["wallet"]["super"]["balance"] == 20
    logs = AuditLog.query.filter_by(action="wallet.adjust").all()
    assert len(logs) == 2 and logs[0].details["reason"] == "Goodwill for delay" and logs[0].target_id == str(uid)
    assert client.post("/api/v1/admin/users/99999/wallet/adjust", headers=admin, json={"credit_type": "super", "amount": 1, "reason": "abc"}).status_code == 404


# ---- jobs --------------------------------------------------------------------------------------------------
def test_maintenance_job_is_idempotent_and_covers_all_customers(client, clock):
    ids = [register(client, f"j{i}@example.com")[1] for i in range(3)]
    make_admin(client)
    r1 = jobs.credit_maintenance(clock[0])
    r2 = jobs.credit_maintenance(clock[0])
    assert r1["wallets"] == 3 and r1["failed"] == 0 and r2["failed"] == 0
    assert all(balances(i) == (10, 0) for i in ids) and DailyCreditGrant.query.count() == 3
    clock[0] = T0 + timedelta(days=1)
    jobs.credit_maintenance(clock[0])
    assert all(balances(i) == (10, 0) for i in ids) and DailyCreditGrant.query.count() == 6
    for i in ids:
        assert wallet_service.reconcile(Wallet.query.filter_by(user_id=i).first()) == {}


def test_run_all_isolates_failures(client, monkeypatch):
    register(client)
    monkeypatch.setattr(jobs, "subscription_maintenance", lambda now=None: 1 / 0)
    out = jobs.run_all()
    assert out["subscriptions"] == {"error": True} and "wallets" in out["credits"] and "orders_released" in out["orders"]
