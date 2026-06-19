"""
Ticket storage — single SQLite database for the full support triage lifecycle.
"""
import sqlite3
from datetime import datetime
from pathlib import Path
from contextlib import contextmanager
import config

DB_PATH = config.DATA_DIR / "support.sqlite"


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
            CREATE TABLE IF NOT EXISTS tickets (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                subject    TEXT NOT NULL,
                body       TEXT NOT NULL,
                source     TEXT DEFAULT 'manual',
                status     TEXT DEFAULT 'pending',
                created_at TEXT NOT NULL,
                updated_at TEXT
            );

            CREATE TABLE IF NOT EXISTS classifications (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id   INTEGER NOT NULL UNIQUE,
                category    TEXT NOT NULL,
                priority    TEXT NOT NULL,
                sentiment   TEXT NOT NULL,
                routing     TEXT NOT NULL,
                confidence  REAL NOT NULL,
                reasoning   TEXT,
                classified_at TEXT NOT NULL,
                FOREIGN KEY (ticket_id) REFERENCES tickets(id)
            );

            CREATE TABLE IF NOT EXISTS responses (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id   INTEGER NOT NULL,
                draft       TEXT NOT NULL,
                status      TEXT DEFAULT 'pending',
                created_at  TEXT NOT NULL,
                FOREIGN KEY (ticket_id) REFERENCES tickets(id)
            );

            CREATE TABLE IF NOT EXISTS triage_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ticket_id   INTEGER NOT NULL,
                action      TEXT NOT NULL,
                reason      TEXT,
                agent_notes TEXT,
                ts          TEXT NOT NULL,
                FOREIGN KEY (ticket_id) REFERENCES tickets(id)
            );

            CREATE TABLE IF NOT EXISTS knowledge_base (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                category    TEXT NOT NULL,
                issue       TEXT NOT NULL,
                resolution  TEXT NOT NULL,
                use_count   INTEGER DEFAULT 0,
                created_at  TEXT NOT NULL
            );

            CREATE VIRTUAL TABLE IF NOT EXISTS kb_fts
                USING fts5(issue, resolution, content=knowledge_base, content_rowid=id);
            CREATE TRIGGER IF NOT EXISTS kb_ai AFTER INSERT ON knowledge_base BEGIN
                INSERT INTO kb_fts(rowid, issue, resolution) VALUES (new.id, new.issue, new.resolution);
            END;
        """)


# --- Tickets ---

def create_ticket(subject: str, body: str, source: str = "manual") -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO tickets (subject, body, source, created_at) VALUES (?,?,?,?)",
            (subject, body, source, datetime.now().isoformat())
        )
        return cur.lastrowid


def get_ticket(ticket_id: int) -> dict | None:
    with _conn() as c:
        row = c.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
    return dict(row) if row else None


def update_ticket_status(ticket_id: int, status: str):
    with _conn() as c:
        c.execute(
            "UPDATE tickets SET status=?, updated_at=? WHERE id=?",
            (status, datetime.now().isoformat(), ticket_id)
        )


def list_tickets(status: str | None = None, limit: int = 50) -> list[dict]:
    with _conn() as c:
        if status:
            rows = c.execute(
                "SELECT t.*, cl.category, cl.priority, cl.routing "
                "FROM tickets t LEFT JOIN classifications cl ON cl.ticket_id = t.id "
                "WHERE t.status=? ORDER BY t.id DESC LIMIT ?", (status, limit)
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT t.*, cl.category, cl.priority, cl.routing "
                "FROM tickets t LEFT JOIN classifications cl ON cl.ticket_id = t.id "
                "ORDER BY t.id DESC LIMIT ?", (limit,)
            ).fetchall()
    return [dict(r) for r in rows]


# --- Classifications ---

def save_classification(ticket_id: int, category: str, priority: str,
                        sentiment: str, routing: str, confidence: float,
                        reasoning: str = "") -> int:
    with _conn() as c:
        try:
            cur = c.execute(
                "INSERT INTO classifications "
                "(ticket_id, category, priority, sentiment, routing, confidence, reasoning, classified_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (ticket_id, category, priority, sentiment, routing,
                 confidence, reasoning, datetime.now().isoformat())
            )
            return cur.lastrowid
        except sqlite3.IntegrityError:
            c.execute(
                "UPDATE classifications SET category=?, priority=?, sentiment=?, routing=?, "
                "confidence=?, reasoning=?, classified_at=? WHERE ticket_id=?",
                (category, priority, sentiment, routing, confidence,
                 reasoning, datetime.now().isoformat(), ticket_id)
            )
            return ticket_id


def get_classification(ticket_id: int) -> dict | None:
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM classifications WHERE ticket_id=?", (ticket_id,)
        ).fetchone()
    return dict(row) if row else None


# --- Responses ---

def save_response(ticket_id: int, draft: str) -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO responses (ticket_id, draft, created_at) VALUES (?,?,?)",
            (ticket_id, draft, datetime.now().isoformat())
        )
        return cur.lastrowid


def get_response(ticket_id: int) -> dict | None:
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM responses WHERE ticket_id=? ORDER BY id DESC LIMIT 1",
            (ticket_id,)
        ).fetchone()
    return dict(row) if row else None


def approve_response(ticket_id: int):
    with _conn() as c:
        c.execute(
            "UPDATE responses SET status='approved' WHERE ticket_id=?", (ticket_id,)
        )


# --- Triage log ---

def log_action(ticket_id: int, action: str, reason: str = "", notes: str = ""):
    with _conn() as c:
        c.execute(
            "INSERT INTO triage_log (ticket_id, action, reason, agent_notes, ts) VALUES (?,?,?,?,?)",
            (ticket_id, action, reason, notes, datetime.now().isoformat())
        )


def get_log(ticket_id: int) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM triage_log WHERE ticket_id=? ORDER BY id", (ticket_id,)
        ).fetchall()
    return [dict(r) for r in rows]


# --- Knowledge base ---

def add_kb_entry(category: str, issue: str, resolution: str):
    with _conn() as c:
        c.execute(
            "INSERT INTO knowledge_base (category, issue, resolution, created_at) VALUES (?,?,?,?)",
            (category, issue, resolution, datetime.now().isoformat())
        )


def search_kb(query: str, limit: int = 3) -> list[dict]:
    with _conn() as c:
        rows = c.execute("""
            SELECT kb.id, kb.category, kb.issue, kb.resolution, kb.use_count
            FROM kb_fts
            JOIN knowledge_base kb ON kb_fts.rowid = kb.id
            WHERE kb_fts MATCH ?
            ORDER BY kb.use_count DESC, bm25(kb_fts)
            LIMIT ?
        """, (query, limit)).fetchall()
        if rows:
            ids = [r["id"] for r in rows]
            c.execute(
                f"UPDATE knowledge_base SET use_count = use_count + 1 "
                f"WHERE id IN ({','.join('?' * len(ids))})", ids
            )
    return [dict(r) for r in rows]


# --- Metrics ---

def metrics() -> dict:
    with _conn() as c:
        total   = c.execute("SELECT COUNT(*) FROM tickets").fetchone()[0]
        by_status = dict(c.execute(
            "SELECT status, COUNT(*) FROM tickets GROUP BY status"
        ).fetchall())
        by_category = dict(c.execute(
            "SELECT category, COUNT(*) FROM classifications GROUP BY category"
        ).fetchall())
        by_priority = dict(c.execute(
            "SELECT priority, COUNT(*) FROM classifications GROUP BY priority"
        ).fetchall())
        auto_resolved = c.execute(
            "SELECT COUNT(*) FROM triage_log WHERE action='auto_resolved'"
        ).fetchone()[0]
    return {
        "total": total,
        "by_status": by_status,
        "by_category": by_category,
        "by_priority": by_priority,
        "auto_resolved": auto_resolved,
    }
