"""
Community safety database — resident complaints, safety alerts,
and construction-to-resident notifications.
"""
import sqlite3
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager
import config

DB_PATH = config.DATA_DIR / "community.sqlite"

COMPLAINT_CATEGORIES = [
    "noise",             # outside permitted hours / excessive levels
    "dust_air",          # dust clouds, air quality
    "debris_hazard",     # falling / loose debris on public path
    "access_blocked",    # blocked sidewalk, road, driveway without notice
    "vibration_damage",  # cracks, shaking, property damage
    "traffic_disruption",# unexpected road closures / lane changes
    "structural_concern",# visible structural issue at site boundary
    "water_flooding",    # dewatering runoff, mud on public road
    "emergency",         # immediate danger to public safety
    "general",
]

SEVERITIES = ["emergency", "high", "medium", "low"]
ROUTINGS   = [
    "emergency_services",   # call 911 + superintendent immediately
    "site_superintendent",  # site action required within 1 hour
    "project_manager",      # PM coordination required within 24 hours
    "city_inspector",       # code violation — notify authority
    "auto_acknowledge",     # standard complaint — auto-respond with info
]


@contextmanager
def _conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA journal_mode=WAL")
    try:
        yield c
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _conn() as c:
        c.executescript("""
            CREATE TABLE IF NOT EXISTS complaints (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                description  TEXT NOT NULL,
                category     TEXT DEFAULT 'general',
                location     TEXT,
                reported_by  TEXT,
                contact      TEXT,
                urgency      TEXT DEFAULT 'medium',
                status       TEXT DEFAULT 'open',
                created_at   TEXT NOT NULL,
                resolved_at  TEXT
            );

            CREATE TABLE IF NOT EXISTS complaint_classifications (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                complaint_id INTEGER NOT NULL UNIQUE,
                category     TEXT NOT NULL,
                severity     TEXT NOT NULL,
                public_risk  TEXT NOT NULL,
                routing      TEXT NOT NULL,
                confidence   REAL NOT NULL,
                reasoning    TEXT,
                classified_at TEXT NOT NULL,
                FOREIGN KEY (complaint_id) REFERENCES complaints(id)
            );

            CREATE TABLE IF NOT EXISTS resolutions (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                complaint_id    INTEGER NOT NULL,
                action_taken    TEXT NOT NULL,
                resolved_by     TEXT,
                resident_notice TEXT,
                created_at      TEXT NOT NULL,
                FOREIGN KEY (complaint_id) REFERENCES complaints(id)
            );

            CREATE TABLE IF NOT EXISTS safety_alerts (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name  TEXT,
                description   TEXT NOT NULL,
                severity      TEXT DEFAULT 'high',
                affected_area TEXT,
                status        TEXT DEFAULT 'active',
                created_at    TEXT NOT NULL,
                resolved_at   TEXT
            );

            CREATE TABLE IF NOT EXISTS notifications (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                project_name TEXT,
                title        TEXT NOT NULL,
                message      TEXT NOT NULL,
                urgency      TEXT DEFAULT 'normal',
                target_area  TEXT,
                created_at   TEXT NOT NULL
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS complaints_fts
                USING fts5(description, location, content=complaints, content_rowid=id);
            CREATE TRIGGER IF NOT EXISTS complaints_ai AFTER INSERT ON complaints BEGIN
                INSERT INTO complaints_fts(rowid, description, location)
                    VALUES (new.id, new.description, new.location);
            END;
        """)


# --- Complaints ---

def file_complaint(description: str, location: str = "", reported_by: str = "",
                   contact: str = "", urgency: str = "medium") -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO complaints (description, location, reported_by, contact, urgency, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (description, location, reported_by, contact, urgency, datetime.now().isoformat())
        )
        return cur.lastrowid


def get_complaint(complaint_id: int) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM complaints WHERE id=?", (complaint_id,)).fetchone()
    return dict(row) if row else None


def list_complaints(status: str | None = None, severity: str | None = None,
                    limit: int = 50) -> list[dict]:
    with _conn() as c:
        if severity:
            rows = c.execute("""
                SELECT c.*, cc.category, cc.severity, cc.routing
                FROM complaints c
                LEFT JOIN complaint_classifications cc ON cc.complaint_id = c.id
                WHERE cc.severity=? ORDER BY c.id DESC LIMIT ?
            """, (severity, limit)).fetchall()
        elif status:
            rows = c.execute("""
                SELECT c.*, cc.category, cc.severity, cc.routing
                FROM complaints c
                LEFT JOIN complaint_classifications cc ON cc.complaint_id = c.id
                WHERE c.status=? ORDER BY c.id DESC LIMIT ?
            """, (status, limit)).fetchall()
        else:
            rows = c.execute("""
                SELECT c.*, cc.category, cc.severity, cc.routing
                FROM complaints c
                LEFT JOIN complaint_classifications cc ON cc.complaint_id = c.id
                ORDER BY
                    CASE cc.severity WHEN 'emergency' THEN 0 WHEN 'high' THEN 1
                                     WHEN 'medium' THEN 2 ELSE 3 END,
                    c.id DESC LIMIT ?
            """, (limit,)).fetchall()
    return [dict(r) for r in rows]


