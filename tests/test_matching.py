import pytest

from app.utils import BLOOD_TYPES, DONOR_COMPATIBILITY, donor_types_for


def test_compatibility_table():
    assert set(DONOR_COMPATIBILITY) == set(BLOOD_TYPES)
    assert len(DONOR_COMPATIBILITY["O-"]) == 8
    assert DONOR_COMPATIBILITY["AB+"] == ["AB+"]
    assert set(donor_types_for("O-")) == {"O-"}
    assert set(donor_types_for("AB+")) == set(BLOOD_TYPES)


@pytest.mark.parametrize("donor_type,request_type,visible", [
    ("O-", "AB+", True), ("O+", "A+", True), ("O+", "O-", False),
    ("A+", "O+", False), ("A+", "AB+", True), ("AB+", "A+", False),
])
def test_blood_type_matching(client, make_donor, make_hospital, post_request, donor_type, request_type, visible):
    d = make_donor(blood_type=donor_type)
    post_request(make_hospital(), blood_type=request_type)
    got = client.get("/api/donors/requests", headers=d).get_json()
    assert (len(got) == 1) is visible


def test_region_and_availability_and_status(client, make_donor, make_hospital, post_request):
    d = make_donor(blood_type="O-", region="Greater Accra")
    post_request(make_hospital("far@test.com", region="Ashanti", city="Kumasi"))
    assert client.get("/api/donors/requests", headers=d).get_json() == []

    h = make_hospital("near@test.com", region="greater accra ")  # case/space-insensitive
    req = post_request(h)
    assert len(client.get("/api/donors/requests", headers=d).get_json()) == 1

    client.put("/api/donors/me", headers=d, json={"is_available": False})
    assert client.get("/api/donors/requests", headers=d).get_json() == []
    client.put("/api/donors/me", headers=d, json={"is_available": True})

    client.patch(f"/api/requests/{req['id']}/status", headers=h, json={"status": "cancelled"})
    assert client.get("/api/donors/requests", headers=d).get_json() == []


def test_sorting_city_then_urgency_then_newest(client, make_donor, make_hospital, post_request):
    d = make_donor(blood_type="O-", city="Accra")
    same = make_hospital("same@test.com", city="Accra")
    other = make_hospital("other@test.com", city="Tema")
    a = post_request(other, urgency="critical")
    b = post_request(same, urgency="normal")
    c = post_request(same, urgency="critical")
    e = post_request(same, urgency="critical")
    ids = [r["id"] for r in client.get("/api/donors/requests", headers=d).get_json()]
    assert ids == [e["id"], c["id"], b["id"], a["id"]]


def test_response_includes_verified_flag_and_responded_state(client, make_donor, make_hospital, post_request):
    d = make_donor(blood_type="O-")
    req = post_request(make_hospital())
    assert req["hospital_verified"] is False
    item = client.get("/api/donors/requests", headers=d).get_json()[0]
    assert item["has_responded"] is False and item["my_response"] is None
    client.post(f"/api/donors/requests/{req['id']}/respond", headers=d, json={"status": "declined"})
    item = client.get("/api/donors/requests", headers=d).get_json()[0]
    assert item["has_responded"] is True and item["my_response"] == "declined"
