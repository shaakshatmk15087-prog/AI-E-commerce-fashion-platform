from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt, jwt_required
from marshmallow import ValidationError

from ..extensions import db
from ..models import FashionProfile
from ..schemas.profile import AccountSchema, DeleteAccountSchema, FashionSchema
from ..services import account_service
from ..utils.auth import current_user

bp = Blueprint("profile", __name__, url_prefix="/api/v1/profile")


def _load(schema):
    try:
        return schema().load(request.get_json(silent=True) or {}, unknown="raise"), None
    except ValidationError as e:
        return None, (jsonify(error="Validation failed", details=e.messages), 400)


@bp.get("")
@jwt_required()
def get_profile():
    return jsonify(user=current_user().to_dict())


@bp.put("")
@jwt_required()
def update_profile():
    data, err = _load(AccountSchema)
    if err:
        return err
    user = current_user()
    for k, v in data.items():
        setattr(user, k, v.strip() if isinstance(v, str) else v)
    db.session.commit()
    return jsonify(user=user.to_dict())


@bp.get("/fashion")
@jwt_required()
def get_fashion():
    fp = FashionProfile.query.filter_by(user_id=current_user().id).first()
    return jsonify(fashion=fp.to_dict() if fp else FashionProfile().to_dict())


@bp.put("/fashion")
@jwt_required()
def put_fashion():
    data, err = _load(FashionSchema)
    if err:
        return err
    user = current_user()
    fp = FashionProfile.query.filter_by(user_id=user.id).first() or FashionProfile(user_id=user.id)
    for k, v in data.items():
        setattr(fp, k, v)
    db.session.add(fp)
    db.session.commit()
    return jsonify(fashion=fp.to_dict())


@bp.delete("/fashion")
@jwt_required()
def delete_fashion():
    FashionProfile.query.filter_by(user_id=current_user().id).delete()
    db.session.commit()
    return jsonify(message="Fashion profile deleted.")


@bp.get("/export")
@jwt_required()
def export_my_data():
    """Download everything we hold about you (GDPR/DPDP-style access request)."""
    resp = jsonify(account_service.export_data(current_user()))
    resp.headers["Content-Disposition"] = 'attachment; filename="my-data.json"'
    return resp


@bp.post("/delete-account")
@jwt_required()
def delete_my_account():
    data, err = _load(DeleteAccountSchema)
    if err:
        return err
    if data["confirm"] != "DELETE":
        return jsonify(error="Validation failed", details={"confirm": ['Type "DELETE" to confirm.']}), 400
    account_service.delete_account(current_user(), data["password"], get_jwt()["jti"])
    db.session.commit()
    return jsonify(message="Your account has been deleted.")
