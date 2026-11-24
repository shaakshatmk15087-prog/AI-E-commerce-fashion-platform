import os
import threading
import time
from datetime import datetime, timedelta

import pytest
from sqlalchemy.exc import OperationalError

from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.models import (AuditLog, ChatSession, Consultation, CreditTransaction, Notification, Stylist, StylistAvailability, User, Wallet)
from app.services import consultation_service, settings_service, wallet_service
from app.tasks import jobs

T0 = datetime(2026, 11, 23, 10, 0)  # fake "now" (naive UTC)


def iso(dt):
    return dt.isoformat() + "Z"


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


def register(client, email):
    r = client.post("/api/v1/auth/register", json={"name": email.split("@")[0].title(), "email": email, "password": "Passw0rdX"})
    return {"Authorization": f"Bearer {r.json['access_token']}"}, r.json["user"]["id"]


def give_super(uid, n):
    wallet_service.grant(uid, "super", n, "grant", source_type="test", source_id=1, key=f"g:{uid}:{n}:{time.time_ns()}", description="t")
    db.session.commit()


def balances(uid):
    db.session.expire_all()
    w = Wallet.query.filter_by(user_id=uid).first()
    return (w.daily_balance, w.super_balance) if w else (0, 0)


def ledger(uid, ctype="super"):
    w = Wallet.query.filter_by(user_id=uid).first()
    return CreditTransaction.query.filter_by(wallet_id=w.id, credit_type=ctype).order_by(CreditTransaction.id).all()


class World:
    pass


def build_world(client, price=None, credits=100):
    w = World()
    w.admin, aid = register(client, "boss@example.com")
    User.query.filter_by(id=aid).update({"role": "admin"})
    db.session.commit()
    w.sty, w.sty_uid = register(client, "stella@example.com")
    r = client.post("/api/v1/admin/stylists", headers=w.admin, json={"user_id": w.sty_uid, "bio": "Editorial stylist", "expertise": ["formal"],
                                                                      "languages": ["English"], "is_approved": True, "price_credits_text": price})
    w.stylist_id = r.json["stylist"]["id"]
    w.cust, w.cust_uid = register(client, "cora@example.com")
    give_super(w.cust_uid, credits)
    return w


def add_slot(client, h, start, minutes=30):
    return client.post("/api/v1/stylist/availability", headers=h, json={"start_at": iso(start), "duration_minutes": minutes})


def make_slot(client, w, days=2, hours=0):
    r = add_slot(client, w.sty, T0 + timedelta(days=days, hours=hours))
    assert r.status_code == 201, r.json
    return r.json["slot"]["id"]


def book(client, h, slot_id, notes="Need help for a wedding"):
    return client.post("/api/v1/consultations", headers=h, json={"slot_id": slot_id, "notes": notes})


@pytest.fixture()
def world(client, clock):
    return build_world(client)


# ---- admin / stylist profiles ---------------------------------------------------------------------------------
def test_only_admin_creates_stylists_and_role_is_set(client, clock):
    admin, aid = register(client, "a@example.com")
    User.query.filter_by(id=aid).update({"role": "admin"})
    db.session.commit()
    h, uid = register(client, "s@example.com")
    cust, _ = register(client, "c@example.com")
    assert client.post("/api/v1/admin/stylists", headers=cust, json={"user_id": uid}).status_code == 403
    r = client.post("/api/v1/admin/stylists", headers=admin, json={"user_id": uid, "is_approved": True})
    assert r.status_code == 201 and db.session.get(User, uid).role == "stylist"
    assert client.post("/api/v1/admin/stylists", headers=admin, json={"user_id": uid}).status_code == 409
    assert client.post("/api/v1/admin/stylists", headers=admin, json={"user_id": aid}).status_code == 409   # admins can't be stylists
    assert client.post("/api/v1/admin/stylists", headers=admin, json={"user_id": 9999}).status_code == 400
    assert AuditLog.query.filter_by(action="stylist.create").count() == 1


