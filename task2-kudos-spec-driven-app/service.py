"""Core business logic for the Kudos feature, including moderation and anti-abuse guards."""

from collections import defaultdict, deque
import logging
import re
import time
from typing import Any, Deque, Dict, List, Optional

from db import db_session, utc_now_iso

logger = logging.getLogger(__name__)

VALID_CATEGORIES = ("Teamwork", "Innovation", "Leadership", "Customer Focus", "Excellence")
MAX_MESSAGE_LENGTH = 500
MAX_PAGE_SIZE = 50
DEFAULT_PAGE_SIZE = 10
MAX_KUDOS_PER_MINUTE = 5
RATE_LIMIT_WINDOW_SECONDS = 60
DUPLICATE_WINDOW_SECONDS = 300
MIN_MODERATION_REASON_LENGTH = 3

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class ServiceError(Exception):
    """Domain error with explicit HTTP status code and machine-readable code."""

    def __init__(self, message: str, status_code: int = 400, code: str = "VALIDATION_ERROR"):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


def sanitize_text(raw: str) -> str:
    """Strip control characters, trim outer whitespace, and neutralize HTML angle brackets."""
    cleaned = _CONTROL_CHARS_RE.sub("", raw or "").strip()
    return cleaned.replace("<", "&lt;").replace(">", "&gt;")


def _serialize_kudos(row: Any) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "sender": {
            "id": row["sender_id"],
            "full_name": row["sender_name"],
            "department": row["sender_department"],
        },
        "recipient": {
            "id": row["recipient_id"],
            "full_name": row["recipient_name"],
            "department": row["recipient_department"],
        },
        "message": row["message"],
        "category": row["category"],
        "created_at": row["created_at"],
        "is_visible": bool(row["is_visible"]),
        "moderation": {
            "moderated_by": row["moderated_by"],
            "moderated_by_name": row["moderator_name"],
            "moderated_at": row["moderated_at"],
            "reason_for_moderation": row["reason_for_moderation"],
        }
        if row["moderated_at"] is not None
        else None,
    }


