from flask import Blueprint, jsonify

health_bp = Blueprint("health", __name__)


@health_bp.get("/api/v1/health")
def health():
    """Liveness: the process is up."""
    return jsonify(status="ok")


@health_bp.get("/api/v1/health/ready")
def ready():
    """Readiness: the database answers. Use this for load-balancer/orchestrator checks."""
    from sqlalchemy import text

    from ..extensions import db
    try:
        db.session.execute(text("SELECT 1"))
    except Exception:
        return jsonify(status="unavailable"), 503
    return jsonify(status="ready")
