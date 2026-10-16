"""
Citidy — Database Engine & Schema Management
=============================================
Product: Citidy Civic Complaint Management Platform
Tagline: "Your City. Your Voice. Tracked to Resolution."

Manages SQLite database schema, migrations, constraints, and initial seeds.
Compatible with standard Python 3 standard library (sqlite3).
Matches the production Supabase PostgreSQL schema specifications.
"""

from __future__ import annotations

import os
import sqlite3
import hashlib
import hmac
import uuid
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "citidy.db"
UPLOAD_DIR = ROOT / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# Secret key for HMAC token signing (in production this comes from environment)
SECRET_KEY = os.environ.get("CITIDY_SECRET_KEY", "citidy-secure-datathon-secret-key-2026")


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    hashed = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100000).hex()
    return f"{salt}:{hashed}"


def verify_password(stored_password_hash: str, provided_password: str) -> bool:
    try:
        salt, expected_hash = stored_password_hash.split(":")
        calc_hash = hashlib.pbkdf2_hmac("sha256", provided_password.encode("utf-8"), salt.encode("utf-8"), 100000).hex()
        return hmac.compare_digest(calc_hash, expected_hash)
    except Exception:
        return False


def generate_token(user_id: str, role: str) -> str:
    timestamp = str(int(datetime.utcnow().timestamp()))
    payload = f"{user_id}|{role}|{timestamp}"
    signature = hmac.new(SECRET_KEY.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}|{signature}"