def test_stylist_cannot_self_approve_or_reprice(client, world):
    me = client.get("/api/v1/stylist/profile", headers=world.sty).json["stylist"]
    assert me["is_approved"] is True
    r = client.put("/api/v1/stylist/profile", headers=world.sty, json={"bio": "New bio", "is_approved": False, "price_credits_text": 1})
    assert r.status_code == 400                                                       # unknown fields rejected
    r = client.put("/api/v1/stylist/profile", headers=world.sty, json={"bio": "New bio", "expertise": ["casual"], "is_available": True})
    assert r.status_code == 200 and r.json["stylist"]["bio"] == "New bio"
    assert client.get("/api/v1/stylist/profile", headers=world.cust).status_code == 403   # customers have no stylist console


def test_directory_visibility_and_pricing(client, world):
    make_slot(client, world)
    listing = client.get("/api/v1/stylists").json["stylists"]
    assert len(listing) == 1 and listing[0]["price_credits"] == 30 and listing[0]["next_slots"] == 1
    assert "email" not in listing[0]
    client.put(f"/api/v1/admin/stylists/{world.stylist_id}", headers=world.admin, json={"is_approved": False, "price_credits_text": 45})
    assert client.get("/api/v1/stylists").json["stylists"] == []
    assert client.get(f"/api/v1/stylists/{world.stylist_id}").status_code == 404
    client.put(f"/api/v1/admin/stylists/{world.stylist_id}", headers=world.admin, json={"is_approved": True, "price_credits_text": 45})
    assert client.get(f"/api/v1/stylists/{world.stylist_id}").json["stylist"]["price_credits"] == 45
    client.put(f"/api/v1/admin/stylists/{world.stylist_id}", headers=world.admin, json={"is_approved": True, "is_available": False})
    assert client.get("/api/v1/stylists").json["stylists"] == []


def test_availability_rules(client, world):
    assert add_slot(client, world.sty, T0 - timedelta(hours=1)).status_code == 400            # past
    sid = make_slot(client, world)
    assert add_slot(client, world.sty, T0 + timedelta(days=2, minutes=15)).status_code == 409  # overlaps
    assert add_slot(client, world.sty, T0 + timedelta(days=2, minutes=30)).status_code == 201  # back-to-back is fine
    assert client.post("/api/v1/stylist/availability", headers=world.sty, json={"start_at": iso(T0 + timedelta(days=3)), "duration_minutes": 5}).status_code == 400
    assert add_slot(client, world.cust, T0 + timedelta(days=4)).status_code == 403
    assert client.delete(f"/api/v1/stylist/availability/{sid}", headers=world.cust).status_code == 403
    other, _ = register(client, "o@example.com")
    assert client.get(f"/api/v1/stylists/{world.stylist_id}/availability").json["slots"][0]["id"] == sid
    book(client, world.cust, sid)
    assert client.delete(f"/api/v1/stylist/availability/{sid}", headers=world.sty).status_code == 409   # booked
    assert sid not in [s["id"] for s in client.get(f"/api/v1/stylists/{world.stylist_id}/availability").json["slots"]]


def test_min_notice_hides_and_blocks_near_slots(client, world):
    soon = add_slot(client, world.sty, T0 + timedelta(hours=1)).json["slot"]["id"]
    assert client.get(f"/api/v1/stylists/{world.stylist_id}/availability").json["slots"] == []
    assert book(client, world.cust, soon).status_code == 409
    assert balances(world.cust_uid)[1] == 100


# ---- booking ---------------------------------------------------------------------------------------------------
def test_quote_then_book_reserves_credits(client, world):
    sid = make_slot(client, world)
    q = client.post("/api/v1/consultations/quote", headers=world.cust, json={"slot_id": sid}).json["quote"]
    assert q["cost"] == 30 and q["sufficient"] and q["breakdown"] == {"super": 30} and q["policy"]["full_refund_hours"] == 24
    assert balances(world.cust_uid)[1] == 100                                           # quoting never spends
    r = book(client, world.cust, sid)
    assert r.status_code == 201 and r.json["consultation"]["status"] == "requested" and r.json["consultation"]["credit_cost"] == 30
    assert balances(world.cust_uid)[1] == 70
    assert [t.transaction_type for t in ledger(world.cust_uid)][-1] == "reservation"
    assert StylistAvailability.query.get(sid).status == "booked"
    n = Notification.query.filter_by(user_id=world.sty_uid).one()
    assert n.type == "consultation" and "Cora" in n.body


