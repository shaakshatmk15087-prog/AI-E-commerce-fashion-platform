import pytest

from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.models import User


@pytest.fixture()
def client():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.session.remove()
        db.drop_all()


def reg(client, email="a@example.com", password="Passw0rdX", **extra):
    return client.post("/api/v1/auth/register", json={"name": "A", "email": email, "password": password, **extra})


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_register_login_me_logout(client):
    r = reg(client)
    assert r.status_code == 201
    assert "password" not in str(r.json) and r.json["user"]["role"] == "customer"
    login = client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "Passw0rdX"})
    token = login.json["access_token"]
    assert client.get("/api/v1/auth/me", headers=auth(token)).json["user"]["email"] == "a@example.com"
    assert client.post("/api/v1/auth/logout", headers=auth(token)).status_code == 200
    assert client.get("/api/v1/auth/me", headers=auth(token)).status_code == 401  # revoked


def test_invalid_credentials(client):
    reg(client)
    assert client.post("/api/v1/auth/login", json={"email": "a@example.com", "password": "wrong"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "no@example.com", "password": "x"}).status_code == 401


def test_duplicate_and_weak_password(client):
    reg(client)
    assert reg(client).status_code == 409
    assert reg(client, email="b@example.com", password="short").status_code == 400


def test_cannot_self_assign_admin(client):
    r = reg(client, email="x@example.com", role="admin")
    assert r.status_code == 400 or r.json["user"]["role"] == "customer"


def test_customer_blocked_from_admin_then_allowed_after_promotion(client):
    token = reg(client).json["access_token"]
    assert client.get("/api/v1/admin/users", headers=auth(token)).status_code == 403
    assert client.get("/api/v1/admin/users").status_code == 401
    u = User.query.filter_by(email="a@example.com").first()
    u.role = "admin"
    db.session.commit()
    assert client.get("/api/v1/admin/users", headers=auth(token)).status_code == 200
