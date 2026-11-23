"""Threaded HTTP REST API and static frontend server for the Kudos Portal."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
import mimetypes
import os
import re
from typing import Any, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from auth import AuthError, AuthService
from db import init_db, utc_now_iso
from service import DEFAULT_PAGE_SIZE, KudosService, ServiceError

logger = logging.getLogger(__name__)

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
ADMIN_VISIBILITY_RE = re.compile(r"^/api/admin/kudos/(\d+)/visibility$")
ADMIN_DELETE_RE = re.compile(r"^/api/admin/kudos/(\d+)$")
MAX_BODY_BYTES = 64 * 1024  # 64 KB cap on JSON request bodies


class KudosApp:
    """Transport-independent HTTP router for the Kudos REST API and SPA assets."""

    def __init__(self, db_path: str, seed_demo_data: bool = True) -> None:
        init_db(db_path, seed_demo_data=seed_demo_data)
        self.db_path = db_path
        self.auth_service = AuthService(db_path)
        self.kudos_service = KudosService(db_path)

    @staticmethod
    def _bearer_token(headers: Dict[str, str]) -> Optional[str]:
        auth_val = ""
        for k, v in headers.items():
            if k.lower() == "authorization":
                auth_val = v
                break
        if auth_val.startswith("Bearer "):
            return auth_val[7:].strip() or None
        return None

    @staticmethod
    def _parse_json_body(raw_body: bytes, optional: bool = False) -> Dict[str, Any]:
        if not raw_body:
            if optional:
                return {}
            raise ServiceError("Request body is required.", 400, "VALIDATION_ERROR")
        if len(raw_body) > MAX_BODY_BYTES:
            raise ServiceError("Request body too large.", 413, "PAYLOAD_TOO_LARGE")
        try:
            parsed = json.loads(raw_body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ServiceError("Malformed JSON request body.", 400, "INVALID_JSON")
        if not isinstance(parsed, dict):
            raise ServiceError("JSON body must be an object.", 400, "VALIDATION_ERROR")
        return parsed

    @staticmethod
    def _json_response(
        status_code: int,
        payload: Dict[str, Any],
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Tuple[int, Dict[str, str], bytes]:
        body = json.dumps(payload).encode("utf-8")
        headers = {
            "Content-Type": "application/json; charset=utf-8",
            "X-Content-Type-Options": "nosniff",
        }
        if extra_headers:
            headers.update(extra_headers)
        return status_code, headers, body

    @classmethod
    def _error_response(
        cls, status_code: int, code: str, message: str
    ) -> Tuple[int, Dict[str, str], bytes]:
        return cls._json_response(
            status_code, {"error": {"code": code, "message": message}}
        )

    @classmethod
    def _serve_static(cls, req_path: str) -> Tuple[int, Dict[str, str], bytes]:
        rel = "index.html" if req_path in ("/", "") else req_path.lstrip("/")
        if rel.startswith("static/"):
            rel = rel[len("static/") :]

        candidate = os.path.abspath(os.path.join(STATIC_DIR, rel))
        static_root = os.path.abspath(STATIC_DIR)
        if not candidate.startswith(static_root + os.sep) or not os.path.isfile(candidate):
            return cls._error_response(404, "NOT_FOUND", "Resource not found.")

        content_type, _ = mimetypes.guess_type(candidate)
        with open(candidate, "rb") as f:
            content = f.read()

        return (
            200,
            {
                "Content-Type": content_type or "application/octet-stream",
                "X-Content-Type-Options": "nosniff",
            },
            content,
        )

    def handle(
        self,
        method: str,
        raw_path: str,
        headers: Optional[Dict[str, str]] = None,
        raw_body: bytes = b"",
    ) -> Tuple[int, Dict[str, str], bytes]:
        """Dispatch an HTTP request and return (status_code, headers, body_bytes)."""
        req_headers = headers or {}
        parsed = urlparse(raw_path)
        path = parsed.path
        query = parse_qs(parsed.query)
        token = self._bearer_token(req_headers)

        try:
            if method == "GET" and path == "/api/health":
                return self._json_response(
                    200, {"status": "ok", "timestamp": utc_now_iso()}
                )

            if method == "POST" and path == "/api/auth/login":
                body = self._parse_json_body(raw_body)
                result = self.auth_service.login(
                    body.get("username", ""), body.get("password", "")
                )
                return self._json_response(200, result)

            if method == "POST" and path == "/api/auth/logout":
                self.auth_service.logout(token or "")
                return self._json_response(200, {"message": "Logged out"})

            if method == "GET" and path == "/api/auth/me":
                user = self.auth_service.require_user(token)
                return self._json_response(200, {"user": user})

            if method == "GET" and path == "/api/users":
                user = self.auth_service.require_user(token)
                exclude_self = query.get("exclude_self", ["false"])[0].lower() == "true"
                users = self.kudos_service.list_users(
                    exclude_user_id=user["id"] if exclude_self else None
                )
                return self._json_response(
                    200,
                    {"users": users},
                    extra_headers={"Cache-Control": "private, max-age=60"},
                )

            if method == "GET" and path == "/api/kudos":
                include_hidden = (
                    query.get("include_hidden", ["false"])[0].lower() == "true"
                )
                if include_hidden:
                    self.auth_service.require_admin(token)

                try:
                    page = int(query.get("page", ["1"])[0])
                    page_size = int(
                        query.get("page_size", [str(DEFAULT_PAGE_SIZE)])[0]
                    )
                except ValueError:
                    raise ServiceError(
                        "page and page_size must be integers.", 400, "VALIDATION_ERROR"
                    )

                category = query.get("category", [None])[0]
                search = query.get("search", [None])[0]
                feed = self.kudos_service.list_kudos(
                    page=page,
                    page_size=page_size,
                    category=category,
                    search=search,
                    include_hidden=include_hidden,
                )
                return self._json_response(200, feed)

            if method == "POST" and path == "/api/kudos":
                user = self.auth_service.require_user(token)
                body = self._parse_json_body(raw_body)
                created = self.kudos_service.create_kudos(
                    sender_id=user["id"],
                    recipient_id=body.get("recipient_id"),
                    message=body.get("message"),
                    category=body.get("category", "Teamwork"),
                )
                return self._json_response(201, {"kudos": created})

            vis_match = ADMIN_VISIBILITY_RE.match(path)
            if method == "PATCH" and vis_match:
                admin = self.auth_service.require_admin(token)
                kudos_id = int(vis_match.group(1))
                body = self._parse_json_body(raw_body)
                updated = self.kudos_service.set_kudos_visibility(
                    kudos_id=kudos_id,
                    is_visible=body.get("is_visible"),
                    admin_id=admin["id"],
                    reason=body.get("reason", ""),
                )
                return self._json_response(200, {"kudos": updated})

            del_match = ADMIN_DELETE_RE.match(path)
            if method == "DELETE" and del_match:
                admin = self.auth_service.require_admin(token)
                kudos_id = int(del_match.group(1))
                body = self._parse_json_body(raw_body, optional=True)
                deleted = self.kudos_service.delete_kudos(
                    kudos_id=kudos_id,
                    admin_id=admin["id"],
                    reason=body.get("reason", "Deleted by administrator"),
                )
                return self._json_response(200, deleted)

            if method == "GET" and path == "/api/admin/audit-logs":
                self.auth_service.require_admin(token)
                try:
                    limit = int(query.get("limit", ["50"])[0])
                except ValueError:
                    raise ServiceError("limit must be an integer.", 400, "VALIDATION_ERROR")
                logs = self.kudos_service.list_audit_logs(limit=limit)
                return self._json_response(200, {"logs": logs})

            if method == "GET" and not path.startswith("/api/"):
                return self._serve_static(path)

            return self._error_response(
                404, "NOT_FOUND", f"Endpoint {method} {path} not found."
            )

        except AuthError as err:
            return self._error_response(err.status_code, err.code, err.message)
        except ServiceError as err:
            return self._error_response(err.status_code, err.code, err.message)
        except Exception:
            logger.exception("Unhandled error processing %s %s", method, path)
            return self._error_response(
                500, "INTERNAL_SERVER_ERROR", "An unexpected error occurred."
            )


class KudosHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer hosting a KudosApp instance."""

    allow_reuse_address = True

    def __init__(
        self,
        server_address: Tuple[str, int],
        db_path: str,
        seed_demo_data: bool = True,
    ) -> None:
        self.app = KudosApp(db_path=db_path, seed_demo_data=seed_demo_data)
        super().__init__(server_address, KudosRequestHandler)


