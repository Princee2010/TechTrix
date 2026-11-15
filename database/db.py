import os
import sqlite3
import config

DEFAULT_SETTINGS = {"language": "English", "style": "Simple"}


def connect():
    conn = sqlite3.connect(config.DB_PATH, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    os.makedirs(config.META_DIR, exist_ok=True)
    schema = os.path.join(os.path.dirname(__file__), "schema.sql")
    conn = connect()
    with open(schema, encoding="utf-8") as f:
        conn.executescript(f.read())
    # migrate databases created by version 1.0
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(documents)")}
    for name, ddl in (("ocr_pages", "INTEGER NOT NULL DEFAULT 0"), ("file_hash", "TEXT")):
        if name not in cols:
            conn.execute(f"ALTER TABLE documents ADD COLUMN {name} {ddl}")
    conn.commit()
    conn.close()


def reset_stuck():
    """Documents left 'processing' by a server restart can never finish."""
    x("UPDATE documents SET status='failed', error='Processing was interrupted. Delete and upload again.' "
      "WHERE status='processing'")


def q(sql, args=(), one=False):
    """Run a SELECT. Returns list of rows, or a single row/None when one=True."""
    conn = connect()
    try:
        rows = conn.execute(sql, args).fetchall()
        return (rows[0] if rows else None) if one else rows
    finally:
        conn.close()


def x(sql, args=()):
    """Run INSERT/UPDATE/DELETE. Returns lastrowid."""
    conn = connect()
    try:
        cur = conn.execute(sql, args)
        conn.commit()
        return cur.lastrowid
    finally:
        conn.close()


def get_settings():
    s = dict(DEFAULT_SETTINGS)
    for r in q("SELECT key, value FROM settings"):
        s[r["key"]] = r["value"]
    return s


def set_setting(key, value):
    x("INSERT INTO settings(key, value) VALUES(?, ?) "
      "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
