from flask import Blueprint, g, jsonify, request
from sqlalchemy import func

from ..extensions import db
from .. import exports
from ..models import (BloodRequest, DonorProfile, DonorResponse, HospitalProfile, Notification,
                      OtpCode, User)
from ..utils import (BLOOD_TYPES, REQUEST_STATUSES, ApiError, json_body, role_required,
                     valid_bool)

bp = Blueprint("admin", __name__, url_prefix="/api/admin")


def _filtered_donors():
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
    return query.order_by(DonorProfile.id).all()


@bp.get("/donors")
@role_required("admin")
def list_donors():
    return jsonify([d.to_dict() for d in _filtered_donors()])


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


@bp.delete("/users/<int:user_id>")
@role_required("admin")
def delete_user(user_id):
    """Permanently remove a donor or hospital account and everything attached to it."""
    user = db.session.get(User, user_id)
    if user is None:
        raise ApiError("User not found", 404)
    if user.id == g.current_user.id:
        raise ApiError("You cannot delete your own account", 400)
    if user.role == "admin":
        raise ApiError("Admin accounts cannot be deleted", 400)

    if user.donor_profile:
        DonorResponse.query.filter_by(donor_id=user.donor_profile.id).delete()
    if user.hospital_profile:
        # requests (and the donor responses to them, via cascade) belong to the hospital
        for req in BloodRequest.query.filter_by(hospital_id=user.hospital_profile.id).all():
            db.session.delete(req)
    Notification.query.filter_by(user_id=user.id).delete()
    OtpCode.query.filter_by(user_id=user.id).delete()
    db.session.flush()
    db.session.delete(user)  # profile removed via cascade
    db.session.commit()
    return jsonify({"deleted": True, "user_id": user_id})


def _filtered_requests():
    query = BloodRequest.query
    status = request.args.get("status")
    if status:
        status = status.strip().lower()
        if status not in REQUEST_STATUSES:
            raise ApiError(f"'status' must be one of: {', '.join(REQUEST_STATUSES)}")
        query = query.filter(BloodRequest.status == status)
    return query.order_by(BloodRequest.created_at.desc(), BloodRequest.id.desc()).all()


@bp.get("/requests")
@role_required("admin")
def list_requests():
    return jsonify([r.to_dict() for r in _filtered_requests()])


def _donor_rows():
    return [[d.id, d.full_name, d.user.email, d.phone, d.blood_type, d.city, d.region,
             "Yes" if d.is_available else "No",
             d.last_donation_date.isoformat() if d.last_donation_date else "",
             "Active" if d.user.is_active else "Deactivated"] for d in _filtered_donors()]


def _hospital_rows():
    rows = HospitalProfile.query.order_by(HospitalProfile.id).all()
    return [[h.id, h.name, h.user.email, h.phone, h.city, h.region, h.address,
             "Yes" if h.is_verified else "No",
             "Active" if h.user.is_active else "Deactivated"] for h in rows]


def _request_rows():
    return [[r.id, r.hospital.name, r.blood_type, r.units_needed, r.urgency, r.status,
             r.created_at.strftime("%Y-%m-%d %H:%M") if r.created_at else "", r.note or ""]
            for r in _filtered_requests()]


REPORTS = {
    "donors": ("Donors Report", ["ID", "Name", "Email", "Phone", "Blood type", "City", "Region",
                                 "Available", "Last donation", "Account"], _donor_rows),
    "hospitals": ("Hospitals Report", ["ID", "Name", "Email", "Phone", "City", "Region", "Address",
                                       "Verified", "Account"], _hospital_rows),
    "requests": ("Blood Requests Report", ["ID", "Hospital", "Blood type", "Units", "Urgency",
                                           "Status", "Created", "Note"], _request_rows),
}


@bp.get("/reports/<kind>")
@role_required("admin")
def download_report(kind):
    """Download a report: ?format=pdf|docx|xlsx (aliases: word, excel).
    Donor and request reports accept the same filters as their list endpoints."""
    if kind not in REPORTS:
        raise ApiError(f"Unknown report. Choose one of: {', '.join(REPORTS)}", 404)
    fmt = exports.normalize_format(request.args.get("format"))
    if fmt is None:
        raise ApiError("'format' must be one of: pdf, docx, xlsx")
    title, headers, rows_fn = REPORTS[kind]
    return exports.table_response(fmt, f"bloodlink-{kind}-report", title, headers, rows_fn())


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