def save_complaint_classification(complaint_id: int, category: str, severity: str,
                                   public_risk: str, routing: str,
                                   confidence: float, reasoning: str = ""):
    with _conn() as c:
        try:
            c.execute(
                "INSERT INTO complaint_classifications "
                "(complaint_id, category, severity, public_risk, routing, confidence, reasoning, classified_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (complaint_id, category, severity, public_risk, routing,
                 confidence, reasoning, datetime.now().isoformat())
            )
        except sqlite3.IntegrityError:
            c.execute(
                "UPDATE complaint_classifications SET category=?, severity=?, public_risk=?, "
                "routing=?, confidence=?, reasoning=?, classified_at=? WHERE complaint_id=?",
                (category, severity, public_risk, routing, confidence,
                 reasoning, datetime.now().isoformat(), complaint_id)
            )


def resolve_complaint(complaint_id: int, action_taken: str,
                       resolved_by: str = "", resident_notice: str = ""):
    with _conn() as c:
        c.execute(
            "UPDATE complaints SET status='resolved', resolved_at=? WHERE id=?",
            (datetime.now().isoformat(), complaint_id)
        )
        c.execute(
            "INSERT INTO resolutions (complaint_id, action_taken, resolved_by, resident_notice, created_at) "
            "VALUES (?,?,?,?,?)",
            (complaint_id, action_taken, resolved_by, resident_notice, datetime.now().isoformat())
        )


def get_resolution(complaint_id: int) -> dict | None:
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM resolutions WHERE complaint_id=? ORDER BY id DESC LIMIT 1",
            (complaint_id,)
        ).fetchone()
    return dict(row) if row else None


# --- Safety alerts ---

def create_safety_alert(description: str, severity: str = "high",
                         project_name: str = "", affected_area: str = "") -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO safety_alerts (project_name, description, severity, affected_area, created_at) "
            "VALUES (?,?,?,?,?)",
            (project_name, description, severity, affected_area, datetime.now().isoformat())
        )
        return cur.lastrowid


def resolve_safety_alert(alert_id: int):
    with _conn() as c:
        c.execute(
            "UPDATE safety_alerts SET status='resolved', resolved_at=? WHERE id=?",
            (datetime.now().isoformat(), alert_id)
        )


def active_safety_alerts() -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM safety_alerts WHERE status='active' "
            "ORDER BY CASE severity WHEN 'emergency' THEN 0 WHEN 'high' THEN 1 ELSE 2 END",
        ).fetchall()
    return [dict(r) for r in rows]


# --- Notifications ---

def create_notification(title: str, message: str, project_name: str = "",
                         urgency: str = "normal", target_area: str = "") -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO notifications (project_name, title, message, urgency, target_area, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (project_name, title, message, urgency, target_area, datetime.now().isoformat())
        )
        return cur.lastrowid


def recent_notifications(limit: int = 10) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM notifications ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


# --- Metrics ---

def community_metrics() -> dict:
    with _conn() as c:
        total      = c.execute("SELECT COUNT(*) FROM complaints").fetchone()[0]
        open_count = c.execute("SELECT COUNT(*) FROM complaints WHERE status='open'").fetchone()[0]
        by_cat     = dict(c.execute(
            "SELECT category, COUNT(*) FROM complaint_classifications GROUP BY category"
        ).fetchall())
        by_sev     = dict(c.execute(
            "SELECT severity, COUNT(*) FROM complaint_classifications GROUP BY severity"
        ).fetchall())
        emergencies = c.execute(
            "SELECT COUNT(*) FROM complaint_classifications WHERE severity='emergency'"
        ).fetchone()[0]
        alerts     = c.execute(
            "SELECT COUNT(*) FROM safety_alerts WHERE status='active'"
        ).fetchone()[0]
    return {
        "total_complaints": total,
        "open_complaints":  open_count,
        "by_category":      by_cat,
        "by_severity":      by_sev,
        "emergencies":      emergencies,
        "active_alerts":    alerts,
    }
