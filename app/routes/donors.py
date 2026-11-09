from flask import Blueprint, g, jsonify, request
from sqlalchemy import case, func

from ..extensions import db
from ..models import BloodRequest, DonorResponse, HospitalProfile
from ..utils import (DONOR_COMPATIBILITY, RESPONSE_STATUSES, URGENCY_RANK, ApiError, clean_str,
                     donor_matches_request, json_body, notify, role_required, valid_bool,
                     valid_choice, valid_date, valid_phone)

bp = Blueprint("donors", __name__, url_prefix="/api/donors")


@bp.get("/me")
@role_required("donor")
def get_me():
    return jsonify(g.current_user.donor_profile.to_dict())


@bp.put("/me")
@role_required("donor")
def update_me():
    data = json_body(request)
    donor = g.current_user.donor_profile
    # Only these fields are editable (blood type and name are fixed in the MVP)
    if "phone" in data:
        donor.phone = valid_phone(data)
    if "city" in data:
        donor.city = clean_str(data, "city", max_len=80)
    if "region" in data:
        donor.region = clean_str(data, "region", max_len=80)
    if "gps_address" in data:
        donor.gps_address = clean_str(data, "gps_address", required=False, max_len=30)
    if "is_available" in data:
        donor.is_available = valid_bool(data, "is_available")
    if "last_donation_date" in data:
        donor.last_donation_date = valid_date(data, "last_donation_date")
    db.session.commit()
    return jsonify(donor.to_dict())


@bp.get("/requests")
@role_required("donor")
def matching_requests():
    donor = g.current_user.donor_profile
    if not donor.is_available:
        return jsonify([])

    city_match = case((func.lower(HospitalProfile.city) == donor.city.strip().lower(), 0), else_=1)
    urgency_order = case(*[(BloodRequest.urgency == k, v) for k, v in URGENCY_RANK.items()], else_=9)

    rows = (
        BloodRequest.query.join(HospitalProfile)
        .filter(
            BloodRequest.status == "open",
            BloodRequest.blood_type.in_(DONOR_COMPATIBILITY[donor.blood_type]),
            func.lower(HospitalProfile.region) == donor.region.strip().lower(),
        )
        # city match first, then critical -> normal, then newest
        .order_by(city_match, urgency_order, BloodRequest.created_at.desc(), BloodRequest.id.desc())
        .all()
    )
    responses = {r.request_id: r.status for r in DonorResponse.query.filter_by(donor_id=donor.id)}
    out = []
    for req in rows:
        item = req.to_dict()
        item["my_response"] = responses.get(req.id)
        item["has_responded"] = req.id in responses
        out.append(item)
    return jsonify(out)


@bp.post("/requests/<int:request_id>/respond")
@role_required("donor")
def respond(request_id):
    data = json_body(request)
    status = valid_choice(data, "status", RESPONSE_STATUSES, lower=True)
    donor = g.current_user.donor_profile

    blood_request = db.session.get(BloodRequest, request_id)
    # Treat requests that don't match this donor as not found
    if blood_request is None or not donor_matches_request(donor, blood_request):
        raise ApiError("Blood request not found", 404)
    if blood_request.status != "open":
        raise ApiError("This request is no longer open", 409)

    existing = DonorResponse.query.filter_by(request_id=request_id, donor_id=donor.id).first()
    if existing:
        newly_accepted = status == "accepted" and existing.status != "accepted"
        existing.status = status
        response = existing
    else:
        newly_accepted = status == "accepted"
        response = DonorResponse(request_id=request_id, donor_id=donor.id, status=status)
        db.session.add(response)

    if newly_accepted:
        notify(
            blood_request.hospital.user_id,
            f"{donor.full_name} ({donor.blood_type}) accepted your {blood_request.blood_type} "
            f"blood request #{blood_request.id}. Contact: {donor.phone}",
        )
    db.session.commit()
    return jsonify({"request_id": request_id, "status": response.status}), 200 if existing else 201


@bp.get("/history")
@role_required("donor")
def history():
    donor = g.current_user.donor_profile
    rows = (
        DonorResponse.query.filter_by(donor_id=donor.id)
        .order_by(DonorResponse.created_at.desc(), DonorResponse.id.desc())
        .all()
    )
    out = []
    for r in rows:
        item = r.request.to_dict()
        item["my_response"] = r.status
        item["responded_at"] = r.created_at.isoformat()
        out.append(item)
    return jsonify(out)
