import pytest

from app.models import User
from app.extensions import db
from tests.conftest import verify_user

DONOR = {"email": "a@test.com", "password": "password123", "full_name": "Ama", "phone": "0241234567",
         "blood_type": "O+", "city": "Accra", "region": "Greater Accra"}


def test_register_and_login_donor(client):
    r = client.post("/api/auth/register/donor", json=DONOR)
    assert r.status_code == 201
    assert "password" not in r.get_data(as_text=True)
    verify_user("a@test.com")
    r = client.post("/api/auth/login", json={"email": "A@test.com", "password": "password123"})
    body = r.get_json()
    assert body["role"] == "donor"
    assert body["user"]["profile"]["blood_type"] == "O+"
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200 and me.get_json()["email"] == "a@test.com"


def test_register_hospital(client):
    r = client.post("/api/auth/register/hospital", json={
        "email": "h@test.com", "password": "password123", "name": "H", "phone": "+233302000000",
        "city": "Accra", "region": "Greater Accra", "address": "x"})
    assert r.status_code == 201
    assert r.get_json()["profile"]["is_verified"] is False


@pytest.mark.parametrize("override", [
    {"email": "not-an-email"},
    {"password": "short"},
    {"phone": "12345"},
    {"phone": "02412345"},
    {"blood_type": "Z+"},
    {"full_name": ""},
])
def test_donor_validation(client, override):
    r = client.post("/api/auth/register/donor", json={**DONOR, **override})
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_duplicate_email(client):
    client.post("/api/auth/register/donor", json=DONOR)
    assert client.post("/api/auth/register/donor", json=DONOR).status_code == 409


def test_bad_login(client):
    client.post("/api/auth/register/donor", json=DONOR)
    r = client.post("/api/auth/login", json={"email": DONOR["email"], "password": "wrongpass1"})
    assert r.status_code == 401


def test_deactivated_user_cannot_login_or_use_token(client, app, make_donor):
    headers = make_donor("d@test.com")
    user = User.query.filter_by(email="d@test.com").first()
    user.is_active = False
    db.session.commit()
    assert client.post("/api/auth/login", json={"email": "d@test.com", "password": "password123"}).status_code == 403
    assert client.get("/api/donors/me", headers=headers).status_code == 401


def test_requires_token(client):
    r = client.get("/api/auth/me")
    assert r.status_code == 401 and "error" in r.get_json()
