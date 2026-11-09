#!/usr/bin/env bash
# Copy data from the old Render Postgres to Supabase.
#
#   OLD_DATABASE_URL=...  NEW_DATABASE_URL=...  ./scripts/migrate_data.sh
#
# Both URLs come from the environment and are never printed. Needs: psql, pg_dump
# (PostgreSQL client 15+), and the project's Python env (for `flask db upgrade`).
# Use plain postgresql:// URLs (with ?sslmode=require for remote hosts).
set -euo pipefail

: "${OLD_DATABASE_URL:?Set OLD_DATABASE_URL (Render External Database URL)}"
: "${NEW_DATABASE_URL:?Set NEW_DATABASE_URL (Supabase Session pooler URL)}"
for tool in psql pg_dump flask; do
  command -v "$tool" >/dev/null || { echo "Missing required tool: $tool" >&2; exit 1; }
done

# libpq tools reject the SQLAlchemy "+psycopg2" suffix and "postgres://" is fine, so just strip the suffix.
OLD="${OLD_DATABASE_URL/+psycopg2/}"
NEW="${NEW_DATABASE_URL/+psycopg2/}"

cd "$(dirname "$0")/.."

echo "(a) Creating schema on Supabase from Alembic migrations..."
DATABASE_URL="$NEW" flask --app run db upgrade

echo "(b) Copying data (data only; alembic_version is already set by step a)..."
# --single-transaction + ON_ERROR_STOP: a failed restore leaves Supabase untouched.
# pg_dump emits tables in foreign-key order and includes sequence values.
pg_dump "$OLD" --data-only --no-owner --no-acl --exclude-table=alembic_version \
  | psql "$NEW" --quiet --set ON_ERROR_STOP=1 --single-transaction >/dev/null

echo "(c) Comparing row counts..."
tables=$(psql "$NEW" -At -c \
  "select tablename from pg_tables where schemaname='public' and tablename<>'alembic_version' order by 1")
status=0
printf '%-22s %10s %10s  %s\n' TABLE OLD NEW RESULT
for t in $tables; do
  o=$(psql "$OLD" -At -c "select count(*) from public.\"$t\"")
  n=$(psql "$NEW" -At -c "select count(*) from public.\"$t\"")
  if [ "$o" = "$n" ]; then r=OK; else r=MISMATCH; status=1; fi
  printf '%-22s %10s %10s  %s\n' "$t" "$o" "$n" "$r"
done
[ "$status" -eq 0 ] && echo "All row counts match." || echo "Row counts differ - do NOT switch over yet." >&2
exit "$status"
