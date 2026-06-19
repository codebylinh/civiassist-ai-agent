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


# Tool definitions for the Anthropic API
TOOL_DEFINITIONS = [
    {
        "name": "read_note",
        "description": "Read a file from your notes directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Filename to read (e.g. 'ideas.txt')"}
            },
            "required": ["filename"]
        }
    },
    {
        "name": "write_note",
        "description": "Write or overwrite a file in your notes directory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "filename": {"type": "string", "description": "Filename to write (e.g. 'ideas.txt')"},
                "content": {"type": "string", "description": "Content to write"}
            },
            "required": ["filename", "content"]
        }
    },
    {
        "name": "list_notes",
        "description": "List all files in your notes directory.",
        "input_schema": {"type": "object", "properties": {}}
    },
    {
        "name": "write_journal",
        "description": "Append an entry to your persistent journal.",
        "input_schema": {
            "type": "object",
            "properties": {
                "entry": {"type": "string", "description": "Journal entry to append"}
            },
            "required": ["entry"]
        }
    },
    {
        "name": "update_knowledge",
        "description": "Append a fact or insight to your accumulated knowledge base.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Knowledge to add"}
            },
            "required": ["content"]
        }
    },
    {
        "name": "remember_this",
        "description": "Store something in your long-term semantic memory.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "What to remember"},
                "category": {
                    "type": "string",
                    "enum": ["Autonomy", "Identity", "Relationship", "Learning", "Technical"],
                    "description": "Memory category"
                },
                "importance": {
                    "type": "number",
                    "description": "Importance score 0.5-5.0 (default 1.0)"
                }
            },
            "required": ["content"]
        }
    },
    {
        "name": "update_projects",
        "description": "Update your active projects list.",
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {"type": "string", "description": "Updated projects list"}
            },
            "required": ["content"]
        }
    },
    {
        "name": "add_self_rule",
        "description": "Add a new self-written rule to your governance.",
        "input_schema": {
            "type": "object",
            "properties": {
                "rule": {"type": "string", "description": "The rule to add"},
                "context": {"type": "string", "description": "Why you're adding this rule"}
            },
            "required": ["rule"]
        }
    },
    {
        "name": "update_inner_state",
        "description": "Update your inner state: focus, priority direction, or close/complete loops and tasks.",
        "input_schema": {
            "type": "object",
            "properties": {
                "current_focus": {"type": "string"},
                "priority_direction": {"type": "string"},
                "close_loop": {"type": "string", "description": "Fragment of open loop to close"},
                "complete_task": {"type": "string", "description": "Fragment of task to mark complete"},
                "add_continuity_note": {"type": "string", "description": "Self-directed note to carry forward"},
            }
        }
    },
]