class KudosService:
    """Handles colleague directory, kudos creation, paginated feeds, and moderation."""

    def __init__(
        self,
        db_path: str,
        max_kudos_per_minute: int = MAX_KUDOS_PER_MINUTE,
        duplicate_window_seconds: int = DUPLICATE_WINDOW_SECONDS,
    ) -> None:
        self.db_path = db_path
        self.max_kudos_per_minute = max_kudos_per_minute
        self.duplicate_window_seconds = duplicate_window_seconds
        self._rate_buckets: Dict[int, Deque[float]] = defaultdict(deque)

    def _check_rate_limit(self, sender_id: int) -> None:
        now = time.monotonic()
        bucket = self._rate_buckets[sender_id]
        cutoff = now - RATE_LIMIT_WINDOW_SECONDS
        while bucket and bucket[0] < cutoff:
            bucket.popleft()
        if len(bucket) >= self.max_kudos_per_minute:
            logger.warning("Rate limit exceeded for user_id=%s", sender_id)
            raise ServiceError(
                f"Rate limit exceeded: maximum {self.max_kudos_per_minute} kudos per minute.",
                status_code=429,
                code="RATE_LIMIT_EXCEEDED",
            )
        bucket.append(now)

    def list_users(self, exclude_user_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """List colleagues sorted alphabetically by full name."""
        with db_session(self.db_path) as conn:
            if exclude_user_id is not None:
                rows = conn.execute(
                    """
                    SELECT id, username, full_name, email, department, role
                    FROM users
                    WHERE id != ?
                    ORDER BY full_name ASC
                    """,
                    (exclude_user_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, username, full_name, email, department, role
                    FROM users
                    ORDER BY full_name ASC
                    """
                ).fetchall()
            return [dict(row) for row in rows]

    def create_kudos(
        self,
        sender_id: int,
        recipient_id: Any,
        message: Any,
        category: str = "Teamwork",
    ) -> Dict[str, Any]:
        """Validate, sanitize, and persist a new kudos message."""
        try:
            recipient_int = int(recipient_id)
        except (TypeError, ValueError):
            raise ServiceError("recipient_id must be a valid integer", 400, "VALIDATION_ERROR")

        if sender_id == recipient_int:
            raise ServiceError("You cannot send kudos to yourself.", 400, "SELF_KUDOS_NOT_ALLOWED")

        if not isinstance(message, str):
            raise ServiceError("Message must be a text string.", 400, "VALIDATION_ERROR")

        raw_trimmed = _CONTROL_CHARS_RE.sub("", message).strip()
        if not raw_trimmed:
            raise ServiceError("Kudos message cannot be empty.", 400, "VALIDATION_ERROR")
        if len(raw_trimmed) > MAX_MESSAGE_LENGTH:
            raise ServiceError(
                f"Kudos message must be {MAX_MESSAGE_LENGTH} characters or fewer.",
                400,
                "MESSAGE_TOO_LONG",
            )

        clean_category = (category or "Teamwork").strip()
        if clean_category not in VALID_CATEGORIES:
            raise ServiceError(
                f"Invalid category. Choose one of: {', '.join(VALID_CATEGORIES)}",
                400,
                "INVALID_CATEGORY",
            )

        safe_message = sanitize_text(raw_trimmed)

        with db_session(self.db_path) as conn:
            recipient = conn.execute(
                "SELECT id FROM users WHERE id = ?", (recipient_int,)
            ).fetchone()
            if recipient is None:
                raise ServiceError("Selected colleague does not exist.", 404, "RECIPIENT_NOT_FOUND")

            # Check duplicate submission within rolling duplicate window
            recent_same = conn.execute(
                """
                SELECT id, created_at
                FROM kudos
                WHERE sender_id = ? AND recipient_id = ? AND lower(message) = lower(?)
                ORDER BY id DESC
                LIMIT 1
                """,
                (sender_id, recipient_int, safe_message),
            ).fetchone()
            if recent_same is not None:
                from datetime import datetime, timezone

                prev_dt = datetime.fromisoformat(recent_same["created_at"])
                age_seconds = (datetime.now(timezone.utc) - prev_dt).total_seconds()
                if age_seconds <= self.duplicate_window_seconds:
                    raise ServiceError(
                        "Duplicate kudos detected: you already sent this exact message recently.",
                        status_code=409,
                        code="DUPLICATE_KUDOS",
                    )

            # Enforce per-user spam rate limit after validating payload
            self._check_rate_limit(sender_id)

            now = utc_now_iso()
            cursor = conn.execute(
                """
                INSERT INTO kudos (sender_id, recipient_id, message, category, created_at, is_visible)
                VALUES (?, ?, ?, ?, ?, 1)
                """,
                (sender_id, recipient_int, safe_message, clean_category, now),
            )
            kudos_id = cursor.lastrowid
            row = self._fetch_kudos_row(conn, kudos_id)
            logger.info(
                "Created kudos id=%s sender=%s recipient=%s category=%s",
                kudos_id,
                sender_id,
                recipient_int,
                clean_category,
            )
            return _serialize_kudos(row)

    def _fetch_kudos_row(self, conn: Any, kudos_id: int) -> Any:
        return conn.execute(
            """
            SELECT
                k.*,
                s.full_name AS sender_name,
                s.department AS sender_department,
                r.full_name AS recipient_name,
                r.department AS recipient_department,
                m.full_name AS moderator_name
            FROM kudos k
            JOIN users s ON s.id = k.sender_id
            JOIN users r ON r.id = k.recipient_id
            LEFT JOIN users m ON m.id = k.moderated_by
            WHERE k.id = ?
            """,
            (kudos_id,),
        ).fetchone()

    def list_kudos(
        self,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        category: Optional[str] = None,
        search: Optional[str] = None,
        include_hidden: bool = False,
    ) -> Dict[str, Any]:
        """Return paginated kudos feed ordered newest-first."""
        if page < 1:
            raise ServiceError("page must be >= 1", 400, "VALIDATION_ERROR")
        if page_size < 1 or page_size > MAX_PAGE_SIZE:
            raise ServiceError(
                f"page_size must be between 1 and {MAX_PAGE_SIZE}",
                400,
                "VALIDATION_ERROR",
            )

        conditions: List[str] = []
        params: List[Any] = []

        if not include_hidden:
            conditions.append("k.is_visible = 1")

        if category and category.strip():
            conditions.append("k.category = ?")
            params.append(category.strip())

        if search and search.strip():
            pattern = f"%{search.strip().lower()}%"
            conditions.append(
                "(lower(k.message) LIKE ? OR lower(s.full_name) LIKE ? OR lower(r.full_name) LIKE ?)"
            )
            params.extend([pattern, pattern, pattern])

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        offset = (page - 1) * page_size

        with db_session(self.db_path) as conn:
            total = conn.execute(
                f"""
                SELECT COUNT(*) AS cnt
                FROM kudos k
                JOIN users s ON s.id = k.sender_id
                JOIN users r ON r.id = k.recipient_id
                {where_clause}
                """,
                params,
            ).fetchone()["cnt"]

            rows = conn.execute(
                f"""
                SELECT
                    k.*,
                    s.full_name AS sender_name,
                    s.department AS sender_department,
                    r.full_name AS recipient_name,
                    r.department AS recipient_department,
                    m.full_name AS moderator_name
                FROM kudos k
                JOIN users s ON s.id = k.sender_id
                JOIN users r ON r.id = k.recipient_id
                LEFT JOIN users m ON m.id = k.moderated_by
                {where_clause}
                ORDER BY k.created_at DESC, k.id DESC
                LIMIT ? OFFSET ?
                """,
                [*params, page_size, offset],
            ).fetchall()

        items = [_serialize_kudos(r) for r in rows]
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "has_more": (offset + len(items)) < total,
        }

    def set_kudos_visibility(
        self,
        kudos_id: int,
        is_visible: bool,
        admin_id: int,
        reason: str = "",
    ) -> Dict[str, Any]:
        """Hide or restore a kudos item and record an immutable moderation audit entry."""
        if not isinstance(is_visible, bool):
            raise ServiceError("is_visible must be a boolean.", 400, "VALIDATION_ERROR")

        clean_reason = sanitize_text(reason)
        if not is_visible and len(clean_reason) < MIN_MODERATION_REASON_LENGTH:
            raise ServiceError(
                f"A moderation reason of at least {MIN_MODERATION_REASON_LENGTH} characters is required when hiding kudos.",
                400,
                "REASON_REQUIRED",
            )
        if is_visible and not clean_reason:
            clean_reason = "Restored by administrator"

        action = "RESTORE" if is_visible else "HIDE"
        now = utc_now_iso()

        with db_session(self.db_path) as conn:
            existing = conn.execute("SELECT id FROM kudos WHERE id = ?", (kudos_id,)).fetchone()
            if existing is None:
                raise ServiceError(f"Kudos {kudos_id} not found.", 404, "NOT_FOUND")

            conn.execute(
                """
                UPDATE kudos
                SET is_visible = ?,
                    moderated_by = ?,
                    moderated_at = ?,
                    reason_for_moderation = ?
                WHERE id = ?
                """,
                (1 if is_visible else 0, admin_id, now, clean_reason, kudos_id),
            )
            conn.execute(
                """
                INSERT INTO moderation_audit_log (kudos_id, action, admin_id, reason, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (kudos_id, action, admin_id, clean_reason, now),
            )
            row = self._fetch_kudos_row(conn, kudos_id)
            logger.info(
                "Moderation action=%s kudos_id=%s admin_id=%s", action, kudos_id, admin_id
            )
            return _serialize_kudos(row)

    def delete_kudos(
        self, kudos_id: int, admin_id: int, reason: str = "Deleted by administrator"
    ) -> Dict[str, Any]:
        """Permanently delete an inappropriate kudos record and log the audit action."""
        clean_reason = sanitize_text(reason) or "Deleted by administrator"
        now = utc_now_iso()

        with db_session(self.db_path) as conn:
            existing = conn.execute("SELECT id FROM kudos WHERE id = ?", (kudos_id,)).fetchone()
            if existing is None:
                raise ServiceError(f"Kudos {kudos_id} not found.", 404, "NOT_FOUND")

            conn.execute("DELETE FROM kudos WHERE id = ?", (kudos_id,))
            conn.execute(
                """
                INSERT INTO moderation_audit_log (kudos_id, action, admin_id, reason, created_at)
                VALUES (?, 'DELETE', ?, ?, ?)
                """,
                (kudos_id, admin_id, clean_reason, now),
            )
            logger.info("Moderation action=DELETE kudos_id=%s admin_id=%s", kudos_id, admin_id)
            return {"deleted_id": kudos_id, "reason": clean_reason}

    def list_audit_logs(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return recent moderation audit log entries (admin-only)."""
        safe_limit = max(1, min(int(limit), 200))
        with db_session(self.db_path) as conn:
            rows = conn.execute(
                """
                SELECT
                    l.id,
                    l.kudos_id,
                    l.action,
                    l.admin_id,
                    u.full_name AS admin_name,
                    l.reason,
                    l.created_at
                FROM moderation_audit_log l
                JOIN users u ON u.id = l.admin_id
                ORDER BY l.id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
            return [dict(r) for r in rows]
