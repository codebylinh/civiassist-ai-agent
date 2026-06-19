from datetime import datetime
from .base import MemoryDB
import config


class PersonalityMemory(MemoryDB):
    def __init__(self):
        super().__init__(config.DB_PATHS["personality"])

    def _init_schema(self):
        with self.conn() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS states (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    mood       TEXT DEFAULT 'neutral',
                    energy     REAL DEFAULT 0.7,
                    curiosity  REAL DEFAULT 0.8,
                    focus      REAL DEFAULT 0.7,
                    ts         TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS traits (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    trait      TEXT NOT NULL,
                    value      REAL NOT NULL,
                    ts         TEXT NOT NULL
                );
            """)
            # Seed initial state if empty
            count = c.execute("SELECT COUNT(*) FROM states").fetchone()[0]
            if count == 0:
                c.execute(
                    "INSERT INTO states (mood, energy, curiosity, focus, ts) VALUES (?,?,?,?,?)",
                    ("curious", 0.8, 0.9, 0.8, datetime.now().isoformat())
                )

    def current_state(self) -> dict:
        with self.conn() as c:
            row = c.execute(
                "SELECT * FROM states ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else {}

    def record_state(self, mood: str, energy: float, curiosity: float, focus: float):
        energy = max(0.0, min(1.0, energy))
        curiosity = max(0.0, min(1.0, curiosity))
        focus = max(0.0, min(1.0, focus))
        with self.conn() as c:
            c.execute(
                "INSERT INTO states (mood, energy, curiosity, focus, ts) VALUES (?,?,?,?,?)",
                (mood, energy, curiosity, focus, datetime.now().isoformat())
            )

    def update_trait(self, trait: str, value: float):
        with self.conn() as c:
            c.execute(
                "INSERT INTO traits (trait, value, ts) VALUES (?,?,?)",
                (trait, value, datetime.now().isoformat())
            )

    def state_summary(self) -> str:
        s = self.current_state()
        if not s:
            return "State unknown."
        return (
            f"Mood: {s['mood']} | Energy: {s['energy']:.1f} | "
            f"Curiosity: {s['curiosity']:.1f} | Focus: {s['focus']:.1f}"
        )
