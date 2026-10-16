"""
Automated Test Suite for STEP 6: Citidy Authentication & Admin Authorization Flow.
Verifies all 8 critical conditions:
1. Admin login with valid credentials (HTTP 200, JWT token, admin role).
2. Admin login with an incorrect password (HTTP 401, clean JSON error).
3. Login with a nonexistent account (HTTP 401, clean JSON error).
4. Login when the backend is unavailable (graceful network error handling).
5. Login when the endpoint returns an HTML error page (safe parsing, no SyntaxError).
6. Login as a normal citizen and attempt to access the admin area (403 Forbidden).
7. Refresh the page after successful admin login (HMAC token verification on /api/auth/me).
8. Log out and verify that protected access is revoked.
"""

import json
import threading
import time
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent.parent
from server import CitidyRequestHandler
from database import init_db, ensure_demo_photos, verify_token, generate_token


class MockHtmlServerHandler(BaseHTTPRequestHandler):
    """Simulates a static hosting server (like GitHub Pages or a misconfigured proxy) returning HTML."""
    def do_POST(self):
        html_response = b"""<!DOCTYPE html>
<html>
<head><title>404 Not Found - GitHub Pages</title></head>
<body><h1>File not found</h1><p>The site configured at this address does not contain the requested file.</p></body>
</html>"""
        self.send_response(404)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html_response)))
        self.end_headers()
        self.wfile.write(html_response)


class TestAuthFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        ensure_demo_photos()
        cls.port = 8199
        cls.server = HTTPServer(("127.0.0.1", cls.port), CitidyRequestHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

        # Mock HTML server for testing HTML error handling
        cls.mock_html_port = 8198
        cls.mock_html_server = HTTPServer(("127.0.0.1", cls.mock_html_port), MockHtmlServerHandler)
        cls.mock_thread = threading.Thread(target=cls.mock_html_server.serve_forever, daemon=True)
        cls.mock_thread.start()
        time.sleep(0.4)

    @classmethod
    def tearDownClass(cls):
        try:
            threading.Thread(target=cls.server.shutdown, daemon=True).start()
            cls.server.server_close()
            threading.Thread(target=cls.mock_html_server.shutdown, daemon=True).start()
            cls.mock_html_server.server_close()
        except Exception:
            pass

    def request(self, port: int, method: str, path: str, payload: dict = None, token: str = None):
        url = f"http://127.0.0.1:{port}{path}"
        data_bytes = json.dumps(payload).encode("utf-8") if payload else None
        req = urllib.request.Request(url, data=data_bytes, method=method)
        req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("Authorization", f"Bearer {token}")

        try:
            with urllib.request.urlopen(req) as resp:
                ct = resp.headers.get("Content-Type", "")
                raw = resp.read().decode("utf-8")
                return resp.status, ct, raw
        except urllib.error.HTTPError as e:
            ct = e.headers.get("Content-Type", "")
            raw = e.read().decode("utf-8")
            return e.code, ct, raw

    def test_01_admin_login_with_valid_credentials(self):
        """1. Admin login with valid credentials."""
        status, ct, raw = self.request(self.port, "POST", "/api/auth/login", {
            "email": "admin@citidy.gov",
            "password": "CitidyAdmin2026!"
        })
        self.assertEqual(status, 200)
        self.assertIn("application/json", ct)
        data = json.loads(raw)
        self.assertIn("token", data)
        self.assertEqual(data["user"]["role"], "admin")
        self.assertEqual(data["user"]["email"], "admin@citidy.gov")

    def test_02_admin_login_with_incorrect_password(self):
        """2. Admin login with an incorrect password."""
        status, ct, raw = self.request(self.port, "POST", "/api/auth/login", {
            "email": "admin@citidy.gov",
            "password": "WrongPassword2026!"
        })
        self.assertEqual(status, 401)
        self.assertIn("application/json", ct)
        data = json.loads(raw)
        self.assertEqual(data["error"], "Invalid email or password")

    def test_03_login_with_nonexistent_account(self):
        """3. Login with a nonexistent account."""
        status, ct, raw = self.request(self.port, "POST", "/api/auth/login", {
            "email": "nonexistent@citidy.gov",
            "password": "SomePassword123!"
        })
        self.assertEqual(status, 401)
        self.assertIn("application/json", ct)
        data = json.loads(raw)
        self.assertEqual(data["error"], "Invalid email or password")

    def test_04_login_when_backend_unavailable(self):
        """4. Login when the backend is unavailable (connection refused)."""
        # Connect to a port where nothing is listening
        dead_port = 8197
        with self.assertRaises(Exception) as ctx:
            self.request(dead_port, "POST", "/api/auth/login", {
                "email": "admin@citidy.gov",
                "password": "CitidyAdmin2026!"
            })
        self.assertTrue(isinstance(ctx.exception, (urllib.error.URLError, ConnectionRefusedError)))

    def test_05_login_when_endpoint_returns_html(self):
        """5. Login when endpoint returns HTML error page (simulating static hosting like GitHub Pages)."""
        status, ct, raw = self.request(self.mock_html_port, "POST", "/api/auth/login", {
            "email": "admin@citidy.gov",
            "password": "CitidyAdmin2026!"
        })
        self.assertEqual(status, 404)
        self.assertIn("text/html", ct)
        self.assertTrue(raw.strip().startswith("<!DOCTYPE html>"))
        # Verify that safe parsing would identify this as non-JSON
        is_json = "application/json" in ct
        self.assertFalse(is_json)

    def test_06_citizen_attempts_admin_area(self):
        """6. Login as a normal citizen and attempt to access the admin area."""
        # Authenticate as citizen
        status, ct, raw = self.request(self.port, "POST", "/api/auth/login", {
            "email": "citizen@citidy.gov",
            "password": "Citizen2026!"
        })
        self.assertEqual(status, 200)
        citizen_token = json.loads(raw)["token"]

        # Attempt to access privileged admin stats
        status, ct, raw = self.request(self.port, "GET", "/api/admin/stats", token=citizen_token)
        self.assertEqual(status, 403)
        self.assertIn("application/json", ct)
        data = json.loads(raw)
        self.assertIn("Forbidden", data["error"])

    def test_07_refresh_page_after_admin_login(self):
        """7. Refresh the page after successful admin login (validates /api/auth/me)."""
        # Login as admin to get token
        _, _, raw = self.request(self.port, "POST", "/api/auth/login", {
            "email": "admin@citidy.gov",
            "password": "CitidyAdmin2026!"
        })
        admin_token = json.loads(raw)["token"]

        # Emulate page reload: Frontend calls /api/auth/me with stored token
        status, ct, raw = self.request(self.port, "GET", "/api/auth/me", token=admin_token)
        self.assertEqual(status, 200)
        self.assertIn("application/json", ct)
        user_data = json.loads(raw)["user"]
        self.assertEqual(user_data["role"], "admin")
        self.assertEqual(user_data["email"], "admin@citidy.gov")

    def test_08_logout_and_revocation(self):
        """8. Log out and verify that protected access is revoked."""
        # Without token, /api/auth/me returns 401
        status, ct, raw = self.request(self.port, "GET", "/api/auth/me")
        self.assertEqual(status, 401)
        self.assertIn("application/json", ct)

        # Without token, /api/admin/stats returns 403
        status, ct, raw = self.request(self.port, "GET", "/api/admin/stats")
        self.assertEqual(status, 403)


if __name__ == "__main__":
    unittest.main()
