# Using Supabase Postgres

Supabase is used as a plain Postgres database only (no SDK, auth or storage).

## Set DATABASE_URL on Render
1. Supabase: **Connect** → **Session pooler** → copy the URI. It looks like
   `postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres`.
   Replace `[YOUR-PASSWORD]` with your password, **URL-encoded** (`@` → `%40`, `#` → `%23`, `/` → `%2F`).
2. Render: service `bloodlink-api` → **Environment** → set `DATABASE_URL` to that URI → save.
   `render.yaml` marks it `sync: false`, so Render never overwrites it.
3. Redeploy. The container runs `flask --app run db upgrade` on start, creating the tables.

The app rewrites the scheme to `postgresql+psycopg2://` and adds `sslmode=require` for non-local hosts automatically.

## Why the Session pooler
Supabase's direct connection (`db.<ref>.supabase.co`) is IPv6-only on the free tier, and Render's free tier
can't reach IPv6 hosts. The Session pooler is IPv4 and supports the long-lived connections SQLAlchemy uses.
(Avoid the Transaction pooler on port 6543 - it breaks prepared statements/session state.)

Each gunicorn worker keeps up to 5 + 5 overflow connections (2 workers → up to 20). If you see
"max clients reached", set `--workers 1` in the Dockerfile or lower `pool_size` in `app/config.py`.

## Verify
- `curl https://<your-service>.onrender.com/api/health` → `{"status":"ok"}` (note: this does not touch the DB).
- Check the deploy logs show the Alembic migration ran with no errors.
- Supabase **Table Editor** shows the six tables; a real DB check is logging in or registering a user.

## Copying existing data
`scripts/migrate_data.sh` (needs `psql`/`pg_dump`, set `OLD_DATABASE_URL` and `NEW_DATABASE_URL` in your shell).
It runs migrations on Supabase first, restores data only, then compares row counts per table.
