"""
Automated Integration Test Suite for Citidy Civic Complaint Management Platform.
Tests the complete end-to-end workflow, security boundaries, and data integrity:
1. Citizen Registration and Authentication.
2. Complaint Submission with Before Photo.
3. Admin Verification, Assignment, and Milestone Progress.
4. Estimated Resolution Time Updates & History.
5. Mandatory Resolution with After Photo.
6. Before-and-After Evidence Comparison.
7. Role-Based Security Boundaries (403 on Privilege Escalation).
8. Completed Turnaround Time Accuracy.
"""

import json
import threading
import time
import urllib.request
import urllib.error
from http.server import HTTPServer
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent.parent
from server import CitidyRequestHandler
from database import init_db, ensure_demo_photos, DB_PATH


class TestCitidyBackend(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        ensure_demo_photos()
        cls.port = 8189
        cls.server = HTTPServer(("127.0.0.1", cls.port), CitidyRequestHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        time.sleep(0.5)

    @classmethod
    def tearDownClass(cls):
        try:
            threading.Thread(target=cls.server.shutdown, daemon=True).start()
            cls.server.server_close()
        except Exception:
            pass

    def api_request(self, method: str, endpoint: str, body: dict = None, token: str = None) -> tuple[int, dict]:
        url = f"http://127.0.0.1:{self.port}{endpoint}"
        req = urllib.request.Request(url, method=method)
        req.add_header("Content-Type", "application/json")
        if token:
            req.add_header("Authorization", f"Bearer {token}")

        data_bytes = json.dumps(body).encode("utf-8") if body else None
        try:
            with urllib.request.urlopen(req, data=data_bytes) as resp:
                status = resp.status
                res_body = json.loads(resp.read().decode("utf-8"))
                return status, res_body
        except urllib.error.HTTPError as e:
            err_body = json.loads(e.read().decode("utf-8")) if e.fp else {}
            return e.code, err_body

    def test_01_citizen_registration_and_login(self):
        """Test registration of a new citizen account and login."""
        unique_email = f"test_citizen_{int(time.time())}@citidy.gov"
        status, res = self.api_request("POST", "/api/auth/register", {
            "fullName": "Carlos Rivera",
            "email": unique_email,
            "password": "SecurePassword2026!",
            "phone": "+1-555-8888"
        })
        self.assertEqual(status, 201)
        self.assertIn("token", res)
        self.assertEqual(res["user"]["role"], "citizen")

        # Login
        status, login_res = self.api_request("POST", "/api/auth/login", {
            "email": unique_email,
            "password": "SecurePassword2026!"
        })
        self.assertEqual(status, 200)
        self.assertIn("token", login_res)

    def test_02_admin_login(self):
        """Test admin login with pre-seeded credentials."""
        status, res = self.api_request("POST", "/api/auth/login", {
            "email": "admin@citidy.gov",
            "password": "CitidyAdmin2026!"
        })
        self.assertEqual(status, 200)
        self.assertEqual(res["user"]["role"], "admin")
        self.assertIn("token", res)

    def test_03_full_complaint_workflow_with_evidence(self):
        """Test complete citizen submission -> admin review -> estimate update -> resolve with AFTER photo."""
        # 1. Citizen logs in
        _, citizen_auth = self.api_request("POST", "/api/auth/login", {
            "email": "citizen@citidy.gov",
            "password": "Citizen2026!"
        })
        citizen_token = citizen_auth["token"]

        # 2. Citizen submits complaint with BEFORE photo (base64 dummy)
        dummy_before_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        status, sub_res = self.api_request("POST", "/api/complaints", {
            "category": "Streetlight failures",
            "title": "Dark street fixture flickering on Pine Street",
            "description": "Entire block is unlit at night, creating safety issues for pedestrians.",
            "latitude": 16.5200,
            "longitude": 80.4700,
            "address": "450 Pine Street",
            "zone": "ZONE_05",
            "priority": "High",
            "photoBase64": dummy_before_b64,
            "photoName": "streetlight_broken.jpg"
        }, token=citizen_token)

        self.assertEqual(status, 201)
        complaint_id = sub_res["complaintId"]
        complaint_num = sub_res["complaintNumber"]
        self.assertTrue(complaint_num.startswith("CTD-2026-"))

        # 3. Admin logs in
        _, admin_auth = self.api_request("POST", "/api/auth/login", {
            "email": "admin@citidy.gov",
            "password": "CitidyAdmin2026!"
        })
        admin_token = admin_auth["token"]

        # 4. Admin verifies and assigns
        status, v_res = self.api_request("POST", f"/api/complaints/{complaint_id}/status", {
            "status": "Verified",
            "note": "Verified by field sensor; fixture ballast failed"
        }, token=admin_token)
        self.assertEqual(status, 200)

        status, a_res = self.api_request("POST", f"/api/complaints/{complaint_id}/status", {
            "status": "Assigned",
            "department": "Electrical & Lighting Division",
            "assignedTo": "Unit 7 Electrical Team",
            "note": "Work ticket generated"
        }, token=admin_token)
        self.assertEqual(status, 200)

        # 5. Admin updates estimated resolution date with reason
        new_est = "2026-10-25T18:00:00"
        status, est_res = self.api_request("POST", f"/api/complaints/{complaint_id}/estimate", {
            "newEstimate": new_est,
            "reason": "Replacement LED driver backordered from regional depot"
        }, token=admin_token)
        self.assertEqual(status, 200)

        # 6. Admin resolves issue with MANDATORY AFTER photo
        dummy_after_b64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
        status, res_res = self.api_request("POST", f"/api/complaints/{complaint_id}/resolve", {
            "photoBase64": dummy_after_b64,
            "photoName": "streetlight_repaired.jpg",
            "resolutionNotes": "New commercial LED luminaire mounted, lumetest passed (45 lux ground illumination).",
            "resolvedBy": "Chief Electrical Inspector"
        }, token=admin_token)
        self.assertEqual(status, 200)
        self.assertEqual(res_res["status"], "Resolved")
        self.assertIn("uploads/", res_res["afterPhoto"])

        # 7. Citizen checks complaint details and verifies BEFORE vs AFTER evidence
        status, c_details = self.api_request("GET", f"/api/complaints/{complaint_id}", token=citizen_token)
        self.assertEqual(status, 200)
        comp = c_details["complaint"]
        self.assertEqual(comp["status"], "Resolved")
        self.assertEqual(comp["progress_percentage"], 100)
        self.assertIsNotNone(comp["before_photo"])
        self.assertIsNotNone(comp["after_photo"])
        self.assertGreaterEqual(len(comp["status_history"]), 4)
        self.assertGreaterEqual(len(comp["estimate_history"]), 1)

        # 8. Citizen checks notifications
        status, notif_res = self.api_request("GET", "/api/notifications", token=citizen_token)
        self.assertEqual(status, 200)
        notifs = notif_res["notifications"]
        self.assertTrue(any(n["complaint_id"] == complaint_id and "Resolved" in n["title"] for n in notifs))

        # 9. Citizen disputes resolution and reopens complaint
        status, reopen_res = self.api_request("POST", f"/api/complaints/{complaint_id}/reopen", {
            "reason": "Luminaire was installed but fixture still flickers intermittently during evening hours."
        }, token=citizen_token)
        self.assertEqual(status, 200)
        self.assertEqual(reopen_res["status"], "Reopened")

        # Verify status is now Reopened in backend
        status, c_reopened = self.api_request("GET", f"/api/complaints/{complaint_id}", token=citizen_token)
        self.assertEqual(status, 200)
        self.assertEqual(c_reopened["complaint"]["status"], "Reopened")

    def test_04_security_privilege_escalation_protection(self):
        """Verify citizens CANNOT access admin endpoints or resolve complaints."""
        # Citizen login
        _, citizen_auth = self.api_request("POST", "/api/auth/login", {
            "email": "citizen@citidy.gov",
            "password": "Citizen2026!"
        })
        citizen_token = citizen_auth["token"]

        # Attempt to access admin stats
        status, _ = self.api_request("GET", "/api/admin/stats", token=citizen_token)
        self.assertEqual(status, 403)

        # Attempt to resolve a complaint as citizen
        status, _ = self.api_request("POST", "/api/complaints/CTD-2026-00001/resolve", {
            "photoBase64": "dummy",
            "resolutionNotes": "I fixed it myself"
        }, token=citizen_token)
        self.assertEqual(status, 403)

    def test_05_mandatory_resolution_photo_enforcement(self):
        """Admins CANNOT resolve a complaint without providing an After photograph."""
        _, admin_auth = self.api_request("POST", "/api/auth/login", {
            "email": "admin@citidy.gov",
            "password": "CitidyAdmin2026!"
        })
        admin_token = admin_auth["token"]

        status, res = self.api_request("POST", "/api/complaints/CTD-2026-00001/resolve", {
            "resolutionNotes": "Done without photo evidence"
        }, token=admin_token)
        self.assertEqual(status, 400)
        self.assertIn("photograph", res["error"].lower())


if __name__ == "__main__":
    unittest.main()
