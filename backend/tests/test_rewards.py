import time

import pytest

from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.models import (Address, AuditLog, Notification, Order, Referral, RewardAccount, RewardOffer, RewardTransaction, User, Wallet)
from app.services import rewards_service, wallet_service


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


def register(client, email, **extra):
    r = client.post("/api/v1/auth/register", json={"name": email.split("@")[0].title(), "email": email, "password": "Passw0rdX", **extra})
    return {"Authorization": f"Bearer {r.json['access_token']}"}, r.json["user"]["id"]


@pytest.fixture()
def admin(client):
    h, uid = register(client, "boss@example.com")
    User.query.filter_by(id=uid).update({"role": "admin"})
    db.session.commit()
    return h


def make_order(uid, total_minor=250000, status="shipped", payment="paid"):
    a = Address.query.filter_by(user_id=uid).first()
    if not a:
        a = Address(user_id=uid, recipient_name="R", phone="9999999", address_line_1="1 St", city="C", state="S", postal_code="123456")
        db.session.add(a)
        db.session.flush()
    o = Order(user_id=uid, address_id=a.id, order_number=f"ORD-T{uid}-{time.time_ns()}", subtotal_minor=total_minor,
              total_minor=total_minor, payment_status=payment, order_status=status)
    db.session.add(o)
    db.session.commit()
    return o.id


def deliver(client, admin, oid):
    return client.patch(f"/api/v1/admin/orders/{oid}/status", headers=admin, json={"order_status": "delivered"})


def points(uid):
    db.session.expire_all()
    a = RewardAccount.query.filter_by(user_id=uid).first()
    return a.balance if a else 0


def code_of(client, h):
    return client.get("/api/v1/rewards/balance", headers=h).json["rewards"]["referral_code"]


# ---- purchase points ---------------------------------------------------------------------------------------
def test_points_awarded_once_when_a_paid_order_is_delivered(client, admin):
    h, uid = register(client, "p@example.com")
    oid = make_order(uid, 250000)                                                        # INR 2,500 => 25 points
    assert points(uid) == 0
    assert deliver(client, admin, oid).status_code == 200 and points(uid) == 25
    rewards_service.on_order_delivered(db.session.get(Order, oid))                        # replayed event
    db.session.commit()
    assert points(uid) == 25 and RewardTransaction.query.filter_by(user_id=uid).count() == 1
    tx = client.get("/api/v1/rewards/transactions", headers=h).json
    assert tx["total"] == 1 and tx["transactions"][0]["points"] == 25 and tx["transactions"][0]["transaction_type"] == "earn"
    assert Notification.query.filter_by(user_id=uid, type="reward").count() == 1
    assert rewards_service.reconcile(uid) == {}


def test_no_points_for_unpaid_or_undelivered_orders(client, admin):
    _, uid = register(client, "u@example.com")
    unpaid = make_order(uid, payment="pending", status="confirmed")
    rewards_service.on_order_delivered(db.session.get(Order, unpaid))                     # not delivered, not paid
    shipped = db.session.get(Order, make_order(uid, 500000, status="shipped"))
    rewards_service.on_order_delivered(shipped)                                           # paid but not delivered yet
    refunded = db.session.get(Order, make_order(uid, 500000, status="delivered", payment="refunded"))
    rewards_service.on_order_delivered(refunded)                                          # refunded => never qualifies
    db.session.commit()
    assert points(uid) == 0
    assert client.patch(f"/api/v1/admin/orders/{unpaid}/status", headers=admin, json={"order_status": "delivered"}).status_code == 409


def test_points_rate_is_configurable_and_floors_to_whole_hundreds(client, admin):
    _, uid = register(client, "r@example.com")
    client.put("/api/v1/admin/settings/rewards", headers=admin, json={"points_per_100_inr": 2})
    deliver(client, admin, make_order(uid, 129999))                                       # INR 1,299.99 => 12 hundreds => 24
    assert points(uid) == 24
    client.put("/api/v1/admin/settings/rewards", headers=admin, json={"points_per_100_inr": 0})
    deliver(client, admin, make_order(uid, 900000))
    assert points(uid) == 24                                                              # earning switched off


