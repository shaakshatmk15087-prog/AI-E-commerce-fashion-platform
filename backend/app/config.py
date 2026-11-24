import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


class Config:
    APP_ENV = os.getenv("APP_ENV", "development")  # development | production
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", str(1024 * 1024)))  # 1 MB request bodies
    TRUST_PROXY_HOPS = int(os.getenv("TRUST_PROXY_HOPS", "0"))  # number of reverse proxies in front (nginx = 1)
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    SENTRY_DSN = os.getenv("SENTRY_DSN", "")
    ALLOW_INSECURE_MOCK_PAYMENTS = os.getenv("ALLOW_INSECURE_MOCK_PAYMENTS", "false").lower() == "true"
    CHAT_RETENTION_DAYS = int(os.getenv("CHAT_RETENTION_DAYS", "365"))  # AI chat history is deleted after this long
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 1800}
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-change-me-0000000000000000")
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-jwt-secret-change-me-00000000000000")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=int(os.getenv("JWT_ACCESS_MINUTES", "60")))
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL") or "sqlite:///dev.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
    CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")]
    PAYMENT_PROVIDER = os.getenv("PAYMENT_PROVIDER", "mock")
    PAYMENT_WEBHOOK_SECRET = os.getenv("PAYMENT_WEBHOOK_SECRET", "dev-webhook-secret-0000000000000000")
    MOCK_PAYMENTS_ENABLED = os.getenv("MOCK_PAYMENTS_ENABLED", "true").lower() == "true"
    SHIPPING_FLAT_MINOR = int(os.getenv("SHIPPING_FLAT_MINOR", "9900"))
    FREE_SHIPPING_THRESHOLD_MINOR = int(os.getenv("FREE_SHIPPING_THRESHOLD_MINOR", "99900"))
    TAX_RATE_BPS = int(os.getenv("TAX_RATE_BPS", "0"))  # basis points; tax policy still to be decided
    PENDING_ORDER_MINUTES = int(os.getenv("PENDING_ORDER_MINUTES", "30"))
    AI_ENABLED = os.getenv("AI_ENABLED", "true").lower() == "true"
    AI_MODEL = os.getenv("AI_MODEL", "claude-opus-5-5")
    AI_FALLBACK_MODEL = os.getenv("AI_FALLBACK_MODEL", "claude-opus-4-8")
    AI_TIMEOUT_SECONDS = float(os.getenv("AI_TIMEOUT_SECONDS", "45"))
    AI_DAILY_MESSAGE_LIMIT = int(os.getenv("AI_DAILY_MESSAGE_LIMIT", "50"))  # per user, UTC day
    AI_MAX_MESSAGE_CHARS = int(os.getenv("AI_MAX_MESSAGE_CHARS", "500"))
    SCHEDULER_ENABLED = os.getenv("SCHEDULER_ENABLED", "false").lower() == "true"
    SCHEDULER_MINUTES = int(os.getenv("SCHEDULER_MINUTES", "5"))
    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_ENABLED = True


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_ENGINE_OPTIONS = {}
    RATELIMIT_STORAGE_URI = "memory://"
    SQLALCHEMY_DATABASE_URI = os.getenv("TEST_DATABASE_URL") or "sqlite:///:memory:"  # set to run the suite on MySQL
    RATELIMIT_ENABLED = False
    AI_ENABLED = True
