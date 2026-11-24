from flask import current_app
from itsdangerous import BadData, URLSafeTimedSerializer

RESET_MAX_AGE = 60 * 60  # 1 hour
VERIFY_MAX_AGE = 60 * 60 * 48


def _ser(salt):
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt=salt)


def make_reset_token(user):
    # Embeds a slice of the current password hash, so the token dies once the password changes (single use).
    return _ser("pw-reset").dumps({"id": user.id, "h": user.password_hash[-12:]})


def read_reset_token(token):
    try:
        return _ser("pw-reset").loads(token, max_age=RESET_MAX_AGE)
    except BadData:
        return None


def make_verify_token(user):
    return _ser("email-verify").dumps({"id": user.id, "e": user.email})


def read_verify_token(token):
    try:
        return _ser("email-verify").loads(token, max_age=VERIFY_MAX_AGE)
    except BadData:
        return None