# ---- referrals ------------------------------------------------------------------------------------------------
def test_referral_rewards_both_sides_only_after_first_delivery(client, admin):
    rh, ruid = register(client, "ref@example.com")
    code = code_of(client, rh)
    assert code and code_of(client, rh) == code                                           # stable
    fh, fuid = register(client, "friend@example.com", referral_code=code.lower())         # case-insensitive
    ref = Referral.query.one()
    assert ref.referrer_id == ruid and ref.referred_id == fuid and ref.status == "pending"
    assert points(ruid) == 0 and points(fuid) == 0                                        # signing up earns nothing

    first = make_order(fuid, 100000)                                                      # INR 1,000 => 10 purchase points
    deliver(client, admin, first)
    assert points(fuid) == 10 + 50 and points(ruid) == 100
    assert Referral.query.one().status == "rewarded"
    second = make_order(fuid, 100000)
    deliver(client, admin, second)
    assert points(fuid) == 70 and points(ruid) == 100                                     # no second referral bonus
    rewards_service.on_order_delivered(db.session.get(Order, first))
    db.session.commit()
    assert points(fuid) == 70 and points(ruid) == 100
    for u in (ruid, fuid):
        assert rewards_service.reconcile(u) == {}
    assert client.get("/api/v1/rewards/balance", headers=rh).json["rewards"]["referrals"] == {"total": 1, "rewarded": 1}


def test_invalid_self_and_repeat_referrals_are_ignored(client):
    h, uid = register(client, "me@example.com")
    code = code_of(client, h)
    register(client, "a@example.com", referral_code="NOSUCHCD")
    assert Referral.query.count() == 0
    assert client.post("/api/v1/auth/register", json={"name": "X", "email": "me@example.com", "password": "Passw0rdX", "referral_code": code}).status_code == 409
    assert rewards_service.attach_referral(db.session.get(User, uid), code) is None      # a user can't refer themselves
    register(client, "b@example.com", referral_code=code)
    b = User.query.filter_by(email="b@example.com").one()
    assert rewards_service.attach_referral(b, code) is None                               # one referral per referred user
    other, _ = register(client, "other@example.com")
    assert rewards_service.attach_referral(b, code_of(client, other)) is None
    assert Referral.query.count() == 1
    assert db.session.query(Referral).filter(Referral.referrer_id == Referral.referred_id).count() == 0


def test_referrer_cap_stops_further_rewards(client, admin):
    rh, ruid = register(client, "cap@example.com")
    code = code_of(client, rh)
    client.put("/api/v1/admin/settings/rewards", headers=admin, json={"max_rewarded_referrals": 1})
    a = register(client, "f1@example.com", referral_code=code)[1]
    b = register(client, "f2@example.com", referral_code=code)[1]
    deliver(client, admin, make_order(a, 100000))
    deliver(client, admin, make_order(b, 100000))
    assert points(ruid) == 100                                                            # only the first counted
    assert points(b) == 10                                                                # b still gets normal purchase points
    assert sorted(r.status for r in Referral.query.all()) == ["capped", "rewarded"]


def test_referral_not_rewarded_for_unpaid_delivery(client, admin):
    rh, ruid = register(client, "ref2@example.com")
    fuid = register(client, "fr@example.com", referral_code=code_of(client, rh))[1]
    rewards_service.on_order_delivered(db.session.get(Order, make_order(fuid, 100000, status="delivered", payment="pending")))
    db.session.commit()
    assert points(ruid) == 0 and Referral.query.one().status == "pending"


# ---- redemption -------------------------------------------------------------------------------------------------
def _offer(name="10 Super Credits", cost=100, credits=10, active=True):
    o = RewardOffer(name=name, points_cost=cost, super_credits=credits, is_active=active)
    db.session.add(o)
    db.session.commit()
    return o


