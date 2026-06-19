"""
Long-term semantic memory using SQLite FTS5 for full-text retrieval.
Importance and recency scores combine to rank retrieved memories.
"""
from datetime import datetime
from .base import MemoryDB
import config


class SemanticMemory(MemoryDB):
    def __init__(self):
        super().__init__(config.DB_PATHS["semantic"])

    def _init_schema(self):
        with self.conn() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS memories (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    content      TEXT NOT NULL,
                    category     TEXT DEFAULT 'general',
                    importance   REAL DEFAULT 1.0,
                    created_at   TEXT NOT NULL,
                    last_accessed TEXT,
                    access_count INTEGER DEFAULT 0,
                    memory_type  TEXT DEFAULT 'PATTERN'
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts
                    USING fts5(content, content=memories, content_rowid=id);
                CREATE TRIGGER IF NOT EXISTS memories_ai
                    AFTER INSERT ON memories BEGIN
                        INSERT INTO memories_fts(rowid, content) VALUES (new.id, new.content);
                    END;
                CREATE TRIGGER IF NOT EXISTS memories_ad
                    AFTER DELETE ON memories BEGIN
                        INSERT INTO memories_fts(memories_fts, rowid, content)
                            VALUES ('delete', old.id, old.content);
                    END;
                CREATE TRIGGER IF NOT EXISTS memories_au
                    AFTER UPDATE ON memories BEGIN
                        INSERT INTO memories_fts(memories_fts, rowid, content)
                            VALUES ('delete', old.id, old.content);
                        INSERT INTO memories_fts(rowid, content) VALUES (new.id, new.content);
                    END;
            """)

    def store(self, content: str, category: str = "general",
              importance: float = 1.0, memory_type: str = "PATTERN") -> int:
        with self.conn() as c:
            cur = c.execute(
                "INSERT INTO memories (content, category, importance, created_at, memory_type) "
                "VALUES (?,?,?,?,?)",
                (content, category, importance, datetime.now().isoformat(), memory_type)
            )
            return cur.lastrowid

    def search(self, query: str, limit: int = 10) -> list[dict]:
        with self.conn() as c:
            rows = c.execute("""
                SELECT m.id, m.content, m.category, m.importance, m.access_count,
                       m.created_at, m.memory_type,
                       bm25(memories_fts) AS score
                FROM memories_fts
                JOIN memories m ON memories_fts.rowid = m.id
                WHERE memories_fts MATCH ?
                ORDER BY (m.importance * 2.0 + score * -1.0 + m.access_count * 0.1) DESC
                LIMIT ?
            """, (query, limit)).fetchall()
            # Update access counts
            if rows:
                ids = [r["id"] for r in rows]
                c.execute(
                    f"UPDATE memories SET access_count = access_count + 1, "
                    f"last_accessed = ? WHERE id IN ({','.join('?' * len(ids))})",
                    [datetime.now().isoformat()] + ids
                )
        return [dict(r) for r in rows]

    def top_by_importance(self, limit: int = 20) -> list[dict]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT * FROM memories WHERE memory_type != 'ARCHIVE' "
                "ORDER BY importance DESC, access_count DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def set_anchor(self, memory_id: int, level: int = 1):
        levels = {1: "ANCHOR", 2: "ANCHOR_MILESTONE", 3: "ANCHOR_DEFINING"}
        with self.conn() as c:
            c.execute(
                "UPDATE memories SET memory_type=?, importance=importance+? WHERE id=?",
                (levels.get(level, "ANCHOR"), level * 2.0, memory_id)
            )

    def archive(self, memory_id: int):
        with self.conn() as c:
            c.execute(
                "UPDATE memories SET memory_type='ARCHIVE' WHERE id=?", (memory_id,)
            )

    def boost_importance(self, memory_id: int, delta: float = 0.5):
        with self.conn() as c:
            c.execute(
                "UPDATE memories SET importance = importance + ? WHERE id=?",
                (delta, memory_id)
            )
