from datetime import datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def iso(dt):
    return dt.isoformat() if dt else None


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # donor | hospital | admin
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    donor_profile = db.relationship("DonorProfile", back_populates="user", uselist=False,
                                    cascade="all, delete-orphan")
    hospital_profile = db.relationship("HospitalProfile", back_populates="user", uselist=False,
                                       cascade="all, delete-orphan")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def profile(self):
        if self.role == "donor":
            return self.donor_profile
        if self.role == "hospital":
            return self.hospital_profile
        return None

    def to_dict(self):
        # password_hash is intentionally never included
        return {
            "id": self.id,
            "email": self.email,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": iso(self.created_at),
        }


class DonorProfile(db.Model):
    __tablename__ = "donor_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    blood_type = db.Column(db.String(3), nullable=False, index=True)
    city = db.Column(db.String(80), nullable=False)
    region = db.Column(db.String(80), nullable=False, index=True)
    gps_address = db.Column(db.String(30))
    is_available = db.Column(db.Boolean, nullable=False, default=True)
    last_donation_date = db.Column(db.Date)

    user = db.relationship("User", back_populates="donor_profile")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "email": self.user.email,
            "full_name": self.full_name,
            "phone": self.phone,
            "blood_type": self.blood_type,
            "city": self.city,
            "region": self.region,
            "gps_address": self.gps_address,
            "is_available": self.is_available,
            "last_donation_date": iso(self.last_donation_date),
            "is_active": self.user.is_active,
        }


class HospitalProfile(db.Model):
    __tablename__ = "hospital_profiles"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    name = db.Column(db.String(160), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    city = db.Column(db.String(80), nullable=False)
    region = db.Column(db.String(80), nullable=False, index=True)
    address = db.Column(db.String(255), nullable=False)
    gps_address = db.Column(db.String(30))
    is_verified = db.Column(db.Boolean, nullable=False, default=False)

    user = db.relationship("User", back_populates="hospital_profile")
    requests = db.relationship("BloodRequest", back_populates="hospital")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "email": self.user.email,
            "name": self.name,
            "phone": self.phone,
            "city": self.city,
            "region": self.region,
            "address": self.address,
            "gps_address": self.gps_address,
            "is_verified": self.is_verified,
            "is_active": self.user.is_active,
        }


class BloodRequest(db.Model):
    __tablename__ = "blood_requests"

    id = db.Column(db.Integer, primary_key=True)
    hospital_id = db.Column(db.Integer, db.ForeignKey("hospital_profiles.id"), nullable=False, index=True)
    blood_type = db.Column(db.String(3), nullable=False)
    units_needed = db.Column(db.Integer, nullable=False)
    urgency = db.Column(db.String(10), nullable=False)  # critical | urgent | normal
    note = db.Column(db.Text)
    status = db.Column(db.String(10), nullable=False, default="open")  # open | fulfilled | cancelled
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    hospital = db.relationship("HospitalProfile", back_populates="requests")
    responses = db.relationship("DonorResponse", back_populates="request", cascade="all, delete-orphan")

    def to_dict(self):
        """Public-safe view: no donor details."""
        h = self.hospital
        return {
            "id": self.id,
            "hospital_id": self.hospital_id,
            "hospital_name": h.name,
            "hospital_city": h.city,
            "hospital_region": h.region,
            "hospital_address": h.address,
            "hospital_verified": h.is_verified,
            "blood_type": self.blood_type,
            "units_needed": self.units_needed,
            "urgency": self.urgency,
            "note": self.note,
            "status": self.status,
            "created_at": iso(self.created_at),
        }


class DonorResponse(db.Model):
    __tablename__ = "donor_responses"
    __table_args__ = (db.UniqueConstraint("request_id", "donor_id", name="uq_request_donor"),)

    id = db.Column(db.Integer, primary_key=True)
    request_id = db.Column(db.Integer, db.ForeignKey("blood_requests.id"), nullable=False, index=True)
    donor_id = db.Column(db.Integer, db.ForeignKey("donor_profiles.id"), nullable=False, index=True)
    status = db.Column(db.String(10), nullable=False)  # accepted | declined
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    request = db.relationship("BloodRequest", back_populates="responses")
    donor = db.relationship("DonorProfile")


class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    message = db.Column(db.String(500), nullable=False)
    is_read = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "message": self.message,
            "is_read": self.is_read,
            "created_at": iso(self.created_at),
        }
