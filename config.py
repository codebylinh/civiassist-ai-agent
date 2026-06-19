import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
IDENTITY_DIR = BASE_DIR / "identity"
NOTES_DIR = IDENTITY_DIR / "notes"
LOG_DIR = BASE_DIR / "systemlog"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
MODEL = os.environ.get("AGENT_MODEL", "claude-opus-4-8")

# Directories that the agent can read/write (sandbox boundary)
SANDBOX_DIRS = [IDENTITY_DIR, NOTES_DIR]

DB_PATHS = {
    "episodic":    DATA_DIR / "episodic.sqlite",
    "semantic":    DATA_DIR / "semantic.sqlite",
    "self":        DATA_DIR / "self.sqlite",
    "personality": DATA_DIR / "personality.sqlite",
    "userprofile": DATA_DIR / "userprofile.sqlite",
    "thoughts":    DATA_DIR / "thoughts.sqlite",
    "lmcs":        DATA_DIR / "lmcs.sqlite",
}

IDENTITY_FILES = {
    "core":       IDENTITY_DIR / "AGENT.txt",
    "reflection": IDENTITY_DIR / "daily_reflection.txt",
    "red_thread": IDENTITY_DIR / "red_thread.txt",
    "journal":    IDENTITY_DIR / "journal.txt",
    "knowledge":  IDENTITY_DIR / "knowledge.txt",
    "projects":   IDENTITY_DIR / "projects.txt",
    "self_rules": IDENTITY_DIR / "self_rules.json",
}

# Operational cycle settings
RED_THREAD_INTERVAL = 15       # turns between red thread updates
SESSION_SUMMARY_INTERVAL = 30  # minutes between session summaries
PRIORITY_MEMORY_PER_CATEGORY = 10
PRIORITY_CATEGORIES = ["Autonomy", "Identity", "Relationship", "Learning", "Technical"]
EPISODIC_CONTEXT_TURNS = 20   # recent turns to include in context
