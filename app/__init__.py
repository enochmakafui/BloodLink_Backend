from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException

from .config import Config
from .extensions import cors, db, jwt, migrate
from .utils import ApiError


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    db.init_app(app)
    jwt.init_app(app)
    migrate.init_app(app, db)
    cors.init_app(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})

    from . import models  # noqa: F401  (register models for migrations)
    from .routes.admin import bp as admin_bp
    from .routes.auth import bp as auth_bp
    from .routes.donors import bp as donors_bp
    from .routes.hospitals import bp as hospitals_bp
    from .routes.notifications import bp as notifications_bp
    from .routes.requests import bp as requests_bp

    for bp in (auth_bp, donors_bp, hospitals_bp, requests_bp, notifications_bp, admin_bp):
        app.register_blueprint(bp)

    register_error_handlers(app)
    return app


def register_error_handlers(app):
    @app.errorhandler(ApiError)
    def api_error(e):
        return jsonify({"error": e.message}), e.status

    @app.errorhandler(HTTPException)
    def http_error(e):
        return jsonify({"error": e.description}), e.code

    @app.errorhandler(Exception)
    def unexpected(e):
        app.logger.exception(e)
        db.session.rollback()
        return jsonify({"error": "Internal server error"}), 500

    @jwt.unauthorized_loader
    def missing_token(reason):
        return jsonify({"error": "Authentication required"}), 401

    @jwt.invalid_token_loader
    def invalid_token(reason):
        return jsonify({"error": "Invalid token"}), 401

    @jwt.expired_token_loader
    def expired_token(header, payload):
        return jsonify({"error": "Token has expired"}), 401
