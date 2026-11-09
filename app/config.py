import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY") or "dev-secret-change-me-please-32-bytes-min"
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY") or "dev-jwt-secret-change-me-please-32-bytes"
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=int(os.getenv("JWT_EXPIRES_HOURS", "24")))
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL", "sqlite:///bloodlink.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*")


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=30)
