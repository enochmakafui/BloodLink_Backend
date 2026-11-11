# Frontend update: Print form, admin reports, permanent delete

Three backend additions. Nothing existing changed (no breaking changes).
Base URL: `https://bloodlink-api-bli0.onrender.com`. All endpoints need the JWT: `Authorization: Bearer <token>`.

| # | Feature | Who | Endpoint |
|---|---|---|---|
| 1 | Print submitted form | donor | `GET /api/donors/me/form` |
| 2 | Download reports (PDF / Word / Excel) | admin | `GET /api/admin/reports/{kind}?format=` |
| 3 | Permanently delete a user | admin | `DELETE /api/admin/users/{user_id}` |

Because these need the auth header, you **cannot** use a plain `<a href>`. Fetch the file, turn it into a blob, then open or save it.

## Shared helper

```js
const API = "https://bloodlink-api-bli0.onrender.com";

async function fetchBlob(path, token) {
  const res = await fetch(API + path, { headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `Request failed (${res.status})`);
  }
  return res.blob();
}

function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = Object.assign(document.createElement("a"), { href: url, download: filename });
  document.body.appendChild(a); a.click(); a.remove();
  URL.revokeObjectURL(url);
}
```

## 1. Donor: print form

Add a **Print my form** button on the donor's page (and on the success screen after registration/verification).

`GET /api/donors/me/form` returns `application/pdf` (inline): a one-page copy of the donor's details with a signature line.

```js
async function printDonorForm(token) {
  const blob = await fetchBlob("/api/donors/me/form", token);
  const url = URL.createObjectURL(new Blob([blob], { type: "application/pdf" }));
  const win = window.open(url);          // opens the PDF viewer, which has its own Print button
  win?.addEventListener("load", () => win.print());
}
```

- Add `?download=1` to force a file download instead (`bloodlink-donor-form.pdf`), e.g. a "Download PDF" button using `saveBlob`.
- If the popup is blocked, fall back to `saveBlob`.
- 403 if the logged-in user is not a donor.

## 2. Admin: download reports

Add a **Download** dropdown (PDF / Word / Excel) to the admin Donors, Hospitals and Requests pages.

`GET /api/admin/reports/{kind}?format={fmt}`

| `kind` | Page | Extra filters (same as the list endpoint) |
|---|---|---|
| `donors` | `/admin/donors` | `blood_type` (URL-encode `+` as `%2B`), `region` |
| `hospitals` | `/admin/hospitals` | none |
| `requests` | `/admin/requests` | `status` = `open\|fulfilled\|cancelled` |

| `format` | File | Notes |
|---|---|---|
| `pdf` (default) | `.pdf` | |
| `docx` | `.docx` | `word` also accepted |
| `xlsx` | `.xlsx` | `excel` also accepted |

Pass the page's **current filters** so the report matches what the admin is looking at.

```js
const EXT = { pdf: "pdf", docx: "docx", xlsx: "xlsx" };

async function downloadReport(kind, fmt, token, filters = {}) {
  const qs = new URLSearchParams({ format: fmt, ...filters }); // encodes "+" correctly
  const blob = await fetchBlob(`/api/admin/reports/${kind}?${qs}`, token);
  saveBlob(blob, `bloodlink-${kind}-report.${EXT[fmt]}`);
}

// downloadReport("donors", "xlsx", token, { blood_type: "O+", region: "Ashanti" });
```

Errors: 400 bad `format`, 404 unknown `kind`, 403 not admin. Show a loading state; large reports can take a moment.

## 3. Admin: permanently delete a user

Keep the existing **Deactivate** toggle (reversible) and add a separate **Delete** button on donor and hospital rows.

`DELETE /api/admin/users/{user_id}` → `200 {"deleted": true, "user_id": 12}`

- `user_id` is the **user** id (the `user_id` field on a donor/hospital profile), not the profile `id`.
- This is **irreversible**. It removes the account, profile, notifications and verification codes. Deleting a **hospital** also deletes all its blood requests and the donors' responses to them. Deleting a donor removes their responses.
- Use a confirmation dialog. Suggested text: *"Permanently delete {name}? This cannot be undone. Use Deactivate if you may want to restore this account."* For hospitals add: *"All of its blood requests will also be deleted."*
- Errors: 400 `You cannot delete your own account` / `Admin accounts cannot be deleted` (hide the button for admin rows), 404 user not found.

```js
async function deleteUser(userId, token) {
  const res = await fetch(`${API}/api/admin/users/${userId}`, {
    method: "DELETE",
    headers: { Authorization: `Bearer ${token}` },
  });
  const body = await res.json();
  if (!res.ok) throw new Error(body.error);
  return body;   // then remove the row from local state / refetch the list
}
```

After success, remove the row from the list (or refetch `GET /api/admin/donors` / `/hospitals`) and refresh the stats.

## Checklist

- [ ] Donor page: **Print my form** button (+ optional Download PDF)
- [ ] Admin donors / hospitals / requests pages: **Download** menu (PDF, Word, Excel) passing current filters
- [ ] Admin donors / hospitals pages: **Delete** button with confirm dialog; hide for admin accounts
- [ ] Handle errors by showing `error` from the JSON body
