from flask import Flask, jsonify

from .config import Config
from .extensions import cors, db, jwt, limiter, migrate
from .hardening import init_hardening


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    init_hardening(app)  # refuses to boot with an insecure production config

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    limiter.init_app(app)
    cors.init_app(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})

    from . import models  # noqa: F401  (registers models for migrations)
    from .models import TokenBlocklist
    from .routes import admin, admin_ops, ai, auth, catalog, health_bp, profile, shop, stylists, wallet
    from .services.errors import ShopError

    app.register_blueprint(health_bp)
    app.register_blueprint(profile.bp)
    app.register_blueprint(catalog.bp)
    app.register_blueprint(shop.bp)
    app.register_blueprint(ai.bp)
    app.register_blueprint(wallet.bp)
    app.register_blueprint(stylists.bp)
    app.register_blueprint(admin_ops.bp)
    app.register_blueprint(auth.bp)
    app.register_blueprint(admin.bp)

    @jwt.token_in_blocklist_loader
    def is_revoked(_header, payload):
        return TokenBlocklist.query.filter_by(jti=payload["jti"]).first() is not None

    @jwt.unauthorized_loader
    @jwt.invalid_token_loader
    def _unauth(_reason):
        return jsonify(error="Authentication required"), 401

    @jwt.expired_token_loader
    @jwt.revoked_token_loader
    def _expired(*_):
        return jsonify(error="Session expired or revoked"), 401

    @app.cli.command("run-jobs")
    def run_jobs_command():
        """Run credit/subscription/order maintenance once (for cron or Task Scheduler)."""
        from .tasks.jobs import run_all
        print(run_all())

    @app.errorhandler(ShopError)
    def _shop_error(e):
        db.session.rollback()  # discard anything the failed request had staged
        body = {"error": e.message}
        if e.details is not None:
            body["details"] = e.details
        return jsonify(body), e.status

    @app.errorhandler(429)
    def _rate(_e):
        return jsonify(error="Too many requests"), 429

    return app
