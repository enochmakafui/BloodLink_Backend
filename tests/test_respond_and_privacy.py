def _respond(client, headers, req_id, status):
    return client.post(f"/api/donors/requests/{req_id}/respond", headers=headers, json={"status": status})


def test_respond_flow_and_notifications(client, make_donor, make_hospital, post_request):
    d = make_donor(blood_type="O-")
    h = make_hospital()
    req = post_request(h)

    # donor was notified about the new request
    notes = client.get("/api/notifications", headers=d).get_json()
    assert len(notes) == 1 and notes[0]["is_read"] is False

    r = _respond(client, d, req["id"], "accepted")
    assert r.status_code == 201

    # hospital was notified
    hn = client.get("/api/notifications", headers=h).get_json()
    assert len(hn) == 1 and "Kofi Mensah" in hn[0]["message"]
    assert client.patch(f"/api/notifications/{hn[0]['id']}/read", headers=h).get_json()["is_read"] is True

    # history
    hist = client.get("/api/donors/history", headers=d).get_json()
    assert len(hist) == 1 and hist[0]["my_response"] == "accepted"


def test_second_response_updates_existing(client, make_donor, make_hospital, post_request):
    d = make_donor(blood_type="O-")
    h = make_hospital()
    req = post_request(h)
    assert _respond(client, d, req["id"], "declined").status_code == 201
    assert _respond(client, d, req["id"], "accepted").status_code == 200
    assert _respond(client, d, req["id"], "accepted").status_code == 200  # no duplicate notification
    assert len(client.get("/api/donors/history", headers=d).get_json()) == 1
    assert len(client.get("/api/notifications", headers=h).get_json()) == 1
    detail = client.get(f"/api/requests/{req['id']}", headers=h).get_json()
    assert len(detail["accepted_donors"]) == 1


def test_cannot_respond_to_closed_request(client, make_donor, make_hospital, post_request):
    d = make_donor(blood_type="O-")
    h = make_hospital()
    req = post_request(h)
    client.patch(f"/api/requests/{req['id']}/status", headers=h, json={"status": "fulfilled"})
    assert _respond(client, d, req["id"], "accepted").status_code == 409


def test_invalid_response_and_unknown_request(client, make_donor, make_hospital, post_request):
    d = make_donor(blood_type="O-")
    req = post_request(make_hospital())
    assert _respond(client, d, req["id"], "maybe").status_code == 400
    assert _respond(client, d, 9999, "accepted").status_code == 404


def test_non_matching_donor_cannot_respond(client, make_donor, make_hospital, post_request):
    d = make_donor(blood_type="A+")
    req = post_request(make_hospital(), blood_type="O+")
    assert _respond(client, d, req["id"], "accepted").status_code == 404


def test_contact_details_only_for_owner_and_accepted(client, make_donor, make_hospital, post_request):
    d1 = make_donor("d1@test.com", blood_type="O-")
    d2 = make_donor("d2@test.com", blood_type="O-")
    owner = make_hospital("owner@test.com")
    other = make_hospital("other@test.com", name="Other")
    req = post_request(owner)

    _respond(client, d1, req["id"], "accepted")
    _respond(client, d2, req["id"], "declined")

    detail = client.get(f"/api/requests/{req['id']}", headers=owner).get_json()
    assert len(detail["accepted_donors"]) == 1
    donor = detail["accepted_donors"][0]
    assert donor["phone"] == "0241234567" and set(donor) >= {"full_name", "phone", "blood_type", "city"}

    # another hospital cannot see or modify it
    assert client.get(f"/api/requests/{req['id']}", headers=other).status_code == 404
    assert client.patch(f"/api/requests/{req['id']}/status", headers=other, json={"status": "cancelled"}).status_code == 404
    assert client.get("/api/requests", headers=other).get_json() == []

    # donors never see contact info or other donors in any donor-facing response
    for path in ("/api/donors/requests", "/api/donors/history"):
        text = client.get(path, headers=d2).get_data(as_text=True)
        assert "0241234567" not in text and "accepted_donors" not in text
    assert client.get(f"/api/requests/{req['id']}", headers=d1).status_code == 403


def test_request_validation_and_status_change(client, make_hospital):
    h = make_hospital()
    bad = [
        {"blood_type": "X", "units_needed": 1, "urgency": "normal"},
        {"blood_type": "A+", "units_needed": 0, "urgency": "normal"},
        {"blood_type": "A+", "units_needed": 1, "urgency": "whenever"},
    ]
    for body in bad:
        assert client.post("/api/requests", headers=h, json=body).status_code == 400
    req = client.post("/api/requests", headers=h,
                      json={"blood_type": "a+", "units_needed": 1, "urgency": "critical"}).get_json()
    assert req["blood_type"] == "A+"
    assert client.patch(f"/api/requests/{req['id']}/status", headers=h, json={"status": "open"}).status_code == 400
    assert client.patch(f"/api/requests/{req['id']}/status", headers=h, json={"status": "fulfilled"}).status_code == 200
    assert client.patch(f"/api/requests/{req['id']}/status", headers=h, json={"status": "cancelled"}).status_code == 409


def test_hospital_analytics(client, make_donor, make_hospital, post_request):
    d1 = make_donor("d1@test.com", blood_type="O-")
    d2 = make_donor("d2@test.com", blood_type="O-")
    h = make_hospital()
    r1 = post_request(h, blood_type="A+")
    r2 = post_request(h, blood_type="A+")
    r3 = post_request(h, blood_type="B-")
    _respond(client, d1, r1["id"], "accepted")
    _respond(client, d2, r1["id"], "accepted")
    client.patch(f"/api/requests/{r2['id']}/status", headers=h, json={"status": "fulfilled"})
    client.patch(f"/api/requests/{r3['id']}/status", headers=h, json={"status": "cancelled"})
    a = client.get("/api/hospitals/analytics", headers=h).get_json()
    assert (a["total_requests"], a["open"], a["fulfilled"], a["cancelled"]) == (3, 1, 1, 1)
    assert a["total_donors_accepted"] == 2
    assert a["requests_by_blood_type"]["A+"] == 2 and a["requests_by_blood_type"]["B-"] == 1


def test_notification_privacy(client, make_donor, make_hospital, post_request):
    d = make_donor(blood_type="O-")
    h = make_hospital()
    post_request(h)
    note_id = client.get("/api/notifications", headers=d).get_json()[0]["id"]
    assert client.patch(f"/api/notifications/{note_id}/read", headers=h).status_code == 404