def test_stylist_specific_price_and_daily_credits_never_used(client, clock):
    w = build_world(client, price=45)
    sid = make_slot(client, w)
    assert book(client, w.cust, sid).json["consultation"]["credit_cost"] == 45 and balances(w.cust_uid)[1] == 55
    daily_only, uid = register(client, "daily@example.com")
    client.get("/api/v1/wallet", headers=daily_only)                                     # gets 10 Daily Credits
    sid2 = make_slot(client, w, days=3)
    r = book(client, daily_only, sid2)
    assert r.status_code == 402 and r.json["details"]["available"] == 0                  # consultations are Super-only
    assert StylistAvailability.query.get(sid2).status == "open" and Consultation.query.count() == 1   # slot not left claimed


def test_insufficient_credits_leaves_no_trace(client, clock):
    w = build_world(client, credits=10)
    sid = make_slot(client, w)
    r = book(client, w.cust, sid)
    assert r.status_code == 402 and r.json["details"] == {"needed": 30, "available": 10}
    assert Consultation.query.count() == 0 and StylistAvailability.query.get(sid).status == "open" and balances(w.cust_uid)[1] == 10


def test_only_customers_can_book_and_unavailable_stylists_refuse(client, world):
    sid = make_slot(client, world)
    assert book(client, world.sty, sid).status_code == 403
    assert book(client, world.admin, sid).status_code == 403
    assert client.post("/api/v1/consultations", headers=world.cust, json={"slot_id": 99999}).status_code == 404
    client.put(f"/api/v1/admin/stylists/{world.stylist_id}", headers=world.admin, json={"is_approved": True, "is_available": False})
    assert book(client, world.cust, sid).status_code == 409
    assert client.post("/api/v1/consultations", json={"slot_id": sid}).status_code == 401


def test_slot_cannot_be_double_booked(client, world):
    sid = make_slot(client, world)
    other, ouid = register(client, "other@example.com")
    give_super(ouid, 100)
    assert book(client, world.cust, sid).status_code == 201
    r = book(client, other, sid)
    assert r.status_code == 409 and balances(ouid)[1] == 100 and Consultation.query.count() == 1


def test_concurrent_bookings_of_one_slot_have_one_winner(tmp_path):
    class FileConfig(TestConfig):
        SQLALCHEMY_DATABASE_URI = os.getenv("TEST_DATABASE_URL") or f"sqlite:///{tmp_path / 'c.db'}"

    app = create_app(FileConfig)
    with app.app_context():
        db.create_all()
        c = app.test_client()
        w = build_world(c)
        slot = add_slot(c, w.sty, datetime.utcnow() + timedelta(days=2)).json["slot"]["id"]
        buyers = []
        for i in range(5):
            h, uid = register(c, f"buyer{i}@example.com")
            give_super(uid, 100)
            buyers.append((h["Authorization"], uid))
    results = []

    def worker(token, uid):
        with app.app_context():
            for _ in range(40):
                try:
                    r = app.test_client().post("/api/v1/consultations", headers={"Authorization": token}, json={"slot_id": slot})
                except OperationalError:
                    db.session.rollback()
                    time.sleep(0.05)
                    continue
                if r.status_code == 500:
                    db.session.rollback()
                    time.sleep(0.05)
                    continue
                results.append((uid, r.status_code))
                return
            results.append((uid, None))

    ts = [threading.Thread(target=worker, args=b) for b in buyers]
    [t.start() for t in ts]
    [t.join() for t in ts]
    with app.app_context():
        codes = [code for _, code in results]
        assert codes.count(201) == 1 and codes.count(409) == 4 and None not in codes, codes
        winner = next(uid for uid, code in results if code == 201)
        for uid, code in results:
            assert balances(uid)[1] == (70 if uid == winner else 100)                  # only the winner paid
        assert Consultation.query.count() == 1
        db.session.remove()
        db.drop_all()


