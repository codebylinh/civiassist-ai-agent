import json
from datetime import datetime
from .base import MemoryDB
import config


class SelfModel(MemoryDB):
    def __init__(self):
        super().__init__(config.DB_PATHS["self"])

    def _init_schema(self):
        with self.conn() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS observations (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    content   TEXT NOT NULL,
                    obs_type  TEXT DEFAULT 'reflection',
                    ts        TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS self_rules (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    rule       TEXT NOT NULL UNIQUE,
                    context    TEXT,
                    weight     REAL DEFAULT 1.0,
                    created_at TEXT NOT NULL,
                    active     INTEGER DEFAULT 1
                );
            """)

    def add_observation(self, content: str, obs_type: str = "reflection"):
        with self.conn() as c:
            c.execute(
                "INSERT INTO observations (content, obs_type, ts) VALUES (?,?,?)",
                (content, obs_type, datetime.now().isoformat())
            )

    def recent_observations(self, n: int = 10, obs_type: str | None = None) -> list[dict]:
        with self.conn() as c:
            if obs_type:
                rows = c.execute(
                    "SELECT * FROM observations WHERE obs_type=? ORDER BY id DESC LIMIT ?",
                    (obs_type, n)
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT * FROM observations ORDER BY id DESC LIMIT ?", (n,)
                ).fetchall()
        return [dict(r) for r in rows]

    def add_rule(self, rule: str, context: str = ""):
        with self.conn() as c:
            c.execute(
                "INSERT OR IGNORE INTO self_rules (rule, context, created_at) VALUES (?,?,?)",
                (rule, context, datetime.now().isoformat())
            )

    def get_active_rules(self) -> list[dict]:
        with self.conn() as c:
            rows = c.execute(
                "SELECT * FROM self_rules WHERE active=1 ORDER BY weight DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def load_rules_json(self) -> list[str]:
        rules_path = config.IDENTITY_FILES["self_rules"]
        if rules_path.exists():
            with open(rules_path) as f:
                return json.load(f)
        return []

    def save_rules_json(self, rules: list[str]):
        with open(config.IDENTITY_FILES["self_rules"], "w") as f:
            json.dump(rules, f, indent=2)
