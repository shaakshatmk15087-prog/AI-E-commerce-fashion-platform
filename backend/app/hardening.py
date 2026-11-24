"""Production hardening: boot-time config validation, security headers, request ids, safe error responses, optional Sentry."""
import logging
import re
import uuid

from flask import g, jsonify, request
from werkzeug.exceptions import HTTPException

log = logging.getLogger(__name__)
_REQ_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


def validate_production_config(cfg):
    """Return a list of problems. In production the app refuses to start unless this is empty."""
    problems = []
    for key in ("SECRET_KEY", "JWT_SECRET_KEY"):
        v = cfg.get(key) or ""
        if v.startswith("dev-") or v.startswith("change-me") or len(v) < 32:
            problems.append(f"{key} must be a unique random value of at least 32 characters.")
    if cfg.get("SECRET_KEY") == cfg.get("JWT_SECRET_KEY"):
        problems.append("SECRET_KEY and JWT_SECRET_KEY must differ.")
    uri = cfg.get("SQLALCHEMY_DATABASE_URI", "")
    if not uri or uri.startswith("sqlite"):
        problems.append("DATABASE_URL must point at MySQL (SQLite is for local development only).")
    if cfg.get("PAYMENT_PROVIDER") == "mock" or cfg.get("MOCK_PAYMENTS_ENABLED"):
        if not cfg.get("ALLOW_INSECURE_MOCK_PAYMENTS"):
            problems.append("The mock payment provider is enabled. Real payments need a real provider; set "
                            "MOCK_PAYMENTS_ENABLED=false and PAYMENT_PROVIDER to a verified gateway (or, for a staging "
                            "environment only, ALLOW_INSECURE_MOCK_PAYMENTS=true).")
    if cfg.get("PAYMENT_WEBHOOK_SECRET", "").startswith("dev-") or len(cfg.get("PAYMENT_WEBHOOK_SECRET", "")) < 24:
        problems.append("PAYMENT_WEBHOOK_SECRET must be a unique secret of at least 24 characters.")
    origins = cfg.get("CORS_ORIGINS") or []
    if not origins or any(not o.startswith("https://") or "localhost" in o or "127.0.0.1" in o for o in origins):
        problems.append("CORS_ORIGINS must list only https:// production origins.")
    if not str(cfg.get("FRONTEND_URL", "")).startswith("https://"):
        problems.append("FRONTEND_URL must be an https:// URL (it is used in emailed links).")
    if str(cfg.get("RATELIMIT_STORAGE_URI", "memory://")).startswith("memory"):
        problems.append("RATELIMIT_STORAGE_URI must be a shared store such as redis:// (per-process memory makes limits ineffective).")
    return problems


def init_hardening(app):
    cfg = app.config
    if cfg.get("APP_ENV") == "production":
        problems = validate_production_config(cfg)
        if problems:
            raise RuntimeError("Refusing to start with an insecure production configuration:\n - " + "\n - ".join(problems))

    if cfg.get("TRUST_PROXY_HOPS", 0) > 0:  # behind nginx/ALB: use the real client IP (rate limits, audit)
        from werkzeug.middleware.proxy_fix import ProxyFix
        h = cfg["TRUST_PROXY_HOPS"]
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=h, x_proto=h, x_host=h)

    class RequestIdFilter(logging.Filter):
        def filter(self, record):
            record.request_id = getattr(g, "request_id", "-") if g else "-"
            return True

    logging.basicConfig(level=cfg.get("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s [%(request_id)s] %(name)s: %(message)s")
    for h in logging.getLogger().handlers:
        h.addFilter(RequestIdFilter())

    @app.before_request
    def _request_id():
        rid = request.headers.get("X-Request-ID", "")
        g.request_id = rid if _REQ_ID.match(rid) else uuid.uuid4().hex

    @app.after_request
    def _headers(resp):
        resp.headers["X-Request-ID"] = getattr(g, "request_id", "-")
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        if request.path.startswith("/api/"):
            resp.headers.setdefault("Cache-Control", "no-store")  # responses are per-user; never cache them
            resp.headers.setdefault("Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'")
        if cfg.get("APP_ENV") == "production":
            resp.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
        return resp

    @app.errorhandler(HTTPException)
    def _http_error(e):
        return jsonify(error=e.name if e.code != 413 else "Request too large", request_id=getattr(g, "request_id", None)), e.code

    @app.errorhandler(Exception)
    def _unhandled(e):
        if app.testing:
            raise e  # surface bugs in tests instead of hiding them behind a 500 page
        log.exception("Unhandled error on %s %s", request.method, request.path)
        return jsonify(error="Something went wrong on our side.", request_id=getattr(g, "request_id", None)), 500

    _init_sentry(app)


def _scrub(event, hint):
    """Never ship credentials, tokens, cookies or request bodies to the error tracker."""
    req = event.get("request", {})
    for k in ("headers", "cookies", "data", "query_string"):
        req.pop(k, None)
    event.pop("user", None)
    return event


def _init_sentry(app):
    dsn = app.config.get("SENTRY_DSN")
    if not dsn:
        return
    try:
        import sentry_sdk
    except ImportError:
        log.warning("SENTRY_DSN is set but sentry-sdk is not installed")
        return
    sentry_sdk.init(dsn=dsn, send_default_pii=False, before_send=_scrub, traces_sample_rate=0.0,
                    environment=app.config.get("APP_ENV"))
