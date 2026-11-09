# BloodLink API – Frontend Integration Guide

Instructions for the frontend developer (or Claude Code) implementing the BloodLink client.
Everything below was verified against the backend source code.

- **Base URL:** `https://bloodlink-api-bli0.onrender.com`
- **Format:** JSON in, JSON out. Send `Content-Type: application/json` on every request with a body.
- **Auth:** `Authorization: Bearer <access_token>` (JWT, valid **24 hours**, no refresh endpoint).
- **CORS:** open (`*`) for `/api/*`, so the browser can call it directly.
- **Hosting caveat:** the API runs on Render's free tier. After 15 min idle the first request can take
  **30–60 s** (cold start). Show a loading state and use a long timeout (≥ 60 s) on the first call
  (e.g. login). Optionally ping `GET /api/health` on app load to wake it.

---

## 1. Concepts

BloodLink connects **hospitals** (who post blood requests) with **donors** (who accept them).
There are three roles: `donor`, `hospital`, `admin`.

- Donors and hospitals self-register and must **verify their email with an OTP** before they can log in. **Admins cannot register through the API** – they are created
  server-side (`seed.py`). Build an admin login screen but no admin signup.
- Login returns the role; route the user to the matching dashboard.
- Notifications are **in-app only** (no SMS/push yet). Poll `GET /api/notifications` (e.g. every 30–60 s
  or on page focus).

### Matching rules (drives what donors see)
A donor sees an `open` request only if **all** are true:
1. Donor `is_available` is `true` (otherwise the list is just `[]`).
2. Donor's blood type is compatible with the requested type (standard ABO/Rh donation rules).
3. Donor's `region` equals the hospital's `region` (**case-insensitive exact match**, whitespace trimmed).

Results are sorted: same **city** first, then `critical → urgent → normal`, then newest.

> **Important for the UI:** `region` and `city` are free text on the backend, so a typo means no match.
> Use a **fixed dropdown of Ghana's 16 regions** for `region` in both signup forms (same spelling everywhere):
> Greater Accra, Ashanti, Western, Western North, Central, Eastern, Volta, Oti, Northern, Savannah,
> North East, Upper East, Upper West, Bono, Bono East, Ahafo.

### Enumerations
| Field | Allowed values |
|---|---|
| `blood_type` | `A+ A- B+ B- AB+ AB- O+ O-` (input is upper-cased by the server) |
| `urgency` | `critical`, `urgent`, `normal` (lower-cased by the server) |
| request `status` | `open`, `fulfilled`, `cancelled` |
| donor response `status` | `accepted`, `declined` |
| `role` | `donor`, `hospital`, `admin` |

### Field formats
- **phone:** Ghana number, `0XXXXXXXXX` (10 digits) or `+233XXXXXXXXX`. Spaces are stripped.
- **email:** valid format; stored lower-cased. **password:** minimum 8 characters.
- **dates:** `YYYY-MM-DD`, not in the future.
- **timestamps** (`created_at`, etc.): ISO-8601 **without timezone suffix, but they are UTC**.
  Parse as UTC (append `Z`) before displaying in local time.
- **gps_address:** optional string, max 30 chars (e.g. Ghana Post GPS code `GA-123-4567`).
- **IDs** are integers.

---

## 2. Error handling

Every error is JSON: `{"error": "<human readable message>"}`. There are no per-field error maps –
show the message in a toast/banner.

