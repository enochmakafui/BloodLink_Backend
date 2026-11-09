from flask import Blueprint, g, jsonify, request
from sqlalchemy import func

from ..extensions import db
from ..models import BloodRequest, DonorResponse
from ..utils import BLOOD_TYPES, clean_str, json_body, role_required, valid_phone

bp = Blueprint("hospitals", __name__, url_prefix="/api/hospitals")


@bp.get("/me")
@role_required("hospital")
def get_me():
    return jsonify(g.current_user.hospital_profile.to_dict())


@bp.put("/me")
@role_required("hospital")
def update_me():
    data = json_body(request)
    hospital = g.current_user.hospital_profile
    if "name" in data:
        hospital.name = clean_str(data, "name", max_len=160)
    if "phone" in data:
        hospital.phone = valid_phone(data)
    if "city" in data:
        hospital.city = clean_str(data, "city", max_len=80)
    if "region" in data:
        hospital.region = clean_str(data, "region", max_len=80)
    if "address" in data:
        hospital.address = clean_str(data, "address")
    if "gps_address" in data:
        hospital.gps_address = clean_str(data, "gps_address", required=False, max_len=30)
    # is_verified can only be changed by an admin
    db.session.commit()
    return jsonify(hospital.to_dict())


@bp.get("/analytics")
@role_required("hospital")
def analytics():
    hospital_id = g.current_user.hospital_profile.id
    by_status = dict(
        db.session.query(BloodRequest.status, func.count())
        .filter(BloodRequest.hospital_id == hospital_id)
        .group_by(BloodRequest.status)
        .all()
    )
    by_type = dict(
        db.session.query(BloodRequest.blood_type, func.count())
        .filter(BloodRequest.hospital_id == hospital_id)
        .group_by(BloodRequest.blood_type)
        .all()
    )
    accepted = (
        db.session.query(func.count(func.distinct(DonorResponse.donor_id)))
        .join(BloodRequest)
        .filter(BloodRequest.hospital_id == hospital_id, DonorResponse.status == "accepted")
        .scalar()
    )
    return jsonify({
        "total_requests": sum(by_status.values()),
        "open": by_status.get("open", 0),
        "fulfilled": by_status.get("fulfilled", 0),
        "cancelled": by_status.get("cancelled", 0),
        "total_donors_accepted": accepted,
        "requests_by_blood_type": {bt: by_type.get(bt, 0) for bt in BLOOD_TYPES},
    })