# ---- lifecycle -------------------------------------------------------------------------------------------------
def booked(client, w, days=2):
    sid = make_slot(client, w, days=days)
    return book(client, w.cust, sid).json["consultation"]["id"]


def test_accept_opens_private_chat(client, world):
    cid = booked(client, world)
    stranger, _ = register(client, "nosy@example.com")
    msg = lambda h, t="hello": client.post(f"/api/v1/consultations/{cid}/messages", headers=h, json={"text": t})
    assert msg(world.cust).status_code == 409                                            # not accepted yet
    assert client.post(f"/api/v1/consultations/{cid}/accept", headers=world.cust).status_code == 403
    assert client.post(f"/api/v1/consultations/{cid}/accept", headers=world.sty).json["consultation"]["status"] == "accepted"
    assert client.post(f"/api/v1/consultations/{cid}/accept", headers=world.sty).status_code == 409   # not twice
    assert ChatSession.query.filter_by(consultation_id=cid, session_type="stylist").count() == 1
    assert msg(world.cust, "I need a wedding look").status_code == 201 and msg(world.sty, "Let's start").status_code == 201
    assert msg(world.cust, "   ").status_code == 400 and msg(world.cust, "x" * 1001).status_code == 400
    got = client.get(f"/api/v1/consultations/{cid}/messages", headers=world.cust).json
    assert [m["sender_type"] for m in got["messages"]] == ["customer", "stylist"]
    assert len(client.get(f"/api/v1/consultations/{cid}/messages?after={got['messages'][0]['id']}", headers=world.sty).json["messages"]) == 1
    assert client.get(f"/api/v1/consultations/{cid}/messages", headers=stranger).status_code == 404
    assert msg(stranger).status_code == 404
    assert client.get(f"/api/v1/consultations/{cid}", headers=stranger).status_code == 404
    assert client.get(f"/api/v1/consultations/{cid}/messages", headers=world.admin).status_code == 200     # admin may read
    assert msg(world.admin).status_code == 403                                                              # ...not post
    other_sty, ouid = register(client, "stella2@example.com")
    client.post("/api/v1/admin/stylists", headers=world.admin, json={"user_id": ouid, "is_approved": True})
    assert client.post(f"/api/v1/consultations/{cid}/complete", headers=other_sty).status_code == 404       # not their consultation


def test_decline_releases_everything_and_reopens_slot(client, world):
    cid = booked(client, world)
    assert balances(world.cust_uid)[1] == 70
    r = client.post(f"/api/v1/consultations/{cid}/decline", headers=world.sty)
    assert r.json["consultation"]["status"] == "declined" and r.json["consultation"]["refunded_credits"] == 30
    assert balances(world.cust_uid)[1] == 100
    assert [t.transaction_type for t in ledger(world.cust_uid)][-2:] == ["reservation", "release"]
    assert StylistAvailability.query.one().status == "open"
    assert Notification.query.filter_by(user_id=world.cust_uid, type="consultation").count() == 1
    assert wallet_service.reconcile(Wallet.query.filter_by(user_id=world.cust_uid).first()) == {}
    assert client.post(f"/api/v1/consultations/{cid}/cancel", headers=world.cust).status_code == 409


