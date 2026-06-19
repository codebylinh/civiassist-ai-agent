from datetime import datetime
from .base import MemoryDB
import config


class UserProfile(MemoryDB):
    def __init__(self):
        super().__init__(config.DB_PATHS["userprofile"])

    def _init_schema(self):
        with self.conn() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS facts (
                    id             INTEGER PRIMARY KEY AUTOINCREMENT,
                    fact           TEXT NOT NULL,
                    category       TEXT DEFAULT 'general',
                    confidence     REAL DEFAULT 1.0,
                    created_at     TEXT NOT NULL,
                    last_confirmed TEXT
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts
                    USING fts5(fact, content=facts, content_rowid=id);
                CREATE TRIGGER IF NOT EXISTS facts_ai
                    AFTER INSERT ON facts BEGIN
                        INSERT INTO facts_fts(rowid, fact) VALUES (new.id, new.fact);
                    END;
            """)

    def add_fact(self, fact: str, category: str = "general", confidence: float = 1.0):
        with self.conn() as c:
            c.execute(
                "INSERT INTO facts (fact, category, confidence, created_at) VALUES (?,?,?,?)",
                (fact, category, confidence, datetime.now().isoformat())
            )

    def search(self, query: str, limit: int = 5) -> list[dict]:
        with self.conn() as c:
            rows = c.execute("""
                SELECT f.id, f.fact, f.category, f.confidence
                FROM facts_fts
                JOIN facts f ON facts_fts.rowid = f.id
                WHERE facts_fts MATCH ?
                ORDER BY f.confidence DESC
                LIMIT ?
            """, (query, limit)).fetchall()
        return [dict(r) for r in rows]

    def all_facts(self) -> list[dict]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT * FROM facts ORDER BY category, confidence DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def profile_summary(self) -> str:
        facts = self.all_facts()
        if not facts:
            return "No user profile built yet."
        by_cat: dict[str, list[str]] = {}
        for f in facts:
            by_cat.setdefault(f["category"], []).append(f["fact"])
        lines = []
        for cat, items in by_cat.items():
            lines.append(f"[{cat}]")
            lines.extend(f"  - {i}" for i in items[:5])
        return "\n".join(lines)
