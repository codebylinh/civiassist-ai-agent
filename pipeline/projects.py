"""
Construction project tracker — projects, phases, RFIs, submittals, site issues.
Stored in a dedicated SQLite database.
"""
import sqlite3
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager
import config

DB_PATH = config.DATA_DIR / "projects.sqlite"

PHASES = [
    "pre_design", "schematic_design", "design_development",
    "construction_documents", "permitting", "bidding",
    "construction", "closeout", "warranty",
]

RFI_STATUSES     = ["open", "answered", "closed"]
SUBMITTAL_STATUSES = ["pending", "approved", "approved_as_noted", "revise_resubmit", "rejected"]
ISSUE_SEVERITIES = ["critical", "high", "medium", "low"]


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
            CREATE TABLE IF NOT EXISTS projects (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                name         TEXT NOT NULL UNIQUE,
                description  TEXT,
                client       TEXT,
                location     TEXT,
                phase        TEXT DEFAULT 'pre_design',
                start_date   TEXT,
                target_date  TEXT,
                status       TEXT DEFAULT 'active',
                created_at   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS rfis (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id   INTEGER NOT NULL,
                rfi_number   TEXT NOT NULL,
                subject      TEXT NOT NULL,
                question     TEXT NOT NULL,
                discipline   TEXT DEFAULT 'civil',
                status       TEXT DEFAULT 'open',
                response     TEXT,
                submitted_by TEXT,
                due_date     TEXT,
                created_at   TEXT NOT NULL,
                closed_at    TEXT,
                FOREIGN KEY (project_id) REFERENCES projects(id)
            );

            CREATE TABLE IF NOT EXISTS submittals (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id   INTEGER NOT NULL,
                spec_section TEXT,
                description  TEXT NOT NULL,
                submitted_by TEXT,
                status       TEXT DEFAULT 'pending',
                review_notes TEXT,
                created_at   TEXT NOT NULL,
                reviewed_at  TEXT,
                FOREIGN KEY (project_id) REFERENCES projects(id)
            );

            CREATE TABLE IF NOT EXISTS site_issues (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id   INTEGER NOT NULL,
                description  TEXT NOT NULL,
                severity     TEXT DEFAULT 'medium',
                location     TEXT,
                reported_by  TEXT,
                status       TEXT DEFAULT 'open',
                resolution   TEXT,
                created_at   TEXT NOT NULL,
                resolved_at  TEXT,
                FOREIGN KEY (project_id) REFERENCES projects(id)
            );

            CREATE TABLE IF NOT EXISTS phase_log (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id   INTEGER NOT NULL,
                from_phase   TEXT,
                to_phase     TEXT NOT NULL,
                notes        TEXT,
                ts           TEXT NOT NULL,
                FOREIGN KEY (project_id) REFERENCES projects(id)
            );
        """)


# --- Projects ---

def create_project(name: str, description: str = "", client: str = "",
                   location: str = "", start_date: str = "", target_date: str = "") -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO projects (name, description, client, location, start_date, target_date, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (name, description, client, location, start_date, target_date, datetime.now().isoformat())
        )
        return cur.lastrowid


def get_project(project_id: int) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    return dict(row) if row else None


def get_project_by_name(name: str) -> dict | None:
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM projects WHERE LOWER(name) LIKE LOWER(?)", (f"%{name}%",)
        ).fetchone()
    return dict(row) if row else None


def list_projects(status: str = "active") -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM projects WHERE status=? ORDER BY id DESC", (status,)
        ).fetchall()
    return [dict(r) for r in rows]


def advance_phase(project_id: int, new_phase: str, notes: str = ""):
    project = get_project(project_id)
    if not project:
        return
    with _conn() as c:
        c.execute(
            "UPDATE projects SET phase=? WHERE id=?", (new_phase, project_id)
        )
        c.execute(
            "INSERT INTO phase_log (project_id, from_phase, to_phase, notes, ts) VALUES (?,?,?,?,?)",
            (project_id, project["phase"], new_phase, notes, datetime.now().isoformat())
        )


# --- RFIs ---

def create_rfi(project_id: int, subject: str, question: str,
               discipline: str = "civil", submitted_by: str = "",
               due_date: str = "") -> int:
    with _conn() as c:
        count = c.execute(
            "SELECT COUNT(*) FROM rfis WHERE project_id=?", (project_id,)
        ).fetchone()[0]
        rfi_number = f"RFI-{count + 1:03d}"
        cur = c.execute(
            "INSERT INTO rfis (project_id, rfi_number, subject, question, discipline, "
            "submitted_by, due_date, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (project_id, rfi_number, subject, question, discipline,
             submitted_by, due_date, datetime.now().isoformat())
        )
        return cur.lastrowid


def answer_rfi(rfi_id: int, response: str):
    with _conn() as c:
        c.execute(
            "UPDATE rfis SET response=?, status='answered' WHERE id=?",
            (response, rfi_id)
        )


def close_rfi(rfi_id: int):
    with _conn() as c:
        c.execute(
            "UPDATE rfis SET status='closed', closed_at=? WHERE id=?",
            (datetime.now().isoformat(), rfi_id)
        )


def list_rfis(project_id: int, status: str | None = None) -> list[dict]:
    with _conn() as c:
        if status:
            rows = c.execute(
                "SELECT * FROM rfis WHERE project_id=? AND status=? ORDER BY id",
                (project_id, status)
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM rfis WHERE project_id=? ORDER BY id", (project_id,)
            ).fetchall()
    return [dict(r) for r in rows]


# --- Submittals ---

def create_submittal(project_id: int, description: str,
                     spec_section: str = "", submitted_by: str = "") -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO submittals (project_id, spec_section, description, submitted_by, created_at) "
            "VALUES (?,?,?,?,?)",
            (project_id, spec_section, description, submitted_by, datetime.now().isoformat())
        )
        return cur.lastrowid


def review_submittal(submittal_id: int, status: str, notes: str = ""):
    with _conn() as c:
        c.execute(
            "UPDATE submittals SET status=?, review_notes=?, reviewed_at=? WHERE id=?",
            (status, notes, datetime.now().isoformat(), submittal_id)
        )


def list_submittals(project_id: int, status: str | None = None) -> list[dict]:
    with _conn() as c:
        if status:
            rows = c.execute(
                "SELECT * FROM submittals WHERE project_id=? AND status=? ORDER BY id",
                (project_id, status)
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT * FROM submittals WHERE project_id=? ORDER BY id", (project_id,)
            ).fetchall()
    return [dict(r) for r in rows]


# --- Site Issues ---

def log_site_issue(project_id: int, description: str, severity: str = "medium",
                   location: str = "", reported_by: str = "") -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO site_issues (project_id, description, severity, location, reported_by, created_at) "
            "VALUES (?,?,?,?,?,?)",
            (project_id, description, severity, location, reported_by, datetime.now().isoformat())
        )
        return cur.lastrowid


def resolve_site_issue(issue_id: int, resolution: str):
    with _conn() as c:
        c.execute(
            "UPDATE site_issues SET status='resolved', resolution=?, resolved_at=? WHERE id=?",
            (resolution, datetime.now().isoformat(), issue_id)
        )


def list_site_issues(project_id: int, status: str = "open") -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM site_issues WHERE project_id=? AND status=? ORDER BY "
            "CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END",
            (project_id, status)
        ).fetchall()
    return [dict(r) for r in rows]


# --- Summary ---

def project_summary(project_id: int) -> str:
    project = get_project(project_id)
    if not project:
        return "Project not found."

    open_rfis      = list_rfis(project_id, status="open")
    open_submittals = list_submittals(project_id, status="pending")
    open_issues    = list_site_issues(project_id, status="open")
    critical_issues = [i for i in open_issues if i["severity"] == "critical"]

    lines = [
        f"Project: {project['name']}",
        f"Client: {project['client'] or 'N/A'}  |  Location: {project['location'] or 'N/A'}",
        f"Phase: {project['phase']}  |  Status: {project['status']}",
        f"Target completion: {project['target_date'] or 'TBD'}",
        "",
        f"Open RFIs: {len(open_rfis)}",
        f"Pending submittals: {len(open_submittals)}",
        f"Open site issues: {len(open_issues)} ({len(critical_issues)} critical)",
    ]

    if critical_issues:
        lines.append("\nCRITICAL ISSUES:")
        for i in critical_issues:
            lines.append(f"  ⚠ {i['description'][:80]}")

    if open_rfis:
        lines.append("\nOpen RFIs:")
        for r in open_rfis[:5]:
            lines.append(f"  [{r['rfi_number']}] {r['subject'][:60]}")

    return "\n".join(lines)


def all_projects_summary() -> str:
    projects = list_projects()
    if not projects:
        return "No active projects."
    lines = []
    for p in projects:
        with _conn() as c:
            open_rfis   = c.execute("SELECT COUNT(*) FROM rfis WHERE project_id=? AND status='open'", (p["id"],)).fetchone()[0]
            open_issues = c.execute("SELECT COUNT(*) FROM site_issues WHERE project_id=? AND status='open'", (p["id"],)).fetchone()[0]
        lines.append(
            f"#{p['id']} {p['name']} | {p['phase']} | RFIs: {open_rfis} | Issues: {open_issues}"
        )
    return "\n".join(lines)