@pytest.mark.parametrize("actor,accept,hours_before,expected_refund", [
    ("cust", False, 100, 30),    # still only requested: always full
    ("cust", True, 100, 30),     # accepted, well before the window: full
    ("cust", True, 10, 15),      # accepted, inside 24h: 50%
    ("sty", True, 10, 30),       # stylist cancels late: customer still gets everything back
])
def test_cancellation_policy(client, world, clock, actor, accept, hours_before, expected_refund):
    sid = add_slot(client, world.sty, T0 + timedelta(hours=hours_before)).json["slot"]["id"]
    cid = book(client, world.cust, sid).json["consultation"]["id"]
    if accept:
        client.post(f"/api/v1/consultations/{cid}/accept", headers=world.sty)
    r = client.post(f"/api/v1/consultations/{cid}/cancel", headers=getattr(world, actor))
    assert r.status_code == 200 and r.json["consultation"]["status"] == "cancelled"
    assert r.json["consultation"]["refunded_credits"] == expected_refund
    assert balances(world.cust_uid)[1] == 70 + expected_refund
    assert wallet_service.reconcile(Wallet.query.filter_by(user_id=world.cust_uid).first()) == {}


def test_late_cancel_rounds_down_and_respects_admin_policy(client, clock):
    w = build_world(client, price=31)
    settings_service.save_section("consultations", settings_service.validate_section("consultations", {"late_cancel_refund_percent": 50}))
    db.session.commit()
    sid = add_slot(client, w.sty, T0 + timedelta(hours=10)).json["slot"]["id"]
    cid = book(client, w.cust, sid).json["consultation"]["id"]
    client.post(f"/api/v1/consultations/{cid}/accept", headers=w.sty)
    assert client.post(f"/api/v1/consultations/{cid}/cancel", headers=w.cust).json["consultation"]["refunded_credits"] == 15   # 31*50//100
    # now tighten the policy to 0% and check a fresh late cancel refunds nothing
    client.put("/api/v1/admin/settings/consultations", headers=w.admin, json={"late_cancel_refund_percent": 0})
    sid = add_slot(client, w.sty, T0 + timedelta(hours=12)).json["slot"]["id"]
    cid = book(client, w.cust, sid).json["consultation"]["id"]
    client.post(f"/api/v1/consultations/{cid}/accept", headers=w.sty)
    assert client.post(f"/api/v1/consultations/{cid}/cancel", headers=w.cust).json["consultation"]["refunded_credits"] == 0


def test_complete_only_after_start_then_settles_earnings(client, world, clock):
    cid = booked(client, world)
    assert client.post(f"/api/v1/consultations/{cid}/complete", headers=world.sty).status_code == 409   # not accepted
    client.post(f"/api/v1/consultations/{cid}/accept", headers=world.sty)
    assert client.post(f"/api/v1/consultations/{cid}/complete", headers=world.sty).status_code == 409   # before start
    clock[0] = T0 + timedelta(days=2, minutes=5)
    r = client.post(f"/api/v1/consultations/{cid}/complete", headers=world.sty)
    assert r.json["consultation"]["status"] == "completed"
    assert Consultation.query.get(cid).stylist_payout_credits == 21                       # 70% of 30
    assert balances(world.cust_uid)[1] == 70                                              # reservation stays spent
    e = client.get("/api/v1/stylist/earnings", headers=world.sty).json["earnings"]
    assert e["completed"] == 1 and e["earned_credits"] == 21 and e["share_percent"] == 70
    assert client.post(f"/api/v1/consultations/{cid}/complete", headers=world.sty).status_code == 409
    assert client.post(f"/api/v1/consultations/{cid}/cancel", headers=world.cust).status_code == 409   # can't undo a settled session
    assert client.post(f"/api/v1/consultations/{cid}/messages", headers=world.cust, json={"text": "late"}).status_code == 409
    assert balances(world.cust_uid)[1] == 70


def test_consultation_lists_are_role_scoped(client, world):
    cid = booked(client, world)
    assert [c["id"] for c in client.get("/api/v1/consultations", headers=world.cust).json["consultations"]] == [cid]
    assert client.get("/api/v1/consultations", headers=world.sty).json["consultations"] == []           # default view = as a customer
    assert [c["id"] for c in client.get("/api/v1/consultations?as=stylist", headers=world.sty).json["consultations"]] == [cid]
    other, _ = register(client, "z@example.com")
    assert client.get("/api/v1/consultations", headers=other).json["consultations"] == []
    assert len(client.get("/api/v1/admin/consultations", headers=world.admin).json["consultations"]) == 1
    assert client.get("/api/v1/admin/consultations", headers=world.cust).status_code == 403


