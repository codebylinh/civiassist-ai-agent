"""
LMCS — LIA Memory Consolidation System.

Memory lifecycle pyramid:
  Active turns (episodic) → Daily reflection → Weekly essence
  → Pattern consolidation → Fundamental insights → Core identity (anchors)
"""
from datetime import datetime, date, timedelta
from .base import MemoryDB
import config


class ConsolidationMemory(MemoryDB):
    def __init__(self):
        super().__init__(config.DB_PATHS["lmcs"])

    def _init_schema(self):
        with self.conn() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS anchors (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    content      TEXT NOT NULL,
                    anchor_level INTEGER DEFAULT 1,
                    created_at   TEXT NOT NULL,
                    last_reviewed TEXT,
                    context      TEXT
                );
                CREATE TABLE IF NOT EXISTS weekly_essences (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    week_start  TEXT NOT NULL UNIQUE,
                    essence     TEXT NOT NULL,
                    created_at  TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS patterns (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    pattern      TEXT NOT NULL,
                    frequency    INTEGER DEFAULT 1,
                    first_seen   TEXT NOT NULL,
                    last_seen    TEXT NOT NULL,
                    archived     INTEGER DEFAULT 0,
                    insight      TEXT
                );
                CREATE TABLE IF NOT EXISTS consolidation_log (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_type   TEXT NOT NULL,
                    ts         TEXT NOT NULL,
                    notes      TEXT
                );
            """)

    # --- Anchors ---
    def add_anchor(self, content: str, level: int = 1, context: str = "") -> int:
        with self.conn() as c:
            cur = c.execute(
                "INSERT INTO anchors (content, anchor_level, created_at, context) VALUES (?,?,?,?)",
                (content, level, datetime.now().isoformat(), context)
            )
            return cur.lastrowid

    def get_anchors(self, min_level: int = 1) -> list[dict]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT * FROM anchors WHERE anchor_level >= ? ORDER BY anchor_level DESC, id DESC",
                (min_level,)
            ).fetchall()
        return [dict(r) for r in rows]

    def review_anchor(self, anchor_id: int, new_level: int | None = None):
        with self.conn() as c:
            if new_level is not None:
                c.execute(
                    "UPDATE anchors SET anchor_level=?, last_reviewed=? WHERE id=?",
                    (new_level, datetime.now().isoformat(), anchor_id)
                )
            else:
                c.execute(
                    "UPDATE anchors SET last_reviewed=? WHERE id=?",
                    (datetime.now().isoformat(), anchor_id)
                )

    # --- Weekly essences ---
    def save_weekly_essence(self, essence: str, week_start: date | None = None):
        if week_start is None:
            today = date.today()
            week_start = today - timedelta(days=today.weekday())
        with self.conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO weekly_essences (week_start, essence, created_at) VALUES (?,?,?)",
                (week_start.isoformat(), essence, datetime.now().isoformat())
            )

    def recent_essences(self, n: int = 4) -> list[dict]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT * FROM weekly_essences ORDER BY week_start DESC LIMIT ?", (n,)
            ).fetchall()
        return [dict(r) for r in rows]

    # --- Patterns ---
    def observe_pattern(self, pattern: str):
        with self.conn() as c:
            existing = c.execute(
                "SELECT id, frequency FROM patterns WHERE pattern=? AND archived=0",
                (pattern,)
            ).fetchone()
            if existing:
                c.execute(
                    "UPDATE patterns SET frequency=frequency+1, last_seen=? WHERE id=?",
                    (datetime.now().isoformat(), existing["id"])
                )
            else:
                now = datetime.now().isoformat()
                c.execute(
                    "INSERT INTO patterns (pattern, first_seen, last_seen) VALUES (?,?,?)",
                    (pattern, now, now)
                )

    def recurring_patterns(self, min_frequency: int = 3) -> list[dict]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT * FROM patterns WHERE frequency >= ? AND archived=0 "
                "ORDER BY frequency DESC LIMIT 20",
                (min_frequency,)
            ).fetchall()
        return [dict(r) for r in rows]

    # --- Log ---
    def log_run(self, run_type: str, notes: str = ""):
        with self.conn() as c:
            c.execute(
                "INSERT INTO consolidation_log (run_type, ts, notes) VALUES (?,?,?)",
                (run_type, datetime.now().isoformat(), notes)
            )

    def last_run(self, run_type: str) -> dict | None:
        with self.conn() as c:
            row = c.execute(
                "SELECT * FROM consolidation_log WHERE run_type=? ORDER BY id DESC LIMIT 1",
                (run_type,)
            ).fetchone()
        return dict(row) if row else None
