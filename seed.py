"""Create the default admin user. Reads ADMIN_EMAIL and ADMIN_PASSWORD from the environment."""
import os
import sys

from app import create_app
from app.extensions import db
from app.models import User


def seed_admin():
    email = os.getenv("ADMIN_EMAIL")
    password = os.getenv("ADMIN_PASSWORD")
    if not email or not password:
        sys.exit("Set ADMIN_EMAIL and ADMIN_PASSWORD (see .env.example) before seeding.")
    if len(password) < 8:
        sys.exit("ADMIN_PASSWORD must be at least 8 characters.")

    app = create_app()
    with app.app_context():
        email = email.strip().lower()
        if User.query.filter_by(email=email).first():
            print(f"Admin {email} already exists - nothing to do.")
            return
        admin = User(email=email, role="admin", email_verified=True)
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
        print(f"Created admin {email}")


if __name__ == "__main__":
    seed_admin()
