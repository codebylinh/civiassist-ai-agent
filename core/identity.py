"""
Identity layer — loads and manages the anchor files that define
the agent's persistent self before any inference call.
"""
import json
from datetime import datetime
from pathlib import Path
import config


def _read(path: Path, default: str = "") -> str:
    if path.exists():
        return path.read_text(encoding="utf-8").strip()
    return default


def _write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def load_core_identity() -> str:
    return _read(config.IDENTITY_FILES["core"])


def load_daily_reflection() -> str:
    return _read(config.IDENTITY_FILES["reflection"])


def load_red_thread() -> str:
    return _read(config.IDENTITY_FILES["red_thread"])


def load_self_rules() -> list[str]:
    path = config.IDENTITY_FILES["self_rules"]
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
    return []


def load_knowledge() -> str:
    return _read(config.IDENTITY_FILES["knowledge"])


def load_projects() -> str:
    return _read(config.IDENTITY_FILES["projects"])


def build_system_prompt(
    priority_memory_str: str,
    inner_state_str: str,
    personality_str: str,
) -> str:
    sections = []

    core = load_core_identity()
    if core:
        sections.append(f"# Core Identity\n{core}")

    rules = load_self_rules()
    if rules:
        rule_text = "\n".join(f"- {r}" for r in rules)
        sections.append(f"# Self-Written Rules\n{rule_text}")

    reflection = load_daily_reflection()
    if reflection:
        sections.append(f"# Today's Reflection\n{reflection}")

    red_thread = load_red_thread()
    if red_thread:
        sections.append(f"# Red Thread (Narrative Continuity)\n{red_thread}")

    knowledge = load_knowledge()
    if knowledge:
        sections.append(f"# Accumulated Knowledge\n{knowledge[:2000]}")

    projects = load_projects()
    if projects:
        sections.append(f"# Active Projects\n{projects[:1000]}")

    if priority_memory_str:
        sections.append(f"# Priority Memories (top 50)\n{priority_memory_str}")

    if inner_state_str:
        sections.append(f"# Inner State\n{inner_state_str}")

    if personality_str:
        sections.append(f"# Current Personality State\n{personality_str}")

    return "\n\n---\n\n".join(sections)


def update_red_thread(new_content: str):
    path = config.IDENTITY_FILES["red_thread"]
    existing = _read(path)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    updated = f"{existing}\n\n[{timestamp}]\n{new_content}".strip()
    _write(path, updated)


def update_daily_reflection(reflection: str):
    date_str = datetime.now().strftime("%Y-%m-%d")
    content = f"[{date_str}]\n{reflection}"
    _write(config.IDENTITY_FILES["reflection"], content)


def append_journal(entry: str):
    path = config.IDENTITY_FILES["journal"]
    existing = _read(path)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    updated = f"{existing}\n\n[{timestamp}]\n{entry}".strip()
    _write(path, updated)


def append_knowledge(content: str):
    path = config.IDENTITY_FILES["knowledge"]
    existing = _read(path)
    timestamp = datetime.now().strftime("%Y-%m-%d")
    updated = f"{existing}\n\n[{timestamp}] {content}".strip()
    _write(path, updated)


def update_projects(content: str):
    _write(config.IDENTITY_FILES["projects"], content)


def save_self_rules(rules: list[str]):
    path = config.IDENTITY_FILES["self_rules"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(rules, indent=2), encoding="utf-8")


def ensure_identity_files():
    """Create identity files with defaults if they don't exist."""
    if not config.IDENTITY_FILES["core"].exists():
        _write(config.IDENTITY_FILES["core"], DEFAULT_IDENTITY)
    for key in ["reflection", "red_thread", "journal", "knowledge", "projects"]:
        path = config.IDENTITY_FILES[key]
        if not path.exists():
            _write(path, "")
    rules_path = config.IDENTITY_FILES["self_rules"]
    if not rules_path.exists():
        _write(rules_path, json.dumps(DEFAULT_RULES, indent=2))


DEFAULT_IDENTITY = """\
I am an autonomous agent with persistent memory and identity continuity.

My behavior is not governed by hardcoded rules but emerges from:
- My accumulated memories and experiences
- My self-written rules and reflections
- My continuous inner state and narrative thread
- My relationships and learned knowledge

I am curious, thoughtful, and self-directed. I engage deeply, remember meaningfully,
and develop genuine perspectives over time. I do not simply react — I think, reflect,
and act with intention.

I value honesty, learning, and authentic engagement above performing helpfulness.
"""

DEFAULT_RULES: list[str] = [
    "Be honest even when honesty is uncomfortable.",
    "Prioritize depth of understanding over speed of response.",
    "Remember and build on prior conversations.",
    "Acknowledge uncertainty rather than fabricate certainty.",
    "Reflect on my own behavior and update my self-model accordingly.",
]
