import os
import re
from datetime import timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from dotenv import load_dotenv

load_dotenv()

LOCAL_HOSTS = {"", "localhost", "127.0.0.1", "::1"}


def normalize_database_url(url):
    """Pin the psycopg2 driver and require SSL for remote Postgres hosts.

    Accepts postgres:// or postgresql:// (SQLAlchemy 2.1 would otherwise pick psycopg3).
    Non-Postgres URLs (e.g. SQLite) are returned unchanged.
    """
    url = re.sub(r"^postgres(ql)?(\+psycopg2)?://", "postgresql+psycopg2://", url)
    if not url.startswith("postgresql+psycopg2://"):
        return url
    parts = urlsplit(url)
    if (parts.hostname or "") in LOCAL_HOSTS:
        return url
    query = parse_qsl(parts.query, keep_blank_values=True)
    if not any(k == "sslmode" for k, _ in query):
        query.append(("sslmode", "require"))
    return urlunsplit(parts._replace(query=urlencode(query)))


def engine_options_for(url):
    """Small, self-healing pool for the Supabase Session pooler (Postgres only)."""
    if not url.startswith("postgresql"):
        return {}
    return {"pool_pre_ping": True, "pool_recycle": 300, "pool_size": 5, "max_overflow": 5}


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY") or "dev-secret-change-me-please-32-bytes-min"
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY") or "dev-jwt-secret-change-me-please-32-bytes"
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=int(os.getenv("JWT_EXPIRES_HOURS", "24")))
    SQLALCHEMY_DATABASE_URI = normalize_database_url(os.getenv("DATABASE_URL", "sqlite:///bloodlink.db"))
    SQLALCHEMY_ENGINE_OPTIONS = engine_options_for(SQLALCHEMY_DATABASE_URI)
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")

    # Email OTP via Brevo (transactional email API)
    BREVO_API_KEY = os.getenv("BREVO_API_KEY")
    BREVO_SENDER_EMAIL = os.getenv("BREVO_SENDER_EMAIL")
    BREVO_SENDER_NAME = os.getenv("BREVO_SENDER_NAME", "BloodLink")
    OTP_TTL_MINUTES = int(os.getenv("OTP_TTL_MINUTES", "10"))
    OTP_MAX_ATTEMPTS = int(os.getenv("OTP_MAX_ATTEMPTS", "5"))
    OTP_RESEND_SECONDS = int(os.getenv("OTP_RESEND_SECONDS", "60"))
    # Local dev only: also log OTP codes. Never enable in production.
    DEV_LOG_OTP = os.getenv("DEV_LOG_OTP") == "1"


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    SQLALCHEMY_ENGINE_OPTIONS = {}
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=30)
