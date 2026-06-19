from datetime import datetime
from .base import MemoryDB
import config


class EpisodicMemory(MemoryDB):
    def __init__(self):
        super().__init__(config.DB_PATHS["episodic"])

    def _init_schema(self):
        with self.conn() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    start_ts  TEXT NOT NULL,
                    end_ts    TEXT,
                    summary   TEXT,
                    turn_count INTEGER DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS turns (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id INTEGER NOT NULL,
                    role       TEXT NOT NULL,
                    content    TEXT NOT NULL,
                    ts         TEXT NOT NULL,
                    FOREIGN KEY (session_id) REFERENCES sessions(id)
                );
            """)

    def new_session(self) -> int:
        with self.conn() as c:
            cur = c.execute(
                "INSERT INTO sessions (start_ts) VALUES (?)",
                (datetime.now().isoformat(),)
            )
            return cur.lastrowid

    def add_turn(self, session_id: int, role: str, content: str):
        with self.conn() as c:
            c.execute(
                "INSERT INTO turns (session_id, role, content, ts) VALUES (?,?,?,?)",
                (session_id, role, content, datetime.now().isoformat())
            )
            c.execute(
                "UPDATE sessions SET turn_count = turn_count + 1 WHERE id = ?",
                (session_id,)
            )

    def close_session(self, session_id: int, summary: str):
        with self.conn() as c:
            c.execute(
                "UPDATE sessions SET end_ts=?, summary=? WHERE id=?",
                (datetime.now().isoformat(), summary, session_id)
            )

    def recent_turns(self, n: int = 20) -> list[dict]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT role, content, ts FROM turns ORDER BY id DESC LIMIT ?", (n,)
            ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def recent_sessions(self, n: int = 5) -> list[dict]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT id, start_ts, end_ts, summary, turn_count FROM sessions "
                "WHERE summary IS NOT NULL ORDER BY id DESC LIMIT ?", (n,)
            ).fetchall()
        return [dict(r) for r in rows]
