#!/usr/bin/env python3
"""Comprehensive unit and API integration tests for the Datacom Kudos System."""

import json
import os
import tempfile
import unittest

from server import KudosApp


class TestKudosEndToEnd(unittest.TestCase):
    """Tests all functional requirements, RBAC, moderation, anti-spam, and schema constraints."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_kudos.db")
        self.app = KudosApp(db_path=self.db_path, seed_demo_data=True)

    def tearDown(self):
        self.temp_dir.cleanup()

    def _request(self, method: str, path: str, body=None, token: str | None = None):
        raw_body = json.dumps(body).encode("utf-8") if body is not None else b""
        headers = {}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"

        status, resp_headers, resp_body = self.app.handle(
            method=method, raw_path=path, headers=headers, raw_body=raw_body
        )
        if resp_headers.get("Content-Type", "").startswith("application/json"):
            return status, json.loads(resp_body.decode("utf-8"))
        return status, resp_body.decode("utf-8")

    def _login(self, username: str, password: str) -> tuple[str, dict]:
        status, payload = self._request(
            "POST", "/api/auth/login", {"username": username, "password": password}
        )
        self.assertEqual(status, 200)
        return payload["token"], payload["user"]

    def test_health_and_static_index_served(self):
        status, data = self._request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "ok")

        status, html_body = self._request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("Datacom Kudos", html_body)

        # Path traversal attempt blocked
        status, _ = self._request("GET", "/../app.py")
        self.assertEqual(status, 404)

    def test_auth_login_logout_and_invalid_credentials(self):
        status, _ = self._request(
            "POST", "/api/auth/login", {"username": "alice", "password": "wrong"}
        )
        self.assertEqual(status, 401)

        token, user = self._login("alice", "demo123")
        self.assertEqual(user["role"], "employee")

        status, me = self._request("GET", "/api/auth/me", token=token)
        self.assertEqual(status, 200)
        self.assertEqual(me["user"]["username"], "alice")

        status, _ = self._request("POST", "/api/auth/logout", token=token)
        self.assertEqual(status, 200)

        status, _ = self._request("GET", "/api/auth/me", token=token)
        self.assertEqual(status, 401)

    def test_colleague_directory_excludes_self(self):
        token, alice = self._login("alice", "demo123")
        status, data = self._request("GET", "/api/users?exclude_self=true", token=token)
        self.assertEqual(status, 200)
        ids = [u["id"] for u in data["users"]]
        self.assertNotIn(alice["id"], ids)
        self.assertGreaterEqual(len(ids), 4)

    def test_create_kudos_and_appear_in_public_feed(self):
        token, _ = self._login("alice", "demo123")
        status, created = self._request(
            "POST",
            "/api/kudos",
            {
                "recipient_id": 2,
                "message": "Thanks for helping debug the production pipeline!",
                "category": "Teamwork",
            },
            token=token,
        )
        self.assertEqual(status, 201)
        kudos = created["kudos"]
        self.assertTrue(kudos["is_visible"])
        self.assertEqual(kudos["recipient"]["id"], 2)

        # Public feed requires no auth and shows newest item first
        status, feed = self._request("GET", "/api/kudos?page=1&page_size=5")
        self.assertEqual(status, 200)
        self.assertEqual(feed["items"][0]["id"], kudos["id"])

    def test_validation_self_kudos_empty_and_over_500_chars(self):
        token, alice = self._login("alice", "demo123")

        # Self-kudos rejected
        status, err = self._request(
            "POST",
            "/api/kudos",
            {"recipient_id": alice["id"], "message": "I am awesome"},
            token=token,
        )
        self.assertEqual(status, 400)
        self.assertEqual(err["error"]["code"], "SELF_KUDOS_NOT_ALLOWED")

        # Empty message rejected
        status, _ = self._request(
            "POST",
            "/api/kudos",
            {"recipient_id": 2, "message": "   "},
            token=token,
        )
        self.assertEqual(status, 400)

        # >500 chars rejected
        status, err = self._request(
            "POST",
            "/api/kudos",
            {"recipient_id": 2, "message": "x" * 501},
            token=token,
        )
        self.assertEqual(status, 400)
        self.assertEqual(err["error"]["code"], "MESSAGE_TOO_LONG")

        # Unknown recipient rejected
        status, _ = self._request(
            "POST",
            "/api/kudos",
            {"recipient_id": 9999, "message": "Hello!"},
            token=token,
        )
        self.assertEqual(status, 404)

    def test_xss_sanitization_duplicate_guard_and_rate_limiting(self):
        token, _ = self._login("bob", "demo123")

        # XSS angle brackets neutralized
        status, created = self._request(
            "POST",
            "/api/kudos",
            {"recipient_id": 1, "message": "<script>alert('xss')</script> Great work!"},
            token=token,
        )
        self.assertEqual(status, 201)
        self.assertNotIn("<script>", created["kudos"]["message"])
        self.assertIn("&lt;script&gt;", created["kudos"]["message"])

        # Immediate duplicate blocked with 409 Conflict
        status, dup = self._request(
            "POST",
            "/api/kudos",
            {"recipient_id": 1, "message": "<script>alert('xss')</script> Great work!"},
            token=token,
        )
        self.assertEqual(status, 409)
        self.assertEqual(dup["error"]["code"], "DUPLICATE_KUDOS")

        # Rate limit (>5 kudos per minute) returns 429 Too Many Requests
        for i in range(4):
            s, _ = self._request(
                "POST",
                "/api/kudos",
                {"recipient_id": 1, "message": f"Unique kudos number {i}"},
                token=token,
            )
            self.assertEqual(s, 201)

        status, rate_err = self._request(
            "POST",
            "/api/kudos",
            {"recipient_id": 1, "message": "Sixth kudos within one minute"},
            token=token,
        )
        self.assertEqual(status, 429)
        self.assertEqual(rate_err["error"]["code"], "RATE_LIMIT_EXCEEDED")

    def test_admin_moderation_hide_restore_delete_and_rbac(self):
        emp_token, _ = self._login("alice", "demo123")
        admin_token, admin_user = self._login("admin", "admin123")

        # Employee posts a kudos
        status, created = self._request(
            "POST",
            "/api/kudos",
            {"recipient_id": 2, "message": "Inappropriate test message"},
            token=emp_token,
        )
        self.assertEqual(status, 201)
        kudos_id = created["kudos"]["id"]

        # Employee cannot moderate, delete, or view hidden kudos / audit logs
        s_hide, _ = self._request(
            "PATCH",
            f"/api/admin/kudos/{kudos_id}/visibility",
            {"is_visible": False, "reason": "Unauthorized attempt"},
            token=emp_token,
        )
        self.assertEqual(s_hide, 403)

        s_del, _ = self._request("DELETE", f"/api/admin/kudos/{kudos_id}", token=emp_token)
        self.assertEqual(s_del, 403)

        s_hidden, _ = self._request("GET", "/api/kudos?include_hidden=true", token=emp_token)
        self.assertEqual(s_hidden, 403)

        s_audit, _ = self._request("GET", "/api/admin/audit-logs", token=emp_token)
        self.assertEqual(s_audit, 403)

        # Admin hiding requires a reason
        s_no_reason, _ = self._request(
            "PATCH",
            f"/api/admin/kudos/{kudos_id}/visibility",
            {"is_visible": False, "reason": ""},
            token=admin_token,
        )
        self.assertEqual(s_no_reason, 400)

        # Admin hides kudos with valid reason
        s_ok, moderated = self._request(
            "PATCH",
            f"/api/admin/kudos/{kudos_id}/visibility",
            {"is_visible": False, "reason": "Violates workplace code of conduct"},
            token=admin_token,
        )
        self.assertEqual(s_ok, 200)
        self.assertFalse(moderated["kudos"]["is_visible"])
        self.assertEqual(moderated["kudos"]["moderation"]["moderated_by"], admin_user["id"])
        self.assertEqual(
            moderated["kudos"]["moderation"]["reason_for_moderation"],
            "Violates workplace code of conduct",
        )

        # Hidden kudos disappears from public feed
        _, public_feed = self._request("GET", "/api/kudos")
        self.assertNotIn(kudos_id, [k["id"] for k in public_feed["items"]])

        # Admin can still view hidden kudos with include_hidden=true
        s_adm_feed, adm_feed = self._request(
            "GET", "/api/kudos?include_hidden=true", token=admin_token
        )
        self.assertEqual(s_adm_feed, 200)
        self.assertIn(kudos_id, [k["id"] for k in adm_feed["items"]])

        # Admin restores kudos
        s_restore, restored = self._request(
            "PATCH",
            f"/api/admin/kudos/{kudos_id}/visibility",
            {"is_visible": True, "reason": "Reviewed and approved"},
            token=admin_token,
        )
        self.assertEqual(s_restore, 200)
        self.assertTrue(restored["kudos"]["is_visible"])

        # Admin permanently deletes kudos
        s_delete, del_res = self._request(
            "DELETE",
            f"/api/admin/kudos/{kudos_id}",
            {"reason": "Permanent removal"},
            token=admin_token,
        )
        self.assertEqual(s_delete, 200)
        self.assertEqual(del_res["deleted_id"], kudos_id)

        # Audit log recorded HIDE, RESTORE, and DELETE in reverse chronological order
        s_logs, logs_res = self._request("GET", "/api/admin/audit-logs", token=admin_token)
        self.assertEqual(s_logs, 200)
        actions = [entry["action"] for entry in logs_res["logs"][:3]]
        self.assertEqual(actions, ["DELETE", "RESTORE", "HIDE"])

    def test_pagination_and_filtering(self):
        status, filtered = self._request("GET", "/api/kudos?category=Innovation")
        self.assertEqual(status, 200)
        self.assertEqual(len(filtered["items"]), 1)
        self.assertEqual(filtered["items"][0]["category"], "Innovation")

        status, page1 = self._request("GET", "/api/kudos?page=1&page_size=2")
        self.assertEqual(status, 200)
        self.assertEqual(len(page1["items"]), 2)
        self.assertTrue(page1["has_more"])

        status, page2 = self._request("GET", "/api/kudos?page=2&page_size=2")
        self.assertEqual(status, 200)
        self.assertEqual(len(page2["items"]), 1)
        self.assertFalse(page2["has_more"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
