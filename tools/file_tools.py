"""
Sandboxed file tools — the agent can only read/write within SANDBOX_DIRS.
"""
from pathlib import Path
import config


def _safe_path(filename: str, base_dir: Path | None = None) -> Path | None:
    """Resolve path and verify it stays inside the sandbox."""
    base = base_dir or config.NOTES_DIR
    try:
        resolved = (base / filename).resolve()
        for sandbox in config.SANDBOX_DIRS:
            if resolved.is_relative_to(sandbox.resolve()):
                return resolved
    except Exception:
        pass
    return None


def read_note(filename: str) -> str:
    path = _safe_path(filename)
    if path and path.exists():
        return path.read_text(encoding="utf-8")
    return f"[File not found: {filename}]"


def write_note(filename: str, content: str) -> str:
    path = _safe_path(filename)
    if path is None:
        return "[Error: path outside sandbox]"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return f"[Written: {filename}]"


def list_notes() -> list[str]:
    return [f.name for f in config.NOTES_DIR.glob("*") if f.is_file()]


def read_identity_file(name: str) -> str:
    """Read one of the named identity files by key."""
    path = config.IDENTITY_FILES.get(name)
    if path and path.exists():
        return path.read_text(encoding="utf-8")
    return f"[Identity file not found: {name}]"


# Tool definitions in OpenAI/Ollama function-calling format
def _fn(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required or [],
            },
        },
    }


TOOL_DEFINITIONS = [
    _fn("read_note", "Read a file from your notes directory.",
        {"filename": {"type": "string", "description": "Filename to read (e.g. 'ideas.txt')"}},
        ["filename"]),

    _fn("write_note", "Write or overwrite a file in your notes directory.",
        {
            "filename": {"type": "string", "description": "Filename to write"},
            "content":  {"type": "string", "description": "Content to write"},
        },
        ["filename", "content"]),

    _fn("list_notes", "List all files in your notes directory.", {}),

    _fn("write_journal", "Append an entry to your persistent journal.",
        {"entry": {"type": "string", "description": "Journal entry to append"}},
        ["entry"]),

    _fn("update_knowledge", "Append a fact or insight to your accumulated knowledge base.",
        {"content": {"type": "string", "description": "Knowledge to add"}},
        ["content"]),

    _fn("remember_this", "Store something in your long-term semantic memory.",
        {
            "content":    {"type": "string", "description": "What to remember"},
            "category":   {"type": "string", "description": "Autonomy | Identity | Relationship | Learning | Technical"},
            "importance": {"type": "number", "description": "Importance score 0.5–5.0 (default 1.0)"},
        },
        ["content"]),

    _fn("update_projects", "Update your active projects list.",
        {"content": {"type": "string", "description": "Updated projects list"}},
        ["content"]),

    _fn("add_self_rule", "Add a new self-written rule to your governance.",
        {
            "rule":    {"type": "string", "description": "The rule to add"},
            "context": {"type": "string", "description": "Why you are adding this rule"},
        },
        ["rule"]),

    _fn("update_inner_state",
        "Update your inner state: focus, priority direction, or close/complete open loops and tasks.",
        {
            "current_focus":       {"type": "string"},
            "priority_direction":  {"type": "string"},
            "close_loop":          {"type": "string", "description": "Fragment of open loop to close"},
            "complete_task":       {"type": "string", "description": "Fragment of task to mark complete"},
            "add_continuity_note": {"type": "string", "description": "Self-directed note to carry forward"},
        }),
]
