from flask import Blueprint, g, jsonify, request
from sqlalchemy import func

from ..extensions import db
from ..models import BloodRequest, DonorProfile, DonorResponse, HospitalProfile, User
from ..utils import (BLOOD_TYPES, REQUEST_STATUSES, ApiError, json_body, role_required,
                     valid_bool)

bp = Blueprint("admin", __name__, url_prefix="/api/admin")


@bp.get("/donors")
@role_required("admin")
def list_donors():
    query = DonorProfile.query
    blood_type = request.args.get("blood_type")
    region = request.args.get("region")
    if blood_type:
        blood_type = blood_type.strip().upper()
        if blood_type not in BLOOD_TYPES:
            raise ApiError(f"'blood_type' must be one of: {', '.join(BLOOD_TYPES)}")
        query = query.filter(DonorProfile.blood_type == blood_type)
    if region:
        query = query.filter(func.lower(DonorProfile.region) == region.strip().lower())
    return jsonify([d.to_dict() for d in query.order_by(DonorProfile.id).all()])


@bp.get("/hospitals")
@role_required("admin")
def list_hospitals():
    rows = HospitalProfile.query.order_by(HospitalProfile.id).all()
    return jsonify([h.to_dict() for h in rows])


@bp.patch("/hospitals/<int:hospital_id>/verify")
@role_required("admin")
def verify_hospital(hospital_id):
    hospital = db.session.get(HospitalProfile, hospital_id)
    if hospital is None:
        raise ApiError("Hospital not found", 404)
    hospital.is_verified = True
    db.session.commit()
    return jsonify(hospital.to_dict())


@bp.patch("/users/<int:user_id>/active")
@role_required("admin")
def set_user_active(user_id):
    data = json_body(request)
    if "is_active" not in data:
        raise ApiError("'is_active' is required")
    active = valid_bool(data, "is_active")
    user = db.session.get(User, user_id)
    if user is None:
        raise ApiError("User not found", 404)
    if user.id == g.current_user.id and not active:
        raise ApiError("You cannot deactivate your own account", 400)
    user.is_active = active
    db.session.commit()
    return jsonify(user.to_dict())


@bp.get("/requests")
@role_required("admin")
def list_requests():
    query = BloodRequest.query
    status = request.args.get("status")
    if status:
        status = status.strip().lower()
        if status not in REQUEST_STATUSES:
            raise ApiError(f"'status' must be one of: {', '.join(REQUEST_STATUSES)}")
        query = query.filter(BloodRequest.status == status)
    rows = query.order_by(BloodRequest.created_at.desc(), BloodRequest.id.desc()).all()
    return jsonify([r.to_dict() for r in rows])


@bp.get("/stats")
@role_required("admin")
def stats():
    by_type = dict(
        db.session.query(DonorProfile.blood_type, func.count()).group_by(DonorProfile.blood_type).all()
    )
    return jsonify({
        "total_donors": DonorProfile.query.count(),
        "total_hospitals": HospitalProfile.query.count(),
        "total_requests": BloodRequest.query.count(),
        "accepted_responses": DonorResponse.query.filter_by(status="accepted").count(),
        "donors_by_blood_type": {bt: by_type.get(bt, 0) for bt in BLOOD_TYPES},
    })
