from functools import wraps

from flask import jsonify
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from ..extensions import db
from ..models import User
from ..services.errors import ShopError


def current_user():
    """The authenticated, ACTIVE user. A deactivated or deleted account's still-valid token is rejected here, so
    every endpoint that resolves the user is covered (not just the role-checked ones)."""
    user = db.session.get(User, int(get_jwt_identity()))
    if user is None or not user.is_active:
        raise ShopError("Account unavailable", 401)
    return user


def roles_required(*roles):
    """Server-side RBAC. The role is read from the DB, never from the client."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            verify_jwt_in_request()
            user = current_user()
            if user.role not in roles:
                return jsonify(error="Forbidden"), 403
            return fn(*args, **kwargs)

        return wrapper

    return decorator
