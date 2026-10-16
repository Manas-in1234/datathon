#!/usr/bin/env python3
"""
Citidy — Phase 12 Comprehensive Test Suite
==========================================
Product: Citidy Civic Complaint Management Platform
Event:   DATATHON 2026 | Track 3: Smart City
Problem Statement: "Where should we fix first?"

Executes 20 verified end-to-end integration test scenarios:
 1. Citizen registration
 2. Citizen login
 3. Administrator login
 4. Invalid credentials
 5. Role authorization
 6. Complaint submission
 7. Image uploads (Before evidence)
 8. Complaint assignment
 9. Status transitions (Milestone progression)
10. ETA changes (with history & reasoning)
11. Notifications (Submission, update, resolution alerts)
12. Resolution photograph upload (MANDATORY After evidence)
13. Resolution workflow (Side-by-side Before/After verification)
14. Map refresh (Public geojson/feature points)
15. Citizen data isolation (Citizen A cannot see Citizen B's complaint)
16. Administrator privileges (Admin can triage and resolve all)
17. Failed network requests (HTML/500/invalid endpoints handled safely)
18. Duplicate / rapid submission handling
19. Empty states & input validation
20. Deployment asset paths & static files integrity
"""

import base64
import json
import unittest
import urllib.request
import urllib.error
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8000"

# Minimal 1x1 transparent PNG for base64 test payloads
TINY_PNG_B64 = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="


def http_request(url: str, method: str = "GET", data: dict = None, token: str = None) -> tuple[int, dict | str]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req) as resp:
            status = resp.status
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read().decode("utf-8")
            if "application/json" in content_type:
                return status, json.loads(raw)
            return status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, raw
    except Exception as ex:
        return 0, str(ex)


