import pytest

from app import create_app
from app.config import TestConfig
from app.extensions import db
from app.models import User


@pytest.fixture()
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def login(client, email, password="password123"):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.get_json()
    return r.get_json()["access_token"]


@pytest.fixture()
def make_donor(client):
    def _make(email="donor@test.com", blood_type="O+", city="Accra", region="Greater Accra", **extra):
        body = {"email": email, "password": "password123", "full_name": "Kofi Mensah",
                "phone": "0241234567", "blood_type": blood_type, "city": city, "region": region}
        body.update(extra)
        r = client.post("/api/auth/register/donor", json=body)
        assert r.status_code == 201, r.get_json()
        return auth(login(client, email))
    return _make


@pytest.fixture()
def make_hospital(client):
    def _make(email="hosp@test.com", city="Accra", region="Greater Accra", name="Korle Bu"):
        r = client.post("/api/auth/register/hospital", json={
            "email": email, "password": "password123", "name": name, "phone": "0302000000",
            "city": city, "region": region, "address": "Guggisberg Ave"})
        assert r.status_code == 201, r.get_json()
        return auth(login(client, email))
    return _make


@pytest.fixture()
def admin_headers(client, app):
    admin = User(email="admin@test.com", role="admin")
    admin.set_password("password123")
    db.session.add(admin)
    db.session.commit()
    return auth(login(client, "admin@test.com"))


@pytest.fixture()
def post_request(client):
    def _post(headers, blood_type="A+", urgency="normal", units=2):
        r = client.post("/api/requests", headers=headers, json={
            "blood_type": blood_type, "units_needed": units, "urgency": urgency, "note": "Urgent"})
        assert r.status_code == 201, r.get_json()
        return r.get_json()
    return _post
