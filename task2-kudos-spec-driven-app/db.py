"""Database initialization, schema management, and seed data for the Kudos system."""

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import os
import secrets
import sqlite3
from typing import Iterator

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    full_name TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    department TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('employee', 'admin')) DEFAULT 'employee',
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS kudos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender_id INTEGER NOT NULL,
    recipient_id INTEGER NOT NULL,
    message TEXT NOT NULL CHECK (length(trim(message)) BETWEEN 1 AND 500),
    category TEXT NOT NULL DEFAULT 'Teamwork',
    created_at TEXT NOT NULL,
    is_visible INTEGER NOT NULL DEFAULT 1 CHECK (is_visible IN (0, 1)),
    moderated_by INTEGER,
    moderated_at TEXT,
    reason_for_moderation TEXT,
    CHECK (sender_id != recipient_id),
    FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (recipient_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (moderated_by) REFERENCES users(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS moderation_audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kudos_id INTEGER NOT NULL,
    action TEXT NOT NULL CHECK (action IN ('HIDE', 'RESTORE', 'DELETE')),
    admin_id INTEGER NOT NULL,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (admin_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_kudos_visible_created
    ON kudos (is_visible, created_at DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_kudos_sender_created
    ON kudos (sender_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_kudos_recipient
    ON kudos (recipient_id);
"""


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def hash_password(password: str, salt: str | None = None) -> str:
    """Hash a password with PBKDF2-HMAC-SHA256 and a random hex salt."""
    if salt is None:
        salt = secrets.token_hex(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000
    ).hex()
    return f"pbkdf2_sha256${salt}${derived}"


def get_connection(db_path: str) -> sqlite3.Connection:
    """Open a configured SQLite connection with foreign keys and Row factory."""
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn


@contextmanager
def db_session(db_path: str) -> Iterator[sqlite3.Connection]:
    """Transactional context manager for SQLite connections."""
    conn = get_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: str, seed_demo_data: bool = True) -> None:
    """Initialize database tables, indexes, and optional demo records."""
    parent = os.path.dirname(os.path.abspath(db_path))
    if parent:
        os.makedirs(parent, exist_ok=True)

    with db_session(db_path) as conn:
        conn.executescript(SCHEMA_SQL)

        if seed_demo_data:
            existing = conn.execute("SELECT COUNT(*) AS cnt FROM users").fetchone()["cnt"]
            if existing == 0:
                _seed_initial_data(conn)


def _seed_initial_data(conn: sqlite3.Connection) -> None:
    """Populate realistic Datacom demo employees, an admin, and initial kudos."""
    now = utc_now_iso()
    demo_users = [
        ("alice", "Alice Chen", "alice.chen@datacom.example", "Engineering", "employee", "demo123"),
        ("bob", "Bob Patel", "bob.patel@datacom.example", "Cloud Ops", "employee", "demo123"),
        ("claire", "Claire Williams", "claire.williams@datacom.example", "Product", "employee", "demo123"),
        ("david", "David Kim", "david.kim@datacom.example", "Data & AI", "employee", "demo123"),
        ("admin", "Morgan Taylor", "morgan.taylor@datacom.example", "People & Culture", "admin", "admin123"),
    ]
    for username, full_name, email, dept, role, raw_pw in demo_users:
        conn.execute(
            """
            INSERT INTO users (username, full_name, email, department, role, password_hash, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (username, full_name, email, dept, role, hash_password(raw_pw), now),
        )

    demo_kudos = [
        (
            1,
            2,
            "Huge thanks for jumping on the overnight cloud incident and restoring SLA before morning standup!",
            "Customer Focus",
        ),
        (
            3,
            1,
            "Your spec-driven design walkthrough saved the whole squad days of rework. Awesome clarity!",
            "Innovation",
        ),
        (
            4,
            3,
            "Appreciate how patiently you aligned stakeholders during sprint planning this week.",
            "Leadership",
        ),
    ]
    for sender_id, recipient_id, message, category in demo_kudos:
        conn.execute(
            """
            INSERT INTO kudos (sender_id, recipient_id, message, category, created_at, is_visible)
            VALUES (?, ?, ?, ?, ?, 1)
            """,
            (sender_id, recipient_id, message, category, now),
        )