# ---- scheduled maintenance -----------------------------------------------------------------------------------------
def test_unanswered_requests_expire_with_full_release(client, world, clock):
    cid = booked(client, world, days=5)
    assert jobs.consultation_maintenance(T0 + timedelta(hours=23))["consultations_expired"] == 0
    clock[0] = T0 + timedelta(hours=25)
    out = jobs.consultation_maintenance(clock[0])
    assert out["consultations_expired"] == 1
    c = Consultation.query.get(cid)
    assert c.status == "expired" and c.cancelled_by == "system" and c.refunded_credits == 30 and balances(world.cust_uid)[1] == 100
    assert StylistAvailability.query.one().status == "open"                                # still in the future => reopened
    assert jobs.consultation_maintenance(clock[0])["consultations_expired"] == 0           # idempotent


def test_started_but_unanswered_request_expires_and_slot_stays_closed(client, world, clock):
    cid = booked(client, world, days=1)
    clock[0] = T0 + timedelta(days=1, minutes=1)
    jobs.consultation_maintenance(clock[0])
    assert Consultation.query.get(cid).status == "expired" and balances(world.cust_uid)[1] == 100
    assert StylistAvailability.query.one().status == "booked"                              # past slot is not reopened


def test_reminders_are_idempotent_and_only_for_accepted(client, world, clock):
    cid = booked(client, world, days=1)
    client.post(f"/api/v1/consultations/{cid}/accept", headers=world.sty)
    clock[0] = T0 + timedelta(days=1) - timedelta(minutes=30)
    assert jobs.consultation_maintenance(clock[0])["reminders"] == 2
    assert jobs.consultation_maintenance(clock[0])["reminders"] == 0
    assert Notification.query.filter_by(type="reminder").count() == 2


# ---- notifications ------------------------------------------------------------------------------------------------
def test_notifications_are_private_and_markable(client, world):
    booked(client, world)
    r = client.get("/api/v1/notifications", headers=world.sty).json
    assert r["unread"] == 1 and r["notifications"][0]["title"] == "New consultation request"
    assert client.get("/api/v1/notifications", headers=world.cust).json["unread"] == 0
    assert client.get("/api/v1/notifications").status_code == 401
    client.post("/api/v1/notifications/read", headers=world.cust, json={})                 # other user can't clear mine
    assert client.get("/api/v1/notifications", headers=world.sty).json["unread"] == 1
    client.post("/api/v1/notifications/read", headers=world.sty, json={})
    assert client.get("/api/v1/notifications", headers=world.sty).json["unread"] == 0


# ---- admin settings ----------------------------------------------------------------------------------------------
def test_consultation_settings_validation_and_audit(client, world):
    assert client.get("/api/v1/admin/settings/consultations", headers=world.cust).status_code == 403
    bad = client.put("/api/v1/admin/settings/consultations", headers=world.admin,
                     json={"stylist_share_percent": 101, "late_cancel_refund_percent": -1, "request_expiry_hours": 0, "nope": 1})
    assert bad.status_code == 400 and set(bad.json["details"]) == {"stylist_share_percent", "late_cancel_refund_percent", "request_expiry_hours", "nope"}
    ok = client.put("/api/v1/admin/settings/consultations", headers=world.admin, json={"stylist_share_percent": 60})
    assert ok.json["settings"]["stylist_share_percent"] == 60 and ok.json["settings"]["cancel_full_refund_hours"] == 24
    assert AuditLog.query.filter_by(action="settings.consultations.update").one().details["after"]["stylist_share_percent"] == 60
    cid = booked(client, world)
    client.post(f"/api/v1/consultations/{cid}/accept", headers=world.sty)
    assert consultation_service.price_for(Stylist.query.one()) == 30
    assert settings_service.get_section("consultations")["stylist_share_percent"] == 60


def test_run_all_includes_consultation_job(client, world):
    assert "consultations_expired" in jobs.run_all()["consultations"]
