"""Authentication, session management, and RBAC helpers for the Kudos system."""

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
from typing import Any, Dict, Optional

from db import db_session, utc_now_iso

SESSION_TTL_HOURS = 24


class AuthError(Exception):
    """Raised when authentication or authorization fails."""

    def __init__(self, message: str, status_code: int = 401, code: str = "UNAUTHORIZED"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


def verify_password(password: str, stored_hash: str) -> bool:
    """Verify a plaintext password against a stored PBKDF2-HMAC-SHA256 hash."""
    try:
        scheme, salt, expected = stored_hash.split("$", 2)
        if scheme != "pbkdf2_sha256":
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000
        ).hex()
        return hmac.compare_digest(candidate, expected)
    except ValueError:
        return False


def _serialize_user(row: Any) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "username": row["username"],
        "full_name": row["full_name"],
        "email": row["email"],
        "department": row["department"],
        "role": row["role"],
    }


class AuthService:
    """Manages user login, logout, session token verification, and role checks."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    def login(self, username: str, password: str) -> Dict[str, Any]:
        """Authenticate credentials and issue a new session token."""
        clean_username = (username or "").strip().lower()
        if not clean_username or not password:
            raise AuthError("Username and password are required", 400, "VALIDATION_ERROR")

        with db_session(self.db_path) as conn:
            user = conn.execute(
                "SELECT * FROM users WHERE lower(username) = ?",
                (clean_username,),
            ).fetchone()

            if user is None or not verify_password(password, user["password_hash"]):
                raise AuthError("Invalid username or password", 401, "INVALID_CREDENTIALS")

            token = secrets.token_urlsafe(32)
            now = datetime.now(timezone.utc)
            expires = now + timedelta(hours=SESSION_TTL_HOURS)
            conn.execute(
                """
                INSERT INTO sessions (token, user_id, created_at, expires_at)
                VALUES (?, ?, ?, ?)
                """,
                (token, user["id"], now.isoformat(), expires.isoformat()),
            )
            return {"token": token, "user": _serialize_user(user)}

    def logout(self, token: str) -> None:
        """Invalidate an active session token."""
        if not token:
            raise AuthError("Authentication token required", 401, "UNAUTHORIZED")
        with db_session(self.db_path) as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))

    def get_user_by_token(self, token: Optional[str]) -> Optional[Dict[str, Any]]:
        """Resolve an active, non-expired session token to its user dictionary."""
        if not token:
            return None
        with db_session(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT u.id, u.username, u.full_name, u.email, u.department, u.role, s.expires_at
                FROM sessions s
                JOIN users u ON u.id = s.user_id
                WHERE s.token = ?
                """,
                (token,),
            ).fetchone()
            if row is None:
                return None

            if row["expires_at"] <= utc_now_iso():
                conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
                return None

            return _serialize_user(row)

    def require_user(self, token: Optional[str]) -> Dict[str, Any]:
        """Require a valid authenticated user or raise 401 AuthError."""
        user = self.get_user_by_token(token)
        if user is None:
            raise AuthError("Authentication required", 401, "UNAUTHORIZED")
        return user

    def require_admin(self, token: Optional[str]) -> Dict[str, Any]:
        """Require an authenticated admin user or raise 401/403 AuthError."""
        user = self.require_user(token)
        if user["role"] != "admin":
            raise AuthError("Administrator privileges required", 403, "FORBIDDEN")
        return user