def test_redeem_converts_points_to_super_credits_atomically(client, admin):
    h, uid = register(client, "red@example.com")
    client.get("/api/v1/wallet", headers=h)                                               # receives today's 10 Daily Credits
    offer = _offer()
    assert [o["name"] for o in client.get("/api/v1/rewards/offers").json["offers"]] == ["10 Super Credits"]
    r = client.post("/api/v1/rewards/redeem", headers=h, json={"offer_id": offer.id})
    assert r.status_code == 402 and r.json["details"] == {"needed": 100, "available": 0}  # nothing yet
    deliver(client, admin, make_order(uid, 1500000))                                      # INR 15,000 => 150 points
    assert points(uid) == 150
    r = client.post("/api/v1/rewards/redeem", headers=h, json={"offer_id": offer.id})
    assert r.status_code == 201 and r.json["redeemed"] == {"points_spent": 100, "super_credits": 10, "balance": 50}
    assert points(uid) == 50
    w = Wallet.query.filter_by(user_id=uid).first()
    assert w.super_balance == 10 and w.daily_balance == 10                                # points never touch Daily Credits
    assert client.post("/api/v1/rewards/redeem", headers=h, json={"offer_id": offer.id}).status_code == 402   # only 50 left
    assert points(uid) == 50 and wallet_service.reconcile(Wallet.query.filter_by(user_id=uid).first()) == {}
    assert rewards_service.reconcile(uid) == {}
    types = [t["transaction_type"] for t in client.get("/api/v1/rewards/transactions", headers=h).json["transactions"]]
    assert types == ["redeem", "earn"]


def test_inactive_offer_and_auth(client):
    h, _ = register(client, "x@example.com")
    off = _offer(active=False)
    assert client.post("/api/v1/rewards/redeem", headers=h, json={"offer_id": off.id}).status_code == 404
    assert client.get("/api/v1/rewards/offers").json["offers"] == []
    assert client.post("/api/v1/rewards/redeem", json={"offer_id": off.id}).status_code == 401
    assert client.get("/api/v1/rewards/balance").status_code == 401
    assert client.post("/api/v1/rewards/redeem", headers=h, json={"offer_id": off.id, "points": 1}).status_code == 400


def test_points_balance_cannot_go_negative_under_double_redeem(client, admin):
    h, uid = register(client, "dbl@example.com")
    offer = _offer(cost=100)
    deliver(client, admin, make_order(uid, 1000000))                                      # exactly 100 points
    codes = [client.post("/api/v1/rewards/redeem", headers=h, json={"offer_id": offer.id}).status_code for _ in range(3)]
    assert codes == [201, 402, 402] and points(uid) == 0


# ---- admin ---------------------------------------------------------------------------------------------------------
def test_admin_manages_offers_and_rewards_settings(client, admin):
    h, _ = register(client, "cust@example.com")
    assert client.put("/api/v1/admin/settings/rewards", headers=h, json={}).status_code == 403
    assert client.post("/api/v1/admin/reward-offers", headers=h, json={}).status_code == 403
    bad = client.put("/api/v1/admin/settings/rewards", headers=admin, json={"points_per_100_inr": -1, "referrer_points": "lots", "x": 1})
    assert bad.status_code == 400 and set(bad.json["details"]) == {"points_per_100_inr", "referrer_points", "x"}
    assert client.post("/api/v1/admin/reward-offers", headers=admin, json={"name": "Bad", "points_cost": 0, "super_credits": 5}).status_code == 400
    oid = client.post("/api/v1/admin/reward-offers", headers=admin, json={"name": "Big", "points_cost": 500, "super_credits": 80}).json["offer"]["id"]
    assert client.put(f"/api/v1/admin/reward-offers/{oid}", headers=admin, json={"name": "Big", "points_cost": 500, "super_credits": 80, "is_active": False}).json["offer"]["is_active"] is False
    assert client.get("/api/v1/rewards/offers").json["offers"] == []
    ok = client.put("/api/v1/admin/settings/rewards", headers=admin, json={"referrer_points": 150})
    assert ok.json["settings"]["referrer_points"] == 150 and ok.json["settings"]["referred_points"] == 50
    assert AuditLog.query.filter_by(action="settings.rewards.update").count() == 1
    assert AuditLog.query.filter(AuditLog.action.like("offer.%")).count() == 2
