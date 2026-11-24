import re

import pytest

from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.services import email_service


@pytest.fixture()
def client():
    app = create_app(TestConfig)
    email_service.outbox.clear()
    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.session.remove()
        db.drop_all()


def reg(client):
    r = client.post("/api/v1/auth/register", json={"name": "A", "email": "a@example.com", "password": "Passw0rdX"})
    return {"Authorization": f"Bearer {r.json['access_token']}"}


def token_from_outbox(subject):
    mail = next(m for m in reversed(email_service.outbox) if m["subject"] == subject)
    return re.search(r"token=([^\s]+)", mail["body"]).group(1)


def test_email_verification(client):
    h = reg(client)
    assert client.get("/api/v1/auth/me", headers=h).json["user"]["is_verified"] is False
    t = token_from_outbox("Verify your email")
    assert client.post("/api/v1/auth/verify-email", json={"token": "bad"}).status_code == 400
    assert client.post("/api/v1/auth/verify-email", json={"token": t}).status_code == 200
    assert client.get("/api/v1/auth/me", headers=h).json["user"]["is_verified"] is True


def test_password_reset_flow_and_single_use(client):
    reg(client)
    n = len(email_service.outbox)
    r = client.post("/api/v1/auth/forgot-password", json={"email": "nobody@example.com"})
    assert r.status_code == 200 and len(email_service.outbox) == n  # no enumeration, no mail
    client.post("/api/v1/auth/forgot-password", json={"email": "a@example.com"})
    t = token_from_outbox("Reset your password")
    assert client.post("/api/v1/auth/reset-password", json={"token": t, "password": "weak"}).status_code == 400
    assert client.post("/api/v1/auth/reset-password", json={"token": t, "password": "NewPassw0rd"}).status_code == 200
    assert client.post("/api/v1/auth/reset-password", json={"token": t, "password": "Another1Pass"}).status_code == 400  # reused
    assert client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "NewPassw0rd"}).status_code == 200
    assert client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "Passw0rdX"}).status_code == 401


def test_account_update_ignores_privileged_fields(client):
    h = reg(client)
    r = client.put("/api/v1/profile", json={"name": "New Name", "phone": "999"}, headers=h)
    assert r.json["user"]["name"] == "New Name"
    assert client.put("/api/v1/profile", json={"role": "admin"}, headers=h).status_code == 400
    assert client.get("/api/v1/auth/me", headers=h).json["user"]["role"] == "customer"


def test_fashion_profile_crud_and_validation(client):
    h = reg(client)
    assert client.get("/api/v1/profile/fashion", headers=h).json["fashion"]["preferred_styles"] == []
    body = {"preferred_styles": ["casual"], "budget_min_minor": 50000, "budget_max_minor": 200000,
            "size_preferences": {"top": "M"}}
    r = client.put("/api/v1/profile/fashion", json=body, headers=h)
    assert r.status_code == 200 and r.json["fashion"]["preferred_styles"] == ["casual"]
    assert client.get("/api/v1/profile/fashion", headers=h).json["fashion"]["size_preferences"] == {"top": "M"}
    bad = client.put("/api/v1/profile/fashion", json={"budget_min_minor": 9, "budget_max_minor": 1}, headers=h)
    assert bad.status_code == 400
    assert client.put("/api/v1/profile/fashion", json={"budget_min_minor": -5}, headers=h).status_code == 400
    assert client.delete("/api/v1/profile/fashion", headers=h).status_code == 200
    assert client.get("/api/v1/profile/fashion", headers=h).json["fashion"]["preferred_styles"] == []


def test_profile_requires_auth(client):
    assert client.get("/api/v1/profile/fashion").status_code == 401
