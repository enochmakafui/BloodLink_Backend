from flask import Blueprint, g, jsonify

from ..extensions import db
from ..models import Notification
from ..utils import ApiError, login_required

bp = Blueprint("notifications", __name__, url_prefix="/api/notifications")


@bp.get("")
@login_required
def list_notifications():
    rows = (
        Notification.query.filter_by(user_id=g.current_user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .all()
    )
    return jsonify([n.to_dict() for n in rows])


@bp.patch("/<int:notification_id>/read")
@login_required
def mark_read(notification_id):
    n = db.session.get(Notification, notification_id)
    if n is None or n.user_id != g.current_user.id:
        raise ApiError("Notification not found", 404)
    n.is_read = True
    db.session.commit()
    return jsonify(n.to_dict())
