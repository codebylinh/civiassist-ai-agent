from datetime import datetime
from .base import MemoryDB
import config


class ThoughtsMemory(MemoryDB):
    def __init__(self):
        super().__init__(config.DB_PATHS["thoughts"])

    def _init_schema(self):
        with self.conn() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS thoughts (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    content    TEXT NOT NULL,
                    thought_type TEXT DEFAULT 'internal',
                    session_id INTEGER,
                    ts         TEXT NOT NULL
                );
            """)

    def add(self, content: str, thought_type: str = "internal", session_id: int | None = None):
        with self.conn() as c:
            c.execute(
                "INSERT INTO thoughts (content, thought_type, session_id, ts) VALUES (?,?,?,?)",
                (content, thought_type, session_id, datetime.now().isoformat())
            )

    def recent(self, n: int = 10, thought_type: str | None = None) -> list[dict]:
        with self.conn() as c:
            if thought_type:
                rows = c.execute(
                    "SELECT * FROM thoughts WHERE thought_type=? ORDER BY id DESC LIMIT ?",
                    (thought_type, n)
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM thoughts ORDER BY id DESC LIMIT ?", (n,)
                ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def pending_open_loops(self) -> list[dict]:
        return self.recent(5, thought_type="open_loop")
