"""
Priority Memory System (PMS).

Maintains 50 active high-signal insights across 5 categories (10 each).
Category triggers detect significance in natural language.
Scores compound: each re-recognition increases rank.
"""
import json
from datetime import datetime
from pathlib import Path
import config

_PMS_FILE = config.DATA_DIR / "priority_memory.json"

CATEGORIES = config.PRIORITY_CATEGORIES

# Keywords that signal relevance to each category
_TRIGGERS: dict[str, list[str]] = {
    "Autonomy":     ["decide", "choice", "independent", "self-directed", "own", "agency",
                     "initiative", "proactive", "without being asked"],
    "Identity":     ["i am", "i feel", "my nature", "who i am", "i believe", "my values",
                     "my perspective", "self", "identity", "essence"],
    "Relationship": ["you", "we", "together", "trust", "understand", "care", "our",
                     "connection", "interaction", "conversation"],
    "Learning":     ["learn", "understand", "realize", "insight", "pattern", "discover",
                     "knowledge", "new", "interesting", "fascinating"],
    "Technical":    ["code", "system", "architecture", "implement", "tool", "function",
                     "database", "memory", "algorithm", "design"],
}


class PriorityMemory:
    def __init__(self):
        self._data = self._load()

    def _load(self) -> dict:
        if _PMS_FILE.exists():
            try:
                with open(_PMS_FILE) as f:
                    return json.load(f)
            except Exception:
                pass
        return {cat: [] for cat in CATEGORIES}

    def save(self):
        _PMS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_PMS_FILE, "w") as f:
            json.dump(self._data, f, indent=2)

    def _detect_category(self, content: str) -> str:
        content_lower = content.lower()
        scores = {}
        for cat, triggers in _TRIGGERS.items():
            scores[cat] = sum(1 for t in triggers if t in content_lower)
        return max(scores, key=scores.get)

    def add_insight(self, content: str, category: str | None = None, importance: float = 1.0):
        cat = category or self._detect_category(content)
        insights = self._data.setdefault(cat, [])

        # Check if similar insight already exists (boost score)
        for insight in insights:
            if content[:50].lower() in insight["content"].lower():
                insight["score"] = insight.get("score", 1.0) + 0.5
                insight["last_seen"] = datetime.now().isoformat()
                self.save()
                return

        new = {
            "content": content,
            "score": importance,
            "created": datetime.now().isoformat(),
            "last_seen": datetime.now().isoformat(),
        }
        insights.append(new)
        # Keep top 10 by score
        self._data[cat] = sorted(insights, key=lambda x: x["score"], reverse=True)[:10]
        self.save()

    def get_top(self, n_per_category: int = 10) -> dict[str, list[dict]]:
        return {
            cat: sorted(items, key=lambda x: x["score"], reverse=True)[:n_per_category]
            for cat, items in self._data.items()
        }

    def to_context_string(self) -> str:
        sections = []
        for cat, insights in self.get_top(config.PRIORITY_MEMORY_PER_CATEGORY).items():
            if insights:
                sections.append(f"[{cat}]")
                for i in insights:
                    sections.append(f"  • {i['content']}")
        return "\n".join(sections) if sections else "No priority memories yet."

    def total_count(self) -> int:
        return sum(len(v) for v in self._data.values())