class KudosRequestHandler(BaseHTTPRequestHandler):
    """HTTP adapter delegating requests to `self.server.app`."""

    server: KudosHTTPServer

    def log_message(self, format: str, *args: Any) -> None:
        logger.info("%s - %s", self.address_string(), format % args)

    def _dispatch(self, method: str) -> None:
        raw_len = self.headers.get("Content-Length")
        raw_body = b""
        if raw_len:
            try:
                length = int(raw_len)
            except ValueError:
                length = -1
            if length < 0 or length > MAX_BODY_BYTES:
                status, headers, body = KudosApp._error_response(
                    413 if length > MAX_BODY_BYTES else 400,
                    "PAYLOAD_TOO_LARGE" if length > MAX_BODY_BYTES else "VALIDATION_ERROR",
                    "Invalid or oversized request body.",
                )
                self._write_response(status, headers, body)
                return
            if length > 0:
                raw_body = self.rfile.read(length)

        status, headers, body = self.server.app.handle(
            method=method,
            raw_path=self.path,
            headers=dict(self.headers.items()),
            raw_body=raw_body,
        )
        self._write_response(status, headers, body)

    def _write_response(
        self, status_code: int, headers: Dict[str, str], body: bytes
    ) -> None:
        self.send_response(status_code)
        for key, value in headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_PATCH(self) -> None:
        self._dispatch("PATCH")

    def do_DELETE(self) -> None:
        self._dispatch("DELETE")
