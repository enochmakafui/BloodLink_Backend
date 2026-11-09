# BloodLink Backend (MVP)

Flask API connecting hospitals that need blood with matching donors.
Roles: `donor`, `hospital`, `admin`. All endpoints are under `/api` and return JSON (`{"error": "..."}` on failure).

## Usage

```bash
# 1. Install (Python 3.11+)
python -m venv .venv
.venv\Scripts\activate            # Windows  (macOS/Linux: source .venv/bin/activate)
pip install -r requirements.txt

# 2. Configure
copy .env.example .env            # macOS/Linux: cp .env.example .env
# edit .env: set SECRET_KEY, JWT_SECRET_KEY, ADMIN_EMAIL, ADMIN_PASSWORD

# 3. Create the database (SQLite by default; set DATABASE_URL for PostgreSQL)
flask --app run.py db upgrade

# 4. Seed the default admin
python seed.py

# 5. Run (http://localhost:5000)
python run.py

# 6. Test
pytest
```

After changing `app/models.py`: `flask --app run.py db migrate -m "message"` then `db upgrade`.

## Matching rules
A donor sees an open request when they are available, their blood type can donate to the requested type
(`DONOR_COMPATIBILITY` in `app/utils.py`), and they are in the hospital's region. Results sort by
city match, then urgency (critical first), then newest.

## Notes
- Donor contact details are only returned to the hospital that owns a request, and only for donors who accepted.
- Notifications are in-app only. `send_sms()` in `app/utils.py` is a stub (TODO: Ghana SMS provider).
- Out of scope (TODOs): email/SMS, websockets, distance search, uploads, hospital document verification, payments, password reset.