| Status | Meaning |
|---|---|
| 400 | Validation problem (message says which field) |
| 401 | Missing / invalid / expired token, or wrong login, or account deactivated mid-session |
| 403 | Logged in but wrong role, or account deactivated at login |
| 404 | Not found (also returned when a resource exists but isn't yours) |
| 409 | Conflict (email already registered; request no longer open / already closed) |
| 500 | `{"error": "Internal server error"}` |

Known 401 messages: `Authentication required`, `Invalid token`, `Token has expired`,
`Invalid email or password`, `Account not found or deactivated`.

**Client rules:**
- On **any 401** (except from `/api/auth/login`) → clear the stored token and redirect to login.
- On **403** → show "You don't have permission" (should only happen on a routing bug).
- Store the token in memory + `localStorage` (or an httpOnly-cookie proxy if you add a BFF); attach it
  via a single fetch/axios wrapper.

---

## 3. Endpoints

`Auth` column: 🔓 public · 🔑 any logged-in user · 🩸 donor · 🏥 hospital · 🛡️ admin

### Health
| Method & path | Auth | Notes |
|---|---|---|
| `GET /api/health` | 🔓 | `{"status":"ok"}`. Does not touch the DB. |

### Auth
#### `POST /api/auth/register/donor` 🔓 → `201`
```json
{
  "email": "kofi@example.com",
  "password": "password123",
  "full_name": "Kofi Mensah",
  "phone": "0241234567",
  "blood_type": "O+",
  "city": "Accra",
  "region": "Greater Accra",
  "gps_address": "GA-123-4567"
}
```
`gps_address` is optional; all others required (`full_name` ≤120, `city`/`region` ≤80).
Response: the user object with profile (see *User shape* below) plus `"verification_required": true`,
and `email_verified: false`. **No token is returned, and the account cannot log in yet.** A 6-digit
code has been emailed; show the *Verify email* screen (see **Email OTP flow** below).
Errors: `409 Email is already registered`.

#### `POST /api/auth/register/hospital` 🔓 → `201`
```json
{
  "email": "korlebu@example.com",
  "password": "password123",
  "name": "Korle Bu Teaching Hospital",
  "phone": "0302123456",
  "city": "Accra",
  "region": "Greater Accra",
  "address": "Guggisberg Ave, Korle Bu",
  "gps_address": "GA-000-0000"
}
```
Required: `email, password, name (≤160), phone, city, region, address`; optional `gps_address`.
Response: same as donor registration (`verification_required: true`, email OTP sent).
Hospital profile `is_verified` (admin approval, different from email verification) starts as `false`
(an admin verifies it; unverified hospitals can still post requests today, but show a
"pending verification" badge).

#### `POST /api/auth/login` 🔓 → `200`
Body: `{"email": "...", "password": "..."}`
```json
{
  "access_token": "<jwt>",
  "role": "donor",
  "user": { "id": 1, "email": "...", "role": "donor", "is_active": true,
            "created_at": "2026-11-09T10:00:00", "profile": { ... } }
}
```
Errors: `401 Invalid email or password`, `403 This account has been deactivated`, and
**`403` with `{"error": "Please verify your email before logging in", "code": "email_not_verified"}`** –
when you see `code === "email_not_verified"`, send the user to the Verify email screen
(call `POST /api/auth/resend-otp` there, since the original code may have expired).

#### Email OTP flow (all public 🔓)
Codes are 6 digits, expire after **10 minutes**, are single-use, and lock after **5 wrong attempts**
(request a new one). A new code invalidates earlier ones. Resend has a **60 s cooldown** (disable the
button for 60 s client-side). All code errors return the same `400 {"error": "Invalid or expired code"}`.

| Endpoint | Body | Result |
|---|---|---|
| `POST /api/auth/verify-email` | `{"email", "otp"}` | `200` – same payload as login (`access_token`, `role`, `user`): the user is **signed in immediately**. |
| `POST /api/auth/resend-otp` | `{"email"}` | Always `200 {"message": "If that email is registered, a code has been sent."}` (never reveals whether the email exists; nothing is sent if already verified or inside the cooldown). |
| `POST /api/auth/forgot-password` | `{"email"}` | Always `200`, same generic message. Emails a reset code if the account exists. |
| `POST /api/auth/reset-password` | `{"email", "otp", "new_password"}` | `200 {"message": "Password updated..."}`. `new_password` min 8 chars. Also marks the email verified. Then send the user to login (no token is returned). |

Screens to build: **Verify email** (email prefilled, 6-digit input, resend with countdown),
**Forgot password** (email) → **Reset password** (email, code, new password).

#### `GET /api/auth/me` 🔑 → `200`
Returns the same `user` object (with `profile`; `profile` is `null` for admins). Use on app start to
restore a session and refresh profile data.

**User shape**
```json
{ "id": 1, "email": "x@y.com", "role": "donor|hospital|admin", "is_active": true,
  "email_verified": true, "created_at": "...", "profile": <DonorProfile | HospitalProfile | null> }
```

**DonorProfile**
```json
{ "id": 3, "user_id": 1, "email": "...", "full_name": "...", "phone": "...", "blood_type": "O+",
  "city": "...", "region": "...", "gps_address": null, "is_available": true,
  "last_donation_date": "2026-01-15" , "is_active": true }
```
**HospitalProfile**
```json
{ "id": 2, "user_id": 5, "email": "...", "name": "...", "phone": "...", "city": "...",
  "region": "...", "address": "...", "gps_address": null, "is_verified": false, "is_active": true }
```
> Note `profile.id` (donor_id / hospital_id) differs from `user.id`.

---

### Donor endpoints (🩸 role `donor`)

#### `GET /api/donors/me` → DonorProfile
#### `PUT /api/donors/me` → updated DonorProfile
Send **only the fields to change**. Editable: `phone, city, region, gps_address, is_available (boolean),
last_donation_date (YYYY-MM-DD or null)`. **Name and blood type cannot be changed.**
Use `is_available` for the "I'm available to donate" toggle.

#### `GET /api/donors/requests` → `BloodRequest[]` (matching, open)
Each item is a *BloodRequest* plus `my_response` (`"accepted" | "declined" | null`) and
`has_responded` (bool). Empty array if the donor is unavailable.

#### `POST /api/donors/requests/{request_id}/respond`
Body: `{"status": "accepted"}` or `{"status": "declined"}`.
- `201` first response, `200` if changing an earlier response. Body: `{"request_id": 7, "status": "accepted"}`.
- A donor may switch declined ⇄ accepted while the request is open. Accepting notifies the hospital and
  shares the donor's name/phone with that hospital.
- `404 Blood request not found` – also returned if the request doesn't match this donor.
- `409 This request is no longer open`.

#### `GET /api/donors/history` → requests the donor responded to
BloodRequest items plus `my_response` and `responded_at`, newest first.

---

### Hospital endpoints (🏥 role `hospital`)

#### `GET /api/hospitals/me` → HospitalProfile
#### `PUT /api/hospitals/me` → updated HospitalProfile
Editable (send only changed fields): `name, phone, city, region, address, gps_address`.
`is_verified` cannot be changed here.

#### `GET /api/hospitals/analytics`
```json
{ "total_requests": 12, "open": 3, "fulfilled": 7, "cancelled": 2,
  "total_donors_accepted": 15,
  "requests_by_blood_type": { "A+": 1, "A-": 0, "B+": 2, "B-": 0, "AB+": 0, "AB-": 0, "O+": 6, "O-": 3 } }
```
`total_donors_accepted` counts distinct donors who accepted. All 8 blood types are always present.

#### `POST /api/requests` → `201` BloodRequest
```json
{ "blood_type": "O-", "units_needed": 3, "urgency": "critical", "note": "Surgery at 6pm" }
```
`units_needed`: integer 1–100. `note` optional (≤1000). Creating a request automatically sends an in-app
notification to every available, compatible donor in the hospital's region.

#### `GET /api/requests` → this hospital's requests, newest first
BloodRequest items plus `accepted_count` (int).

#### `GET /api/requests/{id}` → BloodRequest + `accepted_donors`
```json
{ "...BloodRequest fields...",
  "accepted_donors": [
    { "donor_id": 3, "full_name": "Kofi Mensah", "phone": "0241234567",
      "blood_type": "O+", "city": "Accra", "accepted_at": "2026-11-09T11:00:00" } ] }
```
Only the owning hospital can see this (donor phone numbers are private otherwise). `404` for other hospitals' requests.

#### `PATCH /api/requests/{id}/status`
Body: `{"status": "fulfilled"}` or `{"status": "cancelled"}`. Only allowed from `open`;
otherwise `409 Request is already fulfilled|cancelled`. Returns the BloodRequest.

**BloodRequest shape**
```json
{ "id": 7, "hospital_id": 2, "hospital_name": "...", "hospital_city": "...", "hospital_region": "...",
  "hospital_address": "...", "hospital_verified": false, "blood_type": "O-", "units_needed": 3,
  "urgency": "critical", "note": null, "status": "open", "created_at": "..." }
```

---

### Notifications (🔑 any logged-in role)
#### `GET /api/notifications` → newest first
```json
[ { "id": 9, "message": "Critical request: Korle Bu needs O- blood (3 unit(s)) in Accra.",
    "is_read": false, "created_at": "..." } ]
```
#### `PATCH /api/notifications/{id}/read` → the updated notification
No body. `404` if it isn't the caller's. There is no "mark all read" or unread-count endpoint –
compute the badge client-side from `is_read === false`.

---

### Admin endpoints (🛡️ role `admin`)
| Endpoint | Description |
|---|---|
| `GET /api/admin/stats` | `{ total_donors, total_hospitals, total_requests, accepted_responses, donors_by_blood_type: {A+:..} }` |
| `GET /api/admin/donors?blood_type=O%2B&region=Ashanti` | DonorProfile[]; both filters optional (`+` must be URL-encoded as `%2B`) |
| `GET /api/admin/hospitals` | HospitalProfile[] |
| `PATCH /api/admin/hospitals/{hospital_id}/verify` | No body. Sets `is_verified = true`. (`hospital_id` = hospital **profile** id.) Cannot un-verify. |
| `PATCH /api/admin/users/{user_id}/active` | Body `{"is_active": false}` – deactivate/reactivate. `user_id` = **user** id (`user_id` field on profiles). Cannot deactivate yourself (400). |
| `GET /api/admin/requests?status=open` | BloodRequest[]; `status` filter optional |

A deactivated user gets 401 on their next call and 403 at login.

---

## 4. Suggested app structure

**Routes**
- Public: `/login`, `/register/donor`, `/register/hospital`, `/verify-email`, `/forgot-password`, `/reset-password`
- Donor: `/donor` (matching requests), `/donor/history`, `/donor/profile`, `/notifications`
- Hospital: `/hospital` (my requests + analytics), `/hospital/new`, `/hospital/requests/:id`,
  `/hospital/profile`, `/notifications`
- Admin: `/admin` (stats), `/admin/donors`, `/admin/hospitals`, `/admin/requests`
- Guard each group by `role`; redirect to the right home after login using the `role` in the login response.

**Implementation checklist**
1. One API client module: base URL from env (`VITE_API_URL` / `NEXT_PUBLIC_API_URL`), attaches the bearer
   token, parses `{error}`, handles 401 globally, 60 s timeout.
2. Auth context: `login()`, `logout()` (just delete the token – no server logout), restore via `GET /api/auth/me`.
3. Forms mirror server validation (phone regex, 8-char password, region dropdown, units 1–100) but always
   display the server's `error` message too.
4. After `respond`, update the card from the returned status (or refetch `GET /api/donors/requests`).
5. Donor "accepted" UX: tell the donor the hospital now has their phone number.
6. Hospital detail page: show `accepted_donors` with `tel:` links.
7. Poll notifications; show unread badge.
8. Loading/empty/error states everywhere; first request may be slow (cold start).

**Not available (don't build UI for these yet):** changing password while logged in, changing email, refresh tokens,
pagination (lists return everything), search, editing a request after creation, SMS, deleting accounts.

## 5. Quick manual test (curl)
```bash
BASE=https://bloodlink-api-bli0.onrender.com
curl $BASE/api/health
curl -X POST $BASE/api/auth/login -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"..."}'
curl $BASE/api/auth/me -H "Authorization: Bearer <token>"
```
