from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import create_access_token, get_jwt, jwt_required
from marshmallow import ValidationError

from ..extensions import db, limiter
from ..models import TokenBlocklist, User
from ..schemas.auth import LoginSchema, RegisterSchema, validate_password
from ..schemas.profile import ForgotSchema, ResetSchema, TokenSchema
from ..services import rewards_service
from ..services.email_service import send_email
from ..services.token_service import make_reset_token, make_verify_token, read_reset_token, read_verify_token
from ..utils.auth import current_user

bp = Blueprint("auth", __name__, url_prefix="/api/v1/auth")

# Checked when the email is unknown so response timing does not reveal account existence.
_DUMMY = User()
_DUMMY.set_password("dummy-password")


def _frontend(path):
    return current_app.config["FRONTEND_URL"].rstrip("/") + path


def _send_verification(user):
    link = _frontend(f"/verify-email?token={make_verify_token(user)}")
    send_email(user.email, "Verify your email", f"Hi {user.name},\n\nConfirm your email: {link}\n")


def _token_response(user, status=200):
    token = create_access_token(identity=str(user.id))
    return jsonify(access_token=token, user=user.to_dict()), status


@bp.post("/register")
@limiter.limit("10/hour")
def register():
    try:
        data = RegisterSchema().load(request.get_json(silent=True) or {})
    except ValidationError as e:
        return jsonify(error="Validation failed", details=e.messages), 400

    email = data["email"].strip().lower()
    if User.query.filter_by(email=email).first():
        return jsonify(error="Validation failed", details={"email": ["Email already registered."]}), 409

    # Self-registration is always a customer; role is never accepted from the client.
    user = User(name=data["name"].strip(), email=email, phone=data["phone"], role="customer")
    user.set_password(data["password"])
    db.session.add(user)
    db.session.flush()
    rewards_service.attach_referral(user, data.get("referral_code"))
    db.session.commit()
    _send_verification(user)
    return _token_response(user, 201)


@bp.post("/login")
@limiter.limit("10/minute")
def login():
    try:
        data = LoginSchema().load(request.get_json(silent=True) or {})
    except ValidationError as e:
        return jsonify(error="Validation failed", details=e.messages), 400

    user = User.query.filter_by(email=data["email"].strip().lower()).first()
    ok = (user or _DUMMY).check_password(data["password"])
    if not user or not ok or not user.is_active:
        return jsonify(error="Invalid email or password"), 401
    return _token_response(user)


@bp.post("/logout")
@jwt_required()
def logout():
    db.session.add(TokenBlocklist(jti=get_jwt()["jti"]))
    db.session.commit()
    return jsonify(message="Logged out")


@bp.get("/me")
@jwt_required()
def me():
    user = current_user()
    if user is None or not user.is_active:
        return jsonify(error="Account unavailable"), 401
    return jsonify(user=user.to_dict())


def _load(schema):
    try:
        return schema().load(request.get_json(silent=True) or {}), None
    except ValidationError as e:
        return None, (jsonify(error="Validation failed", details=e.messages), 400)


@bp.post("/forgot-password")
@limiter.limit("5/hour")
def forgot_password():
    data, err = _load(ForgotSchema)
    if err:
        return err
    user = User.query.filter_by(email=data["email"].strip().lower()).first()
    if user and user.is_active:
        link = _frontend(f"/reset-password?token={make_reset_token(user)}")
        send_email(user.email, "Reset your password", f"Reset link (valid 1 hour): {link}\n")
    # Same response either way: do not reveal which emails are registered.
    return jsonify(message="If that email is registered, a reset link has been sent.")


@bp.post("/reset-password")
@limiter.limit("10/hour")
def reset_password():
    data, err = _load(ResetSchema)
    if err:
        return err
    try:
        validate_password(data["password"])
    except ValidationError as e:
        return jsonify(error="Validation failed", details={"password": e.messages}), 400
    payload = read_reset_token(data["token"])
    user = db.session.get(User, payload["id"]) if payload else None
    if not user or not user.is_active or user.password_hash[-12:] != payload["h"]:
        return jsonify(error="This reset link is invalid or has expired."), 400
    user.set_password(data["password"])
    db.session.commit()
    return jsonify(message="Password updated. You can now log in.")


@bp.post("/verify-email")
@limiter.limit("20/hour")
def verify_email():
    data, err = _load(TokenSchema)
    if err:
        return err
    payload = read_verify_token(data["token"])
    user = db.session.get(User, payload["id"]) if payload else None
    if not user or user.email != payload["e"]:
        return jsonify(error="This verification link is invalid or has expired."), 400
    user.is_verified = True
    db.session.commit()
    return jsonify(message="Email verified.")


@bp.post("/resend-verification")
@jwt_required()
@limiter.limit("5/hour")
def resend_verification():
    user = current_user()
    if not user.is_verified:
        _send_verification(user)
    return jsonify(message="Verification email sent." if not user.is_verified else "Already verified.")
