from app.config import engine_options_for, normalize_database_url


def test_scheme_rewritten_to_psycopg2():
    assert normalize_database_url("postgres://u:p@localhost/db").startswith("postgresql+psycopg2://")
    assert normalize_database_url("postgresql://u:p@localhost/db").startswith("postgresql+psycopg2://")
    assert normalize_database_url("postgresql+psycopg2://u:p@localhost/db").count("psycopg2") == 1


def test_sslmode_added_for_remote_hosts_only():
    remote = normalize_database_url("postgres://u:p@aws-0.pooler.supabase.com:5432/postgres")
    assert remote.endswith("?sslmode=require")
    assert "sslmode" not in normalize_database_url("postgresql://u:p@localhost:5432/db")
    assert "sslmode" not in normalize_database_url("postgresql://u:p@127.0.0.1:5432/db")


def test_existing_sslmode_is_kept():
    url = normalize_database_url("postgresql://u:p@db.example.com/x?sslmode=verify-full")
    assert url.count("sslmode") == 1 and "verify-full" in url


def test_sqlite_untouched_and_no_pool_options():
    assert normalize_database_url("sqlite:///bloodlink.db") == "sqlite:///bloodlink.db"
    assert engine_options_for("sqlite:///bloodlink.db") == {}


def test_postgres_pool_options():
    opts = engine_options_for("postgresql+psycopg2://u:p@h/db")
    assert opts == {"pool_pre_ping": True, "pool_recycle": 300, "pool_size": 5, "max_overflow": 5}