def verify_token(token: str) -> dict | None:
    if not token or "|" not in token:
        return None
    try:
        parts = token.split("|")
        if len(parts) != 4:
            return None
        user_id, role, timestamp_str, signature = parts
        payload = f"{user_id}|{role}|{timestamp_str}"
        expected_sig = hmac.new(SECRET_KEY.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            return None
        token_time = datetime.utcfromtimestamp(int(timestamp_str))
        if datetime.utcnow() - token_time > timedelta(days=7):
            return None
        return {"user_id": user_id, "role": role}
    except Exception:
        return None


def init_db() -> None:
    """Initialize all Citidy database tables, indexes, and initial admin/citizen accounts."""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # 1. Profiles (Users)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS profiles (
            id TEXT PRIMARY KEY,
            full_name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'citizen' CHECK(role IN ('citizen', 'admin')),
            phone TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        # 2. Complaints
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS complaints (
            id TEXT PRIMARY KEY,
            complaint_number TEXT UNIQUE NOT NULL,
            user_id TEXT NOT NULL,
            category TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            address TEXT,
            zone TEXT DEFAULT 'ZONE_01',
            priority TEXT DEFAULT 'Medium' CHECK(priority IN ('Low', 'Medium', 'High', 'Critical')),
            status TEXT DEFAULT 'Submitted' CHECK(status IN (
                'Submitted', 'Under Review', 'Verified', 'Assigned',
                'In Progress', 'On Hold', 'Resolved', 'Closed', 'Reopened', 'Rejected'
            )),
            progress_percentage INTEGER DEFAULT 0,
            estimated_resolution_at TIMESTAMP,
            resolved_at TIMESTAMP,
            resolved_by TEXT,
            resolution_notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES profiles(id) ON DELETE CASCADE
        );
        """)

        # 3. Attachments (Photos)
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS complaint_attachments (
            id TEXT PRIMARY KEY,
            complaint_id TEXT NOT NULL,
            uploaded_by TEXT NOT NULL,
            attachment_type TEXT NOT NULL CHECK(attachment_type IN ('before', 'after', 'progress', 'other')),
            file_path TEXT NOT NULL,
            file_name TEXT,
            file_size INTEGER,
            mime_type TEXT,
            caption TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (complaint_id) REFERENCES complaints(id) ON DELETE CASCADE,
            FOREIGN KEY (uploaded_by) REFERENCES profiles(id) ON DELETE CASCADE
        );
        """)

        # 4. Status History
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS complaint_status_history (
            id TEXT PRIMARY KEY,
            complaint_id TEXT NOT NULL,
            old_status TEXT,
            new_status TEXT NOT NULL,
            progress_percentage INTEGER NOT NULL,
            note TEXT,
            changed_by TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (complaint_id) REFERENCES complaints(id) ON DELETE CASCADE,
            FOREIGN KEY (changed_by) REFERENCES profiles(id) ON DELETE CASCADE
        );
        """)

        # 5. Assignments
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS complaint_assignments (
            id TEXT PRIMARY KEY,
            complaint_id TEXT NOT NULL,
            department TEXT NOT NULL,
            assigned_to TEXT,
            assigned_by TEXT NOT NULL,
            assigned_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'Active',
            FOREIGN KEY (complaint_id) REFERENCES complaints(id) ON DELETE CASCADE,
            FOREIGN KEY (assigned_by) REFERENCES profiles(id) ON DELETE CASCADE
        );
        """)

        # 6. Notifications
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id TEXT PRIMARY KEY,
            recipient_user_id TEXT NOT NULL,
            complaint_id TEXT,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            notification_type TEXT NOT NULL,
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (recipient_user_id) REFERENCES profiles(id) ON DELETE CASCADE,
            FOREIGN KEY (complaint_id) REFERENCES complaints(id) ON DELETE CASCADE
        );
        """)

        # 7. Resolution Estimate History
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS resolution_estimate_history (
            id TEXT PRIMARY KEY,
            complaint_id TEXT NOT NULL,
            previous_estimate TIMESTAMP,
            new_estimate TIMESTAMP NOT NULL,
            reason TEXT NOT NULL,
            changed_by TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (complaint_id) REFERENCES complaints(id) ON DELETE CASCADE,
            FOREIGN KEY (changed_by) REFERENCES profiles(id) ON DELETE CASCADE
        );
        """)

        # 8. Notification Preferences
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS notification_preferences (
            user_id TEXT PRIMARY KEY,
            in_app_enabled INTEGER DEFAULT 1,
            email_enabled INTEGER DEFAULT 1,
            push_enabled INTEGER DEFAULT 0,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES profiles(id) ON DELETE CASCADE
        );
        """)

        # 9. Administrative Audit Events
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS administrative_audit_events (
            id TEXT PRIMARY KEY,
            admin_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            target_id TEXT,
            details TEXT,
            ip_address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (admin_id) REFERENCES profiles(id) ON DELETE CASCADE
        );
        """)

        # 10. Citizen Resolution Feedback
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS citizen_feedback (
            id TEXT PRIMARY KEY,
            complaint_id TEXT NOT NULL,
            citizen_id TEXT NOT NULL,
            rating INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
            is_problem_resolved INTEGER DEFAULT 1,
            feedback_comment TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (complaint_id) REFERENCES complaints(id) ON DELETE CASCADE,
            FOREIGN KEY (citizen_id) REFERENCES profiles(id) ON DELETE CASCADE
        );
        """)

        # Migration: Add internal_notes and cluster_id to complaints if missing
        complaint_cols = [row[1] for row in cursor.execute("PRAGMA table_info(complaints)").fetchall()]
        if "internal_notes" not in complaint_cols:
            cursor.execute("ALTER TABLE complaints ADD COLUMN internal_notes TEXT")
        if "cluster_id" not in complaint_cols:
            cursor.execute("ALTER TABLE complaints ADD COLUMN cluster_id TEXT")

        # Create Indexes for High Performance
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_complaints_user ON complaints(user_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_complaints_status ON complaints(status);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_complaints_zone ON complaints(zone);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_attachments_complaint ON complaint_attachments(complaint_id);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_notifications_recipient ON notifications(recipient_user_id, is_read);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_admin ON administrative_audit_events(admin_id, created_at);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_feedback_complaint ON citizen_feedback(complaint_id);")

        conn.commit()

        # Seed standard Admin and Citizen demo accounts if not existing
        cursor.execute("SELECT id FROM profiles WHERE email = 'admin@citidy.gov'")
        if not cursor.fetchone():
            admin_id = str(uuid.uuid4())
            cursor.execute("""
            INSERT INTO profiles (id, full_name, email, password_hash, role, phone)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (admin_id, "Citidy Operations Director", "admin@citidy.gov", hash_password("CitidyAdmin2026!"), "admin", "+1-555-0199"))

            # Notification preferences
            cursor.execute("INSERT OR REPLACE INTO notification_preferences (user_id) VALUES (?)", (admin_id,))

        cursor.execute("SELECT id FROM profiles WHERE email = 'citizen@citidy.gov'")
        if not cursor.fetchone():
            citizen_id = str(uuid.uuid4())
            cursor.execute("""
            INSERT INTO profiles (id, full_name, email, password_hash, role, phone)
            VALUES (?, ?, ?, ?, ?, ?)
            """, (citizen_id, "Maria Chen", "citizen@citidy.gov", hash_password("Citizen2026!"), "citizen", "+1-555-0142"))

            cursor.execute("INSERT OR REPLACE INTO notification_preferences (user_id) VALUES (?)", (citizen_id,))

            # Seed a demonstration complaint with Before & After photo references
            cid = str(uuid.uuid4())
            now = datetime.utcnow()
            est_date = (now + timedelta(days=2)).isoformat()
            resolved_date = now.isoformat()

            cursor.execute("""
            INSERT INTO complaints (
                id, complaint_number, user_id, category, title, description,
                latitude, longitude, address, zone, priority, status,
                progress_percentage, estimated_resolution_at, resolved_at, resolved_by, resolution_notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                cid, "CTD-2026-00001", citizen_id, "Potholes and damaged roads",
                "Deep crater pothole near intersection",
                "Large pothole in the right lane damaging vehicular rims and posing danger to cyclists.",
                16.5164, 80.4638, "Intersection of 4th Ave & Elm St", "ZONE_19", "High", "Resolved",
                100, est_date, resolved_date, "Citidy Operations Director",
                "Pothole was cleaned, cold-mix base applied, asphalt sealed and compacted flush with road grade.",
                (now - timedelta(days=2)).isoformat()
            ))

            # Add Before and After attachment records
            cursor.execute("""
            INSERT INTO complaint_attachments (id, complaint_id, uploaded_by, attachment_type, file_path, file_name, caption)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                str(uuid.uuid4()), cid, citizen_id, "before",
                "uploads/demo_pothole_before.svg", "pothole_hazard_before.svg", "Original hazard photographed by citizen"
            ))

            cursor.execute("""
            INSERT INTO complaint_attachments (id, complaint_id, uploaded_by, attachment_type, file_path, file_name, caption)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                str(uuid.uuid4()), cid, admin_id, "after",
                "uploads/demo_pothole_after.svg", "pothole_repaired_after.svg", "Completed asphalt compaction and road restoration"
            ))

            # Add Status History
            cursor.execute("""
            INSERT INTO complaint_status_history (id, complaint_id, old_status, new_status, progress_percentage, note, changed_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (str(uuid.uuid4()), cid, None, "Submitted", 0, "Citizen complaint submitted", citizen_id, (now - timedelta(days=2)).isoformat()))

            cursor.execute("""
            INSERT INTO complaint_status_history (id, complaint_id, old_status, new_status, progress_percentage, note, changed_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (str(uuid.uuid4()), cid, "Submitted", "Verified", 20, "Issue inspected and verified by operations", admin_id, (now - timedelta(days=1, hours=18)).isoformat()))

            cursor.execute("""
            INSERT INTO complaint_status_history (id, complaint_id, old_status, new_status, progress_percentage, note, changed_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (str(uuid.uuid4()), cid, "Verified", "Assigned", 30, "Assigned to Roads & Highway Maintenance Crew #4", admin_id, (now - timedelta(days=1, hours=12)).isoformat()))

            cursor.execute("""
            INSERT INTO complaint_status_history (id, complaint_id, old_status, new_status, progress_percentage, note, changed_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (str(uuid.uuid4()), cid, "Assigned", "In Progress", 60, "Crew on site; debris cleared, aggregate compacted", admin_id, (now - timedelta(hours=6)).isoformat()))

            cursor.execute("""
            INSERT INTO complaint_status_history (id, complaint_id, old_status, new_status, progress_percentage, note, changed_by, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (str(uuid.uuid4()), cid, "In Progress", "Resolved", 100, "Road restoration completed and verified", admin_id, resolved_date))

            # Add Notification
            cursor.execute("""
            INSERT INTO notifications (id, recipient_user_id, complaint_id, title, message, notification_type, is_read, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                str(uuid.uuid4()), citizen_id, cid,
                "Complaint Resolved: CTD-2026-00001",
                "Your reported pothole at Intersection of 4th Ave & Elm St has been repaired. View the resolution evidence photograph.",
                "resolved", 0, resolved_date
            ))

        conn.commit()


# Initialize demonstration SVG illustrations for before & after evidence
def ensure_demo_photos() -> None:
    before_svg = UPLOAD_DIR / "demo_pothole_before.svg"
    after_svg = UPLOAD_DIR / "demo_pothole_after.svg"

    if not before_svg.exists():
        before_svg.write_text("""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300" width="100%" height="100%">
  <rect width="400" height="300" fill="#334155"/>
  <rect x="0" y="140" width="400" height="20" fill="#e2e8f0" stroke="#94a3b8" stroke-dasharray="20 15"/>
  <ellipse cx="200" cy="180" rx="90" ry="45" fill="#0f172a"/>
  <ellipse cx="195" cy="178" rx="75" ry="35" fill="#1e293b"/>
  <path d="M120 170 Q160 195 200 180 T280 185" stroke="#ef4444" stroke-width="3" fill="none"/>
  <rect x="15" y="15" width="130" height="28" rx="6" fill="#ef4444"/>
  <text x="80" y="34" fill="#ffffff" font-family="sans-serif" font-weight="bold" font-size="12" text-anchor="middle">BEFORE: DAMAGE</text>
  <text x="200" y="270" fill="#cbd5e1" font-family="sans-serif" font-size="12" text-anchor="middle">Citizen Hazard Photo · Severe Asphalt Cavity</text>
</svg>""", encoding="utf-8")

    if not after_svg.exists():
        after_svg.write_text("""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300" width="100%" height="100%">
  <rect width="400" height="300" fill="#334155"/>
  <rect x="0" y="140" width="400" height="20" fill="#e2e8f0" stroke="#94a3b8" stroke-dasharray="20 15"/>
  <ellipse cx="200" cy="180" rx="95" ry="48" fill="#1e293b" stroke="#10b981" stroke-width="2"/>
  <ellipse cx="200" cy="180" rx="88" ry="42" fill="#0f172a"/>
  <circle cx="200" cy="180" r="16" fill="#10b981"/>
  <path d="M193 180 L198 185 L208 174" stroke="#ffffff" stroke-width="3" fill="none" stroke-linecap="round"/>
  <rect x="15" y="15" width="140" height="28" rx="6" fill="#10b981"/>
  <text x="85" y="34" fill="#ffffff" font-family="sans-serif" font-weight="bold" font-size="12" text-anchor="middle">AFTER: REPAIRED</text>
  <text x="200" y="270" fill="#cbd5e1" font-family="sans-serif" font-size="12" text-anchor="middle">Municipal Crew Evidence · Asphalt Compaction Verified</text>
</svg>""", encoding="utf-8")


if __name__ == "__main__":
    init_db()
    ensure_demo_photos()
    print("Citidy database initialized successfully.")
    print("Admin:   admin@citidy.gov   / CitidyAdmin2026!")
    print("Citizen: citizen@citidy.gov / Citizen2026!")