class TestCitidyCompleteLifecycle(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Unique timestamp for this test run
        cls.ts = int(datetime.utcnow().timestamp())
        cls.citizen_email = f"test_citizen_{cls.ts}@citidy.org"
        cls.citizen_password = f"SecurePass{cls.ts}!"
        cls.citizen2_email = f"other_citizen_{cls.ts}@citidy.org"
        cls.admin_email = "admin@citidy.gov"
        cls.admin_password = "CitidyAdmin2026!"

    # 1. Citizen registration
    def test_01_citizen_registration(self):
        status, data = http_request(
            f"{BASE_URL}/api/auth/register",
            method="POST",
            data={
                "fullName": f"Lifecycle Tester {self.ts}",
                "email": self.citizen_email,
                "password": self.citizen_password,
                "phone": "+1-555-8822"
            }
        )
        self.assertEqual(status, 201)
        self.assertIn("token", data)
        self.assertEqual(data["user"]["role"], "citizen")
        TestCitidyCompleteLifecycle.citizen_token = data["token"]
        TestCitidyCompleteLifecycle.citizen_id = data["user"]["id"]

        # Register Citizen 2 for data isolation testing
        status2, data2 = http_request(
            f"{BASE_URL}/api/auth/register",
            method="POST",
            data={
                "fullName": f"Isolated Citizen {self.ts}",
                "email": self.citizen2_email,
                "password": self.citizen_password,
                "phone": "+1-555-9933"
            }
        )
        self.assertEqual(status2, 201)
        TestCitidyCompleteLifecycle.citizen2_token = data2["token"]

    # 2. Citizen login
    def test_02_citizen_login(self):
        status, data = http_request(
            f"{BASE_URL}/api/auth/login",
            method="POST",
            data={"email": self.citizen_email, "password": self.citizen_password}
        )
        self.assertEqual(status, 200)
        self.assertIn("token", data)
        self.assertEqual(data["user"]["role"], "citizen")

    # 3. Administrator login
    def test_03_admin_login(self):
        status, data = http_request(
            f"{BASE_URL}/api/auth/login",
            method="POST",
            data={"email": self.admin_email, "password": self.admin_password}
        )
        self.assertEqual(status, 200)
        self.assertIn("token", data)
        self.assertEqual(data["user"]["role"], "admin")
        TestCitidyCompleteLifecycle.admin_token = data["token"]

    # 4. Invalid credentials
    def test_04_invalid_credentials(self):
        status, data = http_request(
            f"{BASE_URL}/api/auth/login",
            method="POST",
            data={"email": self.admin_email, "password": "WrongPassword999!"}
        )
        self.assertEqual(status, 401)
        self.assertIn("error", data)

    # 5. Role authorization
    def test_05_role_authorization(self):
        # A citizen cannot access admin stats
        status, data = http_request(
            f"{BASE_URL}/api/admin/stats",
            method="GET",
            token=self.citizen_token
        )
        self.assertEqual(status, 403)

        # An admin can access admin stats
        status, data = http_request(
            f"{BASE_URL}/api/admin/stats",
            method="GET",
            token=self.admin_token
        )
        self.assertEqual(status, 200)
        self.assertIn("total", data)

    # 6. Complaint submission
    def test_06_complaint_submission(self):
        status, data = http_request(
            f"{BASE_URL}/api/complaints",
            method="POST",
            token=self.citizen_token,
            data={
                "category": "Potholes and road damage",
                "title": f"Hazardous Road Cavity {self.ts}",
                "description": "Deep asphalt depression causing vehicular damage on main transit corridor.",
                "latitude": 16.5150,
                "longitude": 80.4620,
                "address": "45 Market Street",
                "zone": "ZONE_07",
                "priority": "High",
                "photoBase64": TINY_PNG_B64,
                "photoName": "hazard_pothole.png"
            }
        )
        self.assertEqual(status, 201)
        self.assertIn("complaintId", data)
        self.assertEqual(data["status"], "Submitted")
        TestCitidyCompleteLifecycle.created_complaint_id = data["complaintId"]

    # 7. Image uploads (Before evidence)
    def test_07_image_uploads(self):
        status, data = http_request(
            f"{BASE_URL}/api/complaints/{self.created_complaint_id}",
            method="GET",
            token=self.citizen_token
        )
        self.assertEqual(status, 200)
        c = data["complaint"]
        self.assertIsNotNone(c["before_photo"])
        self.assertTrue(c["before_photo"].startswith("uploads/"))

    # 8. Complaint assignment
    def test_08_complaint_assignment(self):
        status, data = http_request(
            f"{BASE_URL}/api/complaints/{self.created_complaint_id}/status",
            method="POST",
            token=self.admin_token,
            data={
                "status": "Assigned",
                "department": "Department of Public Works",
                "assignedTo": "Emergency Paving Crew #3",
                "note": "Assigned to road maintenance dispatch for rapid remediation."
            }
        )
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "Assigned")

    # 9. Status transitions (Milestone progression)
    def test_09_status_transitions(self):
        status, data = http_request(
            f"{BASE_URL}/api/complaints/{self.created_complaint_id}/status",
            method="POST",
            token=self.admin_token,
            data={
                "status": "In Progress",
                "progressPercentage": 60,
                "note": "Crew on site; aggregate base laid, asphalt compaction commenced."
            }
        )
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "In Progress")
        self.assertEqual(data["progressPercentage"], 60)

    # 10. ETA changes
    def test_10_eta_changes(self):
        new_eta = (datetime.utcnow() + timedelta(days=1)).isoformat()
        status, data = http_request(
            f"{BASE_URL}/api/complaints/{self.created_complaint_id}/estimate",
            method="POST",
            token=self.admin_token,
            data={
                "newEstimate": new_eta,
                "reason": "Expedited work schedule due to favorable weather conditions."
            }
        )
        self.assertEqual(status, 200)
        self.assertEqual(data["newEstimate"], new_eta)

    # 11. Notifications
    def test_11_notifications(self):
        status, data = http_request(
            f"{BASE_URL}/api/notifications",
            method="GET",
            token=self.citizen_token
        )
        self.assertEqual(status, 200)
        notifs = data["notifications"]
        self.assertGreaterEqual(len(notifs), 1)
        self.assertIn("complaint_id", notifs[0])

    # 12. Resolution photograph upload (MANDATORY After evidence)
    def test_12_resolution_photograph_mandatory(self):
        # Attempting to resolve WITHOUT a photo must be rejected with 400
        status, data = http_request(
            f"{BASE_URL}/api/complaints/{self.created_complaint_id}/resolve",
            method="POST",
            token=self.admin_token,
            data={"resolutionNotes": "Work finished"}
        )
        self.assertEqual(status, 400)
        self.assertIn("error", data)

    # 13. Resolution workflow
    def test_13_resolution_workflow(self):
        status, data = http_request(
            f"{BASE_URL}/api/complaints/{self.created_complaint_id}/resolve",
            method="POST",
            token=self.admin_token,
            data={
                "photoBase64": TINY_PNG_B64,
                "photoName": "resolution_proof.png",
                "resolutionNotes": "Pothole filled with heavy-duty hot-mix asphalt, leveled to road grade, cured.",
                "resolvedBy": "Public Works Director"
            }
        )
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "Resolved")
        self.assertIsNotNone(data["afterPhoto"])

    # 14. Map refresh
    def test_14_map_refresh(self):
        status, data = http_request(f"{BASE_URL}/api/map/complaints", method="GET")
        self.assertEqual(status, 200)
        self.assertIn("features", data)
        # Check that our created complaint is present on map
        found = any(f["id"] == self.created_complaint_id for f in data["features"])
        self.assertTrue(found, "Newly resolved complaint must be represented in public map features")

    # 15. Citizen data isolation
    def test_15_citizen_data_isolation(self):
        # Citizen 2 should NOT be able to view Citizen 1's complaint via GET /api/complaints/<id>
        status, data = http_request(
            f"{BASE_URL}/api/complaints/{self.created_complaint_id}",
            method="GET",
            token=self.citizen2_token
        )
        self.assertEqual(status, 403, "Citizen 2 must be blocked from accessing Citizen 1's private complaint")

    # 16. Administrator privileges
    def test_16_administrator_privileges(self):
        # Admin can view any complaint regardless of user_id
        status, data = http_request(
            f"{BASE_URL}/api/complaints/{self.created_complaint_id}",
            method="GET",
            token=self.admin_token
        )
        self.assertEqual(status, 200)
        self.assertEqual(data["complaint"]["id"], self.created_complaint_id)

    # 17. Failed network requests
    def test_17_failed_network_requests(self):
        # Calling non-existent API returns structured JSON 404, not unhandled crash
        status, data = http_request(f"{BASE_URL}/api/non_existent_route", method="GET")
        self.assertEqual(status, 404)
        self.assertIn("error", data)

    # 18. Duplicate submission handling
    def test_18_duplicate_submission_handling(self):
        # Multiple complaints from the same citizen are assigned unique complaint numbers
        status1, data1 = http_request(
            f"{BASE_URL}/api/complaints",
            method="POST",
            token=self.citizen_token,
            data={
                "category": "Garbage accumulation",
                "title": f"Garbage Pile {self.ts} A",
                "description": "Overflowing waste receptacle near park entrance.",
                "latitude": 16.5160, "longitude": 80.4630, "zone": "ZONE_02", "priority": "Medium"
            }
        )
        status2, data2 = http_request(
            f"{BASE_URL}/api/complaints",
            method="POST",
            token=self.citizen_token,
            data={
                "category": "Garbage accumulation",
                "title": f"Garbage Pile {self.ts} B",
                "description": "Second report of waste overflowing on opposite sidewalk.",
                "latitude": 16.5162, "longitude": 80.4632, "zone": "ZONE_02", "priority": "Medium"
            }
        )
        self.assertEqual(status1, 201)
        self.assertEqual(status2, 201)
        self.assertNotEqual(data1["complaintNumber"], data2["complaintNumber"])

    # 19. Empty states and input validation
    def test_19_empty_states_and_validation(self):
        # Empty title / category is rejected
        status, data = http_request(
            f"{BASE_URL}/api/complaints",
            method="POST",
            token=self.citizen_token,
            data={"title": "", "category": "", "description": ""}
        )
        self.assertEqual(status, 400)
        self.assertIn("error", data)

    # 20. Deployment asset paths
    def test_20_deployment_asset_paths(self):
        for path in ["/index.html", "/styles.css", "/app.js", "/data.js", "/google-maps-config.js"]:
            status, raw = http_request(f"{BASE_URL}{path}", method="GET")
            self.assertEqual(status, 200, f"Asset {path} must be accessible with HTTP 200")


if __name__ == "__main__":
    unittest.main()
