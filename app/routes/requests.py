from flask import Blueprint, g, jsonify, request

from ..extensions import db
from ..models import BloodRequest, DonorProfile, DonorResponse, User
from ..utils import (BLOOD_TYPES, URGENCIES, ApiError, clean_str, donor_types_for, json_body,
                     notify, role_required, valid_choice)
from sqlalchemy import func

bp = Blueprint("requests", __name__, url_prefix="/api/requests")


def _owned_request(request_id):
    """Fetch a request owned by the current hospital; 404 for anyone else's."""
    req = db.session.get(BloodRequest, request_id)
    if req is None or req.hospital_id != g.current_user.hospital_profile.id:
        raise ApiError("Blood request not found", 404)
    return req


def _units(data):
    units = data.get("units_needed")
    if isinstance(units, bool) or not isinstance(units, int) or not 1 <= units <= 100:
        raise ApiError("'units_needed' must be a whole number between 1 and 100")
    return units


@bp.post("")
@role_required("hospital")
def create_request():
    data = json_body(request)
    hospital = g.current_user.hospital_profile
    req = BloodRequest(
        hospital_id=hospital.id,
        blood_type=valid_choice(data, "blood_type", BLOOD_TYPES, upper=True),
        units_needed=_units(data),
        urgency=valid_choice(data, "urgency", URGENCIES, lower=True),
        note=clean_str(data, "note", required=False, max_len=1000),
        status="open",
    )
    db.session.add(req)

    # Notify available, active donors in the same region who can donate to this type
    donors = (
        DonorProfile.query.join(User)
        .filter(
            User.is_active.is_(True),
            DonorProfile.is_available.is_(True),
            DonorProfile.blood_type.in_(donor_types_for(req.blood_type)),
            func.lower(DonorProfile.region) == hospital.region.strip().lower(),
        )
        .all()
    )
    for donor in donors:
        notify(donor.user_id,
               f"{req.urgency.capitalize()} request: {hospital.name} needs {req.blood_type} blood "
               f"({req.units_needed} unit(s)) in {hospital.city}.")
    db.session.commit()
    return jsonify(req.to_dict()), 201


@bp.get("")
@role_required("hospital")
def list_requests():
    rows = (
        BloodRequest.query.filter_by(hospital_id=g.current_user.hospital_profile.id)
        .order_by(BloodRequest.created_at.desc(), BloodRequest.id.desc())
        .all()
    )
    out = []
    for req in rows:
        item = req.to_dict()
        item["accepted_count"] = sum(1 for r in req.responses if r.status == "accepted")
        out.append(item)
    return jsonify(out)


@bp.get("/<int:request_id>")
@role_required("hospital")
def request_detail(request_id):
    req = _owned_request(request_id)
    item = req.to_dict()
    # Contact details: owning hospital only, and only donors who accepted
    item["accepted_donors"] = [
        {
            "donor_id": r.donor.id,
            "full_name": r.donor.full_name,
            "phone": r.donor.phone,
            "blood_type": r.donor.blood_type,
            "city": r.donor.city,
            "accepted_at": r.created_at.isoformat(),
        }
        for r in req.responses if r.status == "accepted"
    ]
    return jsonify(item)


@bp.patch("/<int:request_id>/status")
@role_required("hospital")
def update_status(request_id):
    req = _owned_request(request_id)
    data = json_body(request)
    status = valid_choice(data, "status", ("fulfilled", "cancelled"), lower=True)
    if req.status != "open":
        raise ApiError(f"Request is already {req.status}", 409)
    req.status = status
    db.session.commit()
    return jsonify(req.to_dict())
