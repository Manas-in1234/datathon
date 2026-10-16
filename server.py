#!/usr/bin/env python3
"""
Citidy — Unified Web & REST API Server
======================================
Product: Citidy Civic Complaint Management Platform
Tagline: "Your City. Your Voice. Tracked to Resolution."

Features:
- Pure Python 3 standard library (no external pip dependencies required).
- Serves the modern Citidy frontend and static assets.
- Provides secure REST API endpoints with server-side authentication and role-based authorization.
- Backed by persistent SQLite database (citidy.db) matching production Supabase schema.
- Automatic password hashing (PBKDF2-SHA256) and HMAC token verification.
- Complete Complaint Management: submission, visual milestones, before & after photo evidence,
  estimated resolution tracking with change history, overdue calculation, and in-app notifications.

Usage:
    python server.py [--port 8000]
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import re
import sys
import uuid
from datetime import datetime, timedelta
from http import HTTPStatus
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from database import (
    DB_PATH,
    UPLOAD_DIR,
    get_db_connection,
    hash_password,
    verify_password,
    generate_token,
    verify_token,
    init_db,
    ensure_demo_photos,
)

ROOT = Path(__file__).resolve().parent


class CitidyRequestHandler(SimpleHTTPRequestHandler):
    """Handles static files and Citidy REST API requests."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def log_message(self, format, *args):
        # Clean terminal logging
        sys.stdout.write(f"[{datetime.now().strftime('%H:%M:%S')}] {self.address_string()} - {format % args}\n")

    def send_json(self, data: dict | list, status: int = 200) -> None:
        payload = json.dumps(data, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.end_headers()
        self.wfile.write(payload)

    def send_error_json(self, message: str, status: int = 400) -> None:
        self.send_json({"error": message, "status": status}, status=status)

    def get_auth_user(self) -> dict | None:
        auth_header = self.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None
        token = auth_header[7:].strip()
        auth_info = verify_token(token)
        if not auth_info:
            return None

        with get_db_connection() as conn:
            user = conn.execute("SELECT id, full_name, email, role, phone FROM profiles WHERE id = ?", (auth_info["user_id"],)).fetchone()
            if not user:
                return None
            return dict(user)

    def parse_body(self) -> dict:
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return {}
        body_bytes = self.rfile.read(content_length)
        try:
            return json.loads(body_bytes.decode("utf-8"))
        except Exception:
            return {}

    def record_audit_event(self, conn, admin_id: str, event_type: str, target_id: str, details: str) -> None:
        """Record an administrative action to the administrative_audit_events table."""
        try:
            client_ip = self.client_address[0] if hasattr(self, "client_address") else "127.0.0.1"
            conn.execute("""
            INSERT INTO administrative_audit_events (id, admin_id, event_type, target_id, details, ip_address, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (str(uuid.uuid4()), admin_id, event_type, target_id, details, client_ip, datetime.utcnow().isoformat()))
        except Exception as e:
            sys.stderr.write(f"Failed to record audit event: {e}\n")

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.end_headers()

    def do_PUT(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/"):
            self.handle_api_post(path)
        else:
            self.send_error_json("Method Not Allowed", 405)

    # -------------------------------------------------------------------------
    # GET REQUEST ROUTER
    # -------------------------------------------------------------------------
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        if path.startswith("/api/"):
            self.handle_api_get(path, query)
        else:
            # Fallback to standard static file serving
            super().do_GET()

    def handle_api_get(self, path: str, query: dict):
        # 1. Current Authenticated User Profile
        if path == "/api/auth/me":
            user = self.get_auth_user()
            if not user:
                return self.send_error_json("Unauthorized", 401)
            return self.send_json({"user": user})

        # 2. Get Complaints List
        if path == "/api/complaints":
            user = self.get_auth_user()
            if not user:
                return self.send_error_json("Unauthorized", 401)

            with get_db_connection() as conn:
                now = datetime.utcnow().isoformat()
                if user["role"] == "admin":
                    # Admins see all complaints with optional filtering
                    sql = "SELECT * FROM complaints WHERE 1=1"
                    params = []

                    search = query.get("search", [""])[0].strip().lower()
                    if search:
                        sql += " AND (LOWER(complaint_number) LIKE ? OR LOWER(title) LIKE ? OR LOWER(address) LIKE ? OR LOWER(description) LIKE ?)"
                        pat = f"%{search}%"
                        params.extend([pat, pat, pat, pat])

                    status = query.get("status", [""])[0].strip()
                    if status and status != "all":
                        sql += " AND status = ?"
                        params.append(status)

                    zone = query.get("zone", [""])[0].strip()
                    if zone and zone != "all":
                        sql += " AND zone = ?"
                        params.append(zone)

                    category = query.get("category", [""])[0].strip()
                    if category and category != "all":
                        sql += " AND category = ?"
                        params.append(category)

                    sql += " ORDER BY created_at DESC"
                    rows = conn.execute(sql, params).fetchall()
                else:
                    # Citizens only see their own submitted complaints
                    rows = conn.execute("SELECT * FROM complaints WHERE user_id = ? ORDER BY created_at DESC", (user["id"],)).fetchall()

                complaints = []
                for r in rows:
                    c = dict(r)
                    # Compute overdue status
                    c["is_overdue"] = bool(
                        c["estimated_resolution_at"]
                        and c["estimated_resolution_at"] < now
                        and c["status"] not in ("Resolved", "Closed", "Rejected")
                    )

                    # Attach before and after thumbnails
                    attachments = conn.execute(
                        "SELECT id, attachment_type, file_path, file_name, caption FROM complaint_attachments WHERE complaint_id = ?",
                        (c["id"],)
                    ).fetchall()
                    c["attachments"] = [dict(a) for a in attachments]
                    c["before_photo"] = next((a["file_path"] for a in c["attachments"] if a["attachment_type"] == "before"), None)
                    c["after_photo"] = next((a["file_path"] for a in c["attachments"] if a["attachment_type"] == "after"), None)
                    complaints.append(c)

                return self.send_json({"complaints": complaints})

        # 3. Single Complaint Details with Timeline, Estimates, and Evidence
        complaint_match = re.match(r"^/api/complaints/([^/]+)$", path)
        if complaint_match:
            cid = complaint_match.group(1)
            user = self.get_auth_user()
            if not user:
                return self.send_error_json("Unauthorized", 401)

            with get_db_connection() as conn:
                row = conn.execute("SELECT * FROM complaints WHERE id = ? OR complaint_number = ?", (cid, cid)).fetchone()
                if not row:
                    return self.send_error_json("Complaint not found", 404)

                c = dict(row)
                if user["role"] != "admin" and c["user_id"] != user["id"]:
                    return self.send_error_json("Forbidden: you cannot view another citizen's complaint", 403)

                now = datetime.utcnow().isoformat()
                c["is_overdue"] = bool(
                    c["estimated_resolution_at"]
                    and c["estimated_resolution_at"] < now
                    and c["status"] not in ("Resolved", "Closed", "Rejected")
                )

                # Attachments
                attachments = conn.execute("SELECT * FROM complaint_attachments WHERE complaint_id = ? ORDER BY created_at ASC", (c["id"],)).fetchall()
                c["attachments"] = [dict(a) for a in attachments]
                c["before_photo"] = next((a["file_path"] for a in c["attachments"] if a["attachment_type"] == "before"), None)
                c["after_photo"] = next((a["file_path"] for a in c["attachments"] if a["attachment_type"] == "after"), None)

                # Timeline / Status History
                history = conn.execute("""
                SELECT h.*, p.full_name as changed_by_name, p.role as changed_by_role
                FROM complaint_status_history h
                LEFT JOIN profiles p ON h.changed_by = p.id
                WHERE h.complaint_id = ?
                ORDER BY h.created_at ASC
                """, (c["id"],)).fetchall()
                c["status_history"] = [dict(h) for h in history]

                # Estimate History
                estimates = conn.execute("""
                SELECT e.*, p.full_name as changed_by_name
                FROM resolution_estimate_history e
                LEFT JOIN profiles p ON e.changed_by = p.id
                WHERE e.complaint_id = ?
                ORDER BY e.created_at DESC
                """, (c["id"],)).fetchall()
                c["estimate_history"] = [dict(e) for e in estimates]

                # Assignments
                assignments = conn.execute("SELECT * FROM complaint_assignments WHERE complaint_id = ? ORDER BY assigned_at DESC", (c["id"],)).fetchall()
                c["assignments"] = [dict(a) for a in assignments]

                # Citizen profile info
                citizen = conn.execute("SELECT id, full_name, email, phone FROM profiles WHERE id = ?", (c["user_id"],)).fetchone()
                c["citizen"] = dict(citizen) if citizen else {}

                return self.send_json({"complaint": c})

        # 4. User Notifications
        if path == "/api/notifications":
            user = self.get_auth_user()
            if not user:
                return self.send_error_json("Unauthorized", 401)

            with get_db_connection() as conn:
                notifs = conn.execute(
                    "SELECT * FROM notifications WHERE recipient_user_id = ? ORDER BY created_at DESC LIMIT 50",
                    (user["id"],)
                ).fetchall()
                unread_count = conn.execute(
                    "SELECT COUNT(*) as count FROM notifications WHERE recipient_user_id = ? AND is_read = 0",
                    (user["id"],)
                ).fetchone()["count"]

                return self.send_json({
                    "notifications": [dict(n) for n in notifs],
                    "unread_count": unread_count,
                })

        # 5. Public / Filtered Complaint Map Data
        if path == "/api/map/complaints":
            with get_db_connection() as conn:
                rows = conn.execute("""
                SELECT id, complaint_number, category, title, latitude, longitude,
                       address, zone, priority, status, progress_percentage, created_at, resolved_at
                FROM complaints
                ORDER BY created_at DESC
                """).fetchall()

                features = []
                for r in rows:
                    c = dict(r)
                    after = conn.execute(
                        "SELECT file_path FROM complaint_attachments WHERE complaint_id = ? AND attachment_type = 'after' LIMIT 1",
                        (c["id"],)
                    ).fetchone()
                    before = conn.execute(
                        "SELECT file_path FROM complaint_attachments WHERE complaint_id = ? AND attachment_type = 'before' LIMIT 1",
                        (c["id"],)
                    ).fetchone()
                    c["after_photo"] = after["file_path"] if after else None
                    c["before_photo"] = before["file_path"] if before else None
                    features.append(c)

                return self.send_json({"features": features})

        # 6. Admin Summary Statistics & Resolution Performance
        if path == "/api/admin/stats":
            user = self.get_auth_user()
            if not user or user["role"] != "admin":
                return self.send_error_json("Forbidden: Admin access required", 403)

            with get_db_connection() as conn:
                now = datetime.utcnow().isoformat()
                total = conn.execute("SELECT COUNT(*) as count FROM complaints").fetchone()["count"]
                submitted = conn.execute("SELECT COUNT(*) as count FROM complaints WHERE status = 'Submitted'").fetchone()["count"]
                in_progress = conn.execute("SELECT COUNT(*) as count FROM complaints WHERE status = 'In Progress'").fetchone()["count"]
                resolved = conn.execute("SELECT COUNT(*) as count FROM complaints WHERE status IN ('Resolved', 'Closed')").fetchone()["count"]
                overdue = conn.execute("""
                SELECT COUNT(*) as count FROM complaints
                WHERE estimated_resolution_at < ? AND status NOT IN ('Resolved', 'Closed', 'Rejected')
                """, (now,)).fetchone()["count"]

                # Calculate average resolution time STRICTLY on completed records (resolved_at populated)
                completed_rows = conn.execute("""
                SELECT created_at, resolved_at FROM complaints
                WHERE status IN ('Resolved', 'Closed') AND resolved_at IS NOT NULL
                """).fetchall()

                durations = []
                for cr in completed_rows:
                    try:
                        t_start = datetime.fromisoformat(cr["created_at"])
                        t_end = datetime.fromisoformat(cr["resolved_at"])
                        dur_hours = (t_end - t_start).total_seconds() / 3600.0
                        if dur_hours >= 0:
                            durations.append(dur_hours)
                    except Exception:
                        pass

                avg_res_hours = round(sum(durations) / len(durations), 1) if durations else None

                # Category breakdown
                cat_rows = conn.execute("SELECT category, COUNT(*) as count FROM complaints GROUP BY category ORDER BY count DESC").fetchall()
                categories = {r["category"]: r["count"] for r in cat_rows}

                # Zone breakdown
                zone_rows = conn.execute("SELECT zone, COUNT(*) as count FROM complaints GROUP BY zone ORDER BY count DESC").fetchall()
                zones = {r["zone"]: r["count"] for r in zone_rows}

                return self.send_json({
                    "total": total,
                    "submitted": submitted,
                    "in_progress": in_progress,
                    "resolved": resolved,
                    "overdue": overdue,
                    "avg_resolution_hours": avg_res_hours,
                    "completed_samples": len(durations),
                    "categories": categories,
                    "zones": zones,
                })

        # 7. Administrative Audit Logs (Admin-Only)
        if path == "/api/admin/audit-logs":
            user = self.get_auth_user()
            if not user or user["role"] != "admin":
                return self.send_error_json("Forbidden: Administrator privileges required", 403)

            with get_db_connection() as conn:
                rows = conn.execute("""
                SELECT a.*, p.full_name as admin_name, p.email as admin_email
                FROM administrative_audit_events a
                LEFT JOIN profiles p ON a.admin_id = p.id
                ORDER BY a.created_at DESC LIMIT 100
                """).fetchall()
                return self.send_json({"audit_logs": [dict(r) for r in rows]})

        # 8. Citizen Feedback for a Complaint
        feedback_get_match = re.match(r"^/api/complaints/([^/]+)/feedback$", path)
        if feedback_get_match:
            cid = feedback_get_match.group(1)
            user = self.get_auth_user()
            if not user:
                return self.send_error_json("Unauthorized", 401)

            with get_db_connection() as conn:
                complaint = conn.execute("SELECT id, user_id FROM complaints WHERE id = ? OR complaint_number = ?", (cid, cid)).fetchone()
                if not complaint:
                    return self.send_error_json("Complaint not found", 404)
                if user["role"] != "admin" and complaint["user_id"] != user["id"]:
                    return self.send_error_json("Forbidden", 403)

                rows = conn.execute("""
                SELECT f.*, p.full_name as citizen_name
                FROM citizen_feedback f
                LEFT JOIN profiles p ON f.citizen_id = p.id
                WHERE f.complaint_id = ?
                ORDER BY f.created_at DESC
                """, (complaint["id"],)).fetchall()
                return self.send_json({"feedback": [dict(r) for r in rows]})

        # 9. Nearby Complaints / Geographic Clustering
        nearby_match = re.match(r"^/api/complaints/([^/]+)/nearby$", path)
        if nearby_match:
            cid = nearby_match.group(1)
            user = self.get_auth_user()
            if not user:
                return self.send_error_json("Unauthorized", 401)

            with get_db_connection() as conn:
                target = conn.execute("SELECT * FROM complaints WHERE id = ? OR complaint_number = ?", (cid, cid)).fetchone()
                if not target:
                    return self.send_error_json("Complaint not found", 404)

                t_lat = target["latitude"]
                t_lon = target["longitude"]
                t_zone = target["zone"]
                t_cat = target["category"]

                # Find complaints within ~500m (0.005 deg) or same category in the same zone
                rows = conn.execute("""
                SELECT id, complaint_number, title, category, zone, latitude, longitude, status, priority, created_at
                FROM complaints
                WHERE id != ? AND (
                    (latitude BETWEEN ? AND ? AND longitude BETWEEN ? AND ?)
                    OR (zone = ? AND category = ?)
                )
                ORDER BY created_at DESC
                LIMIT 10
                """, (target["id"], t_lat - 0.006, t_lat + 0.006, t_lon - 0.006, t_lon + 0.006, t_zone, t_cat)).fetchall()
                return self.send_json({"target_id": target["id"], "nearby_complaints": [dict(r) for r in rows]})

        return self.send_error_json("API endpoint not found", 404)

    # -------------------------------------------------------------------------
    # POST REQUEST ROUTER
    # -------------------------------------------------------------------------
    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/"):
            self.handle_api_post(path)
        else:
            self.send_error_json("Method Not Allowed", 405)

    def handle_api_post(self, path: str):
        body = self.parse_body()

        # 1. Citizen Registration
        if path == "/api/auth/register":
            full_name = body.get("fullName", "").strip()
            email = body.get("email", "").strip().lower()
            password = body.get("password", "")
            phone = body.get("phone", "").strip()

            if not full_name or not email or not password:
                return self.send_error_json("Full name, email, and password are required")
            if len(password) < 8:
                return self.send_error_json("Password must be at least 8 characters long")
            if "@" not in email:
                return self.send_error_json("Invalid email address")

            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id FROM profiles WHERE email = ?", (email,))
                if cursor.fetchone():
                    return self.send_error_json("An account with this email already exists", 409)

                user_id = str(uuid.uuid4())
                cursor.execute("""
                INSERT INTO profiles (id, full_name, email, password_hash, role, phone)
                VALUES (?, ?, ?, ?, 'citizen', ?)
                """, (user_id, full_name, email, hash_password(password), phone))

                cursor.execute("INSERT INTO notification_preferences (user_id) VALUES (?)", (user_id,))
                conn.commit()

            token = generate_token(user_id, "citizen")
            return self.send_json({
                "message": "Account registered successfully",
                "token": token,
                "user": {"id": user_id, "fullName": full_name, "email": email, "role": "citizen", "phone": phone}
            }, 201)

        # 2. Authentication Login (Citizen or Admin)
        if path == "/api/auth/login":
            email = body.get("email", "").strip().lower()
            password = body.get("password", "")

            if not email or not password:
                return self.send_error_json("Email and password are required")

            with get_db_connection() as conn:
                user = conn.execute("SELECT * FROM profiles WHERE email = ?", (email,)).fetchone()
                if not user or not verify_password(user["password_hash"], password):
                    return self.send_error_json("Invalid email or password", 401)

                token = generate_token(user["id"], user["role"])
                return self.send_json({
                    "message": "Login successful",
                    "token": token,
                    "user": {
                        "id": user["id"],
                        "fullName": user["full_name"],
                        "email": user["email"],
                        "role": user["role"],
                        "phone": user["phone"]
                    }
                })

        # 3. Submit a New Complaint (Citizen)
        if path == "/api/complaints":
            user = self.get_auth_user()
            if not user:
                return self.send_error_json("Unauthorized: Log in to report a problem", 401)

            category = body.get("category", "").strip()
            title = body.get("title", "").strip()
            description = body.get("description", "").strip()
            address = body.get("address", "").strip()
            zone = body.get("zone", "ZONE_01").strip()
            priority = body.get("priority", "Medium").strip()
            photo_b64 = body.get("photoBase64", "")
            photo_name = body.get("photoName", "complaint_photo.jpg")

            try:
                lat = float(body.get("latitude", 0.0))
                lon = float(body.get("longitude", 0.0))
            except (ValueError, TypeError):
                return self.send_error_json("Valid GPS latitude and longitude are required")

            if not category or not title or not description:
                return self.send_error_json("Category, title, and description are required")

            # Calculate estimated resolution time target based on priority
            now = datetime.utcnow()
            priority_hours = {"Critical": 24, "High": 72, "Medium": 120, "Low": 240}
            target_hours = priority_hours.get(priority, 120)
            est_resolution_at = (now + timedelta(hours=target_hours)).isoformat()

            cid = str(uuid.uuid4())
            complaint_num = f"CTD-2026-{int(datetime.utcnow().timestamp()) % 100000:05d}"

            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                INSERT INTO complaints (
                    id, complaint_number, user_id, category, title, description,
                    latitude, longitude, address, zone, priority, status,
                    progress_percentage, estimated_resolution_at, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Submitted', 0, ?, ?, ?)
                """, (
                    cid, complaint_num, user["id"], category, title, description,
                    lat, lon, address, zone, priority, est_resolution_at, now.isoformat(), now.isoformat()
                ))

                # Handle image upload if provided
                if photo_b64:
                    photo_rel_path = self.save_base64_image(photo_b64, f"{cid}_before")
                    if photo_rel_path:
                        cursor.execute("""
                        INSERT INTO complaint_attachments (id, complaint_id, uploaded_by, attachment_type, file_path, file_name, caption)
                        VALUES (?, ?, ?, 'before', ?, ?, 'Original citizen problem photo')
                        """, (str(uuid.uuid4()), cid, user["id"], photo_rel_path, photo_name))

                # Status History
                cursor.execute("""
                INSERT INTO complaint_status_history (id, complaint_id, old_status, new_status, progress_percentage, note, changed_by, created_at)
                VALUES (?, ?, NULL, 'Submitted', 0, 'Complaint successfully submitted by citizen', ?, ?)
                """, (str(uuid.uuid4()), cid, user["id"], now.isoformat()))

                # Initial Notification to Citizen
                cursor.execute("""
                INSERT INTO notifications (id, recipient_user_id, complaint_id, title, message, notification_type, is_read, created_at)
                VALUES (?, ?, ?, ?, ?, 'submission', 0, ?)
                """, (
                    str(uuid.uuid4()), user["id"], cid,
                    f"Complaint Submitted: {complaint_num}",
                    f"Your complaint regarding '{title}' in {zone} was recorded. Estimated target: {target_hours // 24} days.",
                    now.isoformat()
                ))

                conn.commit()

            return self.send_json({
                "message": "Complaint submitted successfully",
                "complaintId": cid,
                "complaintNumber": complaint_num,
                "status": "Submitted",
                "estimatedResolutionAt": est_resolution_at,
            }, 201)

        # 4. Update Complaint Status & Progress (Admin-Only)
        status_match = re.match(r"^/api/complaints/([^/]+)/status$", path)
        if status_match:
            cid = status_match.group(1)
            user = self.get_auth_user()
            if not user or user["role"] != "admin":
                return self.send_error_json("Forbidden: Administrator privileges required", 403)

            new_status = body.get("status", "").strip()
            progress = body.get("progressPercentage", None)
            note = body.get("note", "").strip()
            department = body.get("department", "").strip()
            assigned_to = body.get("assignedTo", "").strip()

            valid_statuses = [
                "Submitted", "Under Review", "Verified", "Assigned",
                "In Progress", "On Hold", "Resolved", "Closed", "Reopened", "Rejected"
            ]
            if new_status not in valid_statuses:
                return self.send_error_json(f"Invalid status. Must be one of: {', '.join(valid_statuses)}")

            with get_db_connection() as conn:
                complaint = conn.execute("SELECT * FROM complaints WHERE id = ? OR complaint_number = ?", (cid, cid)).fetchone()
                if not complaint:
                    return self.send_error_json("Complaint not found", 404)

                old_status = complaint["status"]
                now = datetime.utcnow().isoformat()

                # Calculate progress % based on milestone rules if not explicitly supplied
                if progress is None:
                    milestones = {
                        "Submitted": 0, "Under Review": 10, "Verified": 20,
                        "Assigned": 30, "In Progress": 60, "On Hold": complaint["progress_percentage"],
                        "Resolved": 100, "Closed": 100, "Reopened": 40, "Rejected": 0
                    }
                    progress = milestones.get(new_status, complaint["progress_percentage"])

                conn.execute("""
                UPDATE complaints
                SET status = ?, progress_percentage = ?, updated_at = ?
                WHERE id = ?
                """, (new_status, progress, now, complaint["id"]))

                # Record status history audit trail
                conn.execute("""
                INSERT INTO complaint_status_history (id, complaint_id, old_status, new_status, progress_percentage, note, changed_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (str(uuid.uuid4()), complaint["id"], old_status, new_status, progress, note or f"Status updated to {new_status}", user["id"], now))

                # Handle department assignment
                if department or assigned_to:
                    conn.execute("""
                    INSERT INTO complaint_assignments (id, complaint_id, department, assigned_to, assigned_by, assigned_at, status)
                    VALUES (?, ?, ?, ?, ?, ?, 'Active')
                    """, (str(uuid.uuid4()), complaint["id"], department or "Public Works", assigned_to, user["id"], now))

                # Create Citizen Notification
                conn.execute("""
                INSERT INTO notifications (id, recipient_user_id, complaint_id, title, message, notification_type, is_read, created_at)
                VALUES (?, ?, ?, ?, ?, 'status_update', 0, ?)
                """, (
                    str(uuid.uuid4()), complaint["user_id"], complaint["id"],
                    f"Update: {complaint['complaint_number']} is now {new_status}",
                    f"Status changed from {old_status} to {new_status} ({progress}% complete). {note}",
                    now
                ))

                # Record Administrative Audit Event
                self.record_audit_event(conn, user["id"], "STATUS_CHANGE", complaint["id"], f"Status changed from {old_status} to {new_status} ({progress}%). Dept: {department or 'N/A'}")

                conn.commit()

            return self.send_json({"message": f"Status updated to {new_status}", "status": new_status, "progressPercentage": progress})

        # 5. Resolve Complaint with MANDATORY Resolution Evidence Photo (Admin-Only)
        resolve_match = re.match(r"^/api/complaints/([^/]+)/resolve$", path)
        if resolve_match:
            cid = resolve_match.group(1)
            user = self.get_auth_user()
            if not user or user["role"] != "admin":
                return self.send_error_json("Forbidden: Administrator privileges required", 403)

            photo_b64 = body.get("photoBase64", "").strip()
            photo_name = body.get("photoName", "resolution_evidence.jpg")
            resolution_notes = body.get("resolutionNotes", "").strip()
            resolved_by = body.get("resolvedBy", user["full_name"]).strip()

            if not photo_b64:
                return self.send_error_json("Mandatory requirement: A final resolution photograph of the completed fix must be provided.")
            if not resolution_notes:
                return self.send_error_json("Mandatory requirement: Resolution description and notes must be provided.")

            with get_db_connection() as conn:
                complaint = conn.execute("SELECT * FROM complaints WHERE id = ? OR complaint_number = ?", (cid, cid)).fetchone()
                if not complaint:
                    return self.send_error_json("Complaint not found", 404)

                photo_rel_path = self.save_base64_image(photo_b64, f"{complaint['id']}_after")
                if not photo_rel_path:
                    return self.send_error_json("Failed to process resolution photograph upload")

                now = datetime.utcnow().isoformat()

                # Save AFTER attachment record
                conn.execute("""
                INSERT INTO complaint_attachments (id, complaint_id, uploaded_by, attachment_type, file_path, file_name, caption, created_at)
                VALUES (?, ?, ?, 'after', ?, ?, 'Final verified resolution evidence photo', ?)
                """, (str(uuid.uuid4()), complaint["id"], user["id"], photo_rel_path, photo_name, now))

                # Update complaint
                conn.execute("""
                UPDATE complaints
                SET status = 'Resolved', progress_percentage = 100, resolved_at = ?, resolved_by = ?, resolution_notes = ?, updated_at = ?
                WHERE id = ?
                """, (now, resolved_by, resolution_notes, now, complaint["id"]))

                # Status History
                conn.execute("""
                INSERT INTO complaint_status_history (id, complaint_id, old_status, new_status, progress_percentage, note, changed_by, created_at)
                VALUES (?, ?, ?, 'Resolved', 100, ?, ?, ?)
                """, (str(uuid.uuid4()), complaint["id"], complaint["status"], resolution_notes, user["id"], now))

                # Citizen Notification
                conn.execute("""
                INSERT INTO notifications (id, recipient_user_id, complaint_id, title, message, notification_type, is_read, created_at)
                VALUES (?, ?, ?, ?, ?, 'resolved', 0, ?)
                """, (
                    str(uuid.uuid4()), complaint["user_id"], complaint["id"],
                    f"Issue Resolved: {complaint['complaint_number']}",
                    f"Your reported complaint '{complaint['title']}' has been marked Resolved. Resolution photograph and notes are now visible in your dashboard.",
                    now
                ))

                # Administrative Audit Event
                self.record_audit_event(conn, user["id"], "COMPLAINT_RESOLVED", complaint["id"], f"Resolved with notes: {resolution_notes[:100]}")

                conn.commit()

            return self.send_json({
                "message": "Complaint successfully resolved with verified photograph evidence",
                "status": "Resolved",
                "resolvedAt": now,
                "afterPhoto": photo_rel_path
            })

        # 6. Update Estimated Resolution Date (Admin-Only with Change History)
        estimate_match = re.match(r"^/api/complaints/([^/]+)/estimate$", path)
        if estimate_match:
            cid = estimate_match.group(1)
            user = self.get_auth_user()
            if not user or user["role"] != "admin":
                return self.send_error_json("Forbidden: Administrator privileges required", 403)

            new_estimate = body.get("newEstimate", "").strip()
            reason = body.get("reason", "").strip()

            if not new_estimate or not reason:
                return self.send_error_json("New estimated resolution date and a documented reason are required.")

            with get_db_connection() as conn:
                complaint = conn.execute("SELECT * FROM complaints WHERE id = ? OR complaint_number = ?", (cid, cid)).fetchone()
                if not complaint:
                    return self.send_error_json("Complaint not found", 404)

                prev_estimate = complaint["estimated_resolution_at"]
                now = datetime.utcnow().isoformat()

                # Record in estimate history table
                conn.execute("""
                INSERT INTO resolution_estimate_history (id, complaint_id, previous_estimate, new_estimate, reason, changed_by, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (str(uuid.uuid4()), complaint["id"], prev_estimate, new_estimate, reason, user["id"], now))

                # Update complaint
                conn.execute("UPDATE complaints SET estimated_resolution_at = ?, updated_at = ? WHERE id = ?", (new_estimate, now, complaint["id"]))

                # Citizen notification
                conn.execute("""
                INSERT INTO notifications (id, recipient_user_id, complaint_id, title, message, notification_type, is_read, created_at)
                VALUES (?, ?, ?, ?, ?, 'estimate_change', 0, ?)
                """, (
                    str(uuid.uuid4()), complaint["user_id"], complaint["id"],
                    f"Estimated Resolution Updated: {complaint['complaint_number']}",
                    f"New target date: {new_estimate}. Reason: {reason}",
                    now
                ))

                # Administrative Audit Event
                self.record_audit_event(conn, user["id"], "ESTIMATE_UPDATED", complaint["id"], f"New target: {new_estimate}. Reason: {reason}")

                conn.commit()

            return self.send_json({"message": "Estimated resolution date updated", "newEstimate": new_estimate})

        # 7. Reopen a Resolved Complaint (Citizen or Admin)
        reopen_match = re.match(r"^/api/complaints/([^/]+)/reopen$", path)
        if reopen_match:
            cid = reopen_match.group(1)
            user = self.get_auth_user()
            if not user:
                return self.send_error_json("Unauthorized", 401)

            reason = body.get("reason", "").strip()
            if not reason:
                return self.send_error_json("Please provide a reason why this resolution is being disputed.")

            with get_db_connection() as conn:
                complaint = conn.execute("SELECT * FROM complaints WHERE id = ? OR complaint_number = ?", (cid, cid)).fetchone()
                if not complaint:
                    return self.send_error_json("Complaint not found", 404)

                if user["role"] != "admin" and complaint["user_id"] != user["id"]:
                    return self.send_error_json("Forbidden", 403)

                now = datetime.utcnow().isoformat()
                conn.execute("UPDATE complaints SET status = 'Reopened', progress_percentage = 40, updated_at = ? WHERE id = ?", (now, complaint["id"]))

                conn.execute("""
                INSERT INTO complaint_status_history (id, complaint_id, old_status, new_status, progress_percentage, note, changed_by, created_at)
                VALUES (?, ?, ?, 'Reopened', 40, ?, ?, ?)
                """, (str(uuid.uuid4()), complaint["id"], complaint["status"], f"Reopened by {user['full_name']}: {reason}", user["id"], now))

                if user["role"] == "admin":
                    self.record_audit_event(conn, user["id"], "COMPLAINT_REOPENED", complaint["id"], f"Reopened by admin: {reason}")

                conn.commit()

            return self.send_json({"message": "Complaint reopened for review", "status": "Reopened"})

        # 8. Mark Notification as Read
        notif_read_match = re.match(r"^/api/notifications/([^/]+)/read$", path)
        if notif_read_match:
            nid = notif_read_match.group(1)
            user = self.get_auth_user()
            if not user:
                return self.send_error_json("Unauthorized", 401)

            with get_db_connection() as conn:
                if nid == "all":
                    conn.execute("UPDATE notifications SET is_read = 1 WHERE recipient_user_id = ?", (user["id"],))
                else:
                    conn.execute("UPDATE notifications SET is_read = 1 WHERE id = ? AND recipient_user_id = ?", (nid, user["id"]))
                conn.commit()
            return self.send_json({"message": "Notification marked as read"})

        # 9. Update Profile Information (Citizen or Admin)
        if path == "/api/auth/profile":
            user = self.get_auth_user()
            if not user:
                return self.send_error_json("Unauthorized", 401)

            full_name = body.get("fullName", "").strip()
            phone = body.get("phone", "").strip()

            if not full_name:
                return self.send_error_json("Full name cannot be empty")

            with get_db_connection() as conn:
                conn.execute("UPDATE profiles SET full_name = ?, phone = ? WHERE id = ?", (full_name, phone, user["id"]))
                conn.commit()
                updated_user = conn.execute("SELECT id, full_name, email, role, phone FROM profiles WHERE id = ?", (user["id"],)).fetchone()

            return self.send_json({
                "message": "Profile updated successfully",
                "user": dict(updated_user)
            })

        # 10. Submit Citizen Feedback on Resolution
        feedback_post_match = re.match(r"^/api/complaints/([^/]+)/feedback$", path)
        if feedback_post_match:
            cid = feedback_post_match.group(1)
            user = self.get_auth_user()
            if not user:
                return self.send_error_json("Unauthorized", 401)

            rating = body.get("rating")
            try:
                rating = int(rating)
                if not (1 <= rating <= 5):
                    raise ValueError()
            except (ValueError, TypeError):
                return self.send_error_json("Valid star rating between 1 and 5 is required")

            is_resolved = 1 if body.get("isProblemResolved", True) else 0
            comment = body.get("feedbackComment", "").strip()

            with get_db_connection() as conn:
                complaint = conn.execute("SELECT * FROM complaints WHERE id = ? OR complaint_number = ?", (cid, cid)).fetchone()
                if not complaint:
                    return self.send_error_json("Complaint not found", 404)

                if user["role"] != "admin" and complaint["user_id"] != user["id"]:
                    return self.send_error_json("Forbidden: only the reporting citizen can submit resolution feedback", 403)

                if complaint["status"] not in ("Resolved", "Closed"):
                    return self.send_error_json("Feedback can only be submitted after resolution", 400)

                fid = str(uuid.uuid4())
                now = datetime.utcnow().isoformat()
                conn.execute("""
                INSERT INTO citizen_feedback (id, complaint_id, citizen_id, rating, is_problem_resolved, feedback_comment, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (fid, complaint["id"], user["id"], rating, is_resolved, comment, now))
                conn.commit()

            return self.send_json({"message": "Thank you! Your feedback has been recorded.", "feedbackId": fid}, 201)

        # 11. Upload Attachment (Work-in-progress, before, or additional photos)
        attachment_post_match = re.match(r"^/api/complaints/([^/]+)/attachment$", path)
        if attachment_post_match:
            cid = attachment_post_match.group(1)
            user = self.get_auth_user()
            if not user:
                return self.send_error_json("Unauthorized", 401)

            photo_b64 = body.get("photoBase64", "").strip()
            photo_name = body.get("photoName", "attachment.jpg").strip()
            caption = body.get("caption", "").strip()
            att_type = body.get("attachmentType", "progress").strip()

            valid_types = ["before", "after", "progress", "other"]
            if att_type not in valid_types:
                att_type = "progress"

            if not photo_b64:
                return self.send_error_json("Photo data is required")

            with get_db_connection() as conn:
                complaint = conn.execute("SELECT * FROM complaints WHERE id = ? OR complaint_number = ?", (cid, cid)).fetchone()
                if not complaint:
                    return self.send_error_json("Complaint not found", 404)

                # Authorization: Citizens can only attach to their own complaints
                if user["role"] != "admin" and complaint["user_id"] != user["id"]:
                    return self.send_error_json("Forbidden", 403)

                # Citizens cannot post 'after' resolution photos directly (admin verified only)
                if user["role"] != "admin" and att_type == "after":
                    return self.send_error_json("Forbidden: resolution evidence must be submitted by municipal administrators", 403)

                rel_path = self.save_base64_image(photo_b64, f"{complaint['id']}_{att_type}")
                if not rel_path:
                    return self.send_error_json("Failed to process image upload")

                att_id = str(uuid.uuid4())
                now = datetime.utcnow().isoformat()
                conn.execute("""
                INSERT INTO complaint_attachments (id, complaint_id, uploaded_by, attachment_type, file_path, file_name, caption, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (att_id, complaint["id"], user["id"], att_type, rel_path, photo_name, caption, now))

                if user["role"] == "admin":
                    self.record_audit_event(conn, user["id"], "ATTACHMENT_UPLOADED", complaint["id"], f"Uploaded {att_type} photo: {photo_name}")

                conn.commit()

            return self.send_json({
                "message": "Attachment uploaded successfully",
                "attachmentId": att_id,
                "filePath": rel_path
            }, 201)

        return self.send_error_json("API endpoint not found", 404)

    def save_base64_image(self, b64_string: str, prefix: str) -> str | None:
        try:
            if "," in b64_string:
                header, data_str = b64_string.split(",", 1)
            else:
                data_str = b64_string

            img_bytes = base64.b64decode(data_str)
            if len(img_bytes) > 15 * 1024 * 1024:
                return None  # Max 15MB

            filename = f"{prefix}_{int(datetime.utcnow().timestamp())}.jpg"
            target_file = UPLOAD_DIR / filename
            target_file.write_bytes(img_bytes)
            return f"uploads/{filename}"
        except Exception as e:
            sys.stderr.write(f"Error saving image: {e}\n")
            return None


def run_server(port: int = 8000) -> None:
    init_db()
    ensure_demo_photos()
    server_address = ("", port)
    httpd = HTTPServer(server_address, CitidyRequestHandler)
    print("=" * 65)
    print("CITIDY — Civic Complaint Management Platform (Server Running)")
    print(f"URL:      http://localhost:{port}")
    print(f"Database: {DB_PATH.name} (SQLite / PostgreSQL Supabase Ready)")
    print("Pre-seeded Accounts:")
    print("  • Admin:   admin@citidy.gov   / CitidyAdmin2026!")
    print("  • Citizen: citizen@citidy.gov / Citizen2026!")
    print("=" * 65)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nCitidy server shutting down.")
        httpd.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Citidy Civic Complaint Platform Server")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind server (default 8000)")
    args = parser.parse_args()
    run_server(args.port)
