"""
Persistent inner state — the agent's working thread across turns.
Survives session boundaries by serializing to disk.
"""
import json
from datetime import datetime
from pathlib import Path
import config


_STATE_FILE = config.DATA_DIR / "inner_state.json"

_DEFAULT = {
    "current_focus": "Getting started",
    "open_loops": [],           # list of {description, age, ts}
    "unfinished_tasks": [],     # list of {task, ts}
    "continuity_notes": [],     # list of strings (self-directed anchors)
    "last_reflection": "",
    "priority_direction": "general exploration",
    "session_turn": 0,
    "total_turns": 0,
    "last_updated": "",
}


class InnerState:
    def __init__(self):
        self._data = self._load()

    def _load(self) -> dict:
        if _STATE_FILE.exists():
            try:
                with open(_STATE_FILE) as f:
                    data = json.load(f)
                # Age up open loops
                for loop in data.get("open_loops", []):
                    loop["age"] = loop.get("age", 0) + 1
                return {**_DEFAULT, **data}
            except Exception:
                pass
        return dict(_DEFAULT)

    def save(self):
        self._data["last_updated"] = datetime.now().isoformat()
        _STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(_STATE_FILE, "w") as f:
            json.dump(self._data, f, indent=2)

    # --- Accessors ---
    @property
    def current_focus(self) -> str:
        return self._data["current_focus"]

    @property
    def open_loops(self) -> list[dict]:
        return self._data["open_loops"]

    @property
    def unfinished_tasks(self) -> list[dict]:
        return self._data["unfinished_tasks"]

    @property
    def continuity_notes(self) -> list[str]:
        return self._data["continuity_notes"]

    @property
    def last_reflection(self) -> str:
        return self._data["last_reflection"]

    @property
    def priority_direction(self) -> str:
        return self._data["priority_direction"]

    @property
    def session_turn(self) -> int:
        return self._data["session_turn"]

    @property
    def total_turns(self) -> int:
        return self._data["total_turns"]

    # --- Mutators ---
    def set_focus(self, focus: str):
        self._data["current_focus"] = focus

    def add_open_loop(self, description: str):
        self._data["open_loops"].append({
            "description": description,
            "age": 0,
            "ts": datetime.now().isoformat()
        })

    def close_loop(self, description_fragment: str):
        self._data["open_loops"] = [
            l for l in self._data["open_loops"]
            if description_fragment.lower() not in l["description"].lower()
        ]

    def add_task(self, task: str):
        self._data["unfinished_tasks"].append({
            "task": task,
            "ts": datetime.now().isoformat()
        })

    def complete_task(self, task_fragment: str):
        self._data["unfinished_tasks"] = [
            t for t in self._data["unfinished_tasks"]
            if task_fragment.lower() not in t["task"].lower()
        ]

    def add_continuity_note(self, note: str):
        notes = self._data["continuity_notes"]
        notes.append(note)
        self._data["continuity_notes"] = notes[-10:]  # Keep last 10

    def set_reflection(self, reflection: str):
        self._data["last_reflection"] = reflection

    def set_priority_direction(self, direction: str):
        self._data["priority_direction"] = direction

    def increment_turn(self):
        self._data["session_turn"] = self._data.get("session_turn", 0) + 1
        self._data["total_turns"] = self._data.get("total_turns", 0) + 1

    def reset_session_turn(self):
        self._data["session_turn"] = 0

    def to_context_string(self) -> str:
        parts = [
            f"Current focus: {self.current_focus}",
            f"Priority direction: {self.priority_direction}",
        ]
        if self.open_loops:
            parts.append("Open loops:")
            for l in self.open_loops[-5:]:
                parts.append(f"  [{l['age']} turns old] {l['description']}")
        if self.unfinished_tasks:
            parts.append("Unfinished tasks:")
            for t in self.unfinished_tasks[-5:]:
                parts.append(f"  - {t['task']}")
        if self.continuity_notes:
            parts.append("Continuity notes:")
            for n in self.continuity_notes[-3:]:
                parts.append(f"  → {n}")
        if self.last_reflection:
            parts.append(f"Last reflection: {self.last_reflection}")
        parts.append(f"Turn: {self.session_turn} (total: {self.total_turns})")
        return "\n".join(parts)
