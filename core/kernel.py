"""
LCRK — Cognitive Runtime Kernel.

Event-driven state accumulation (no fixed timers).
Each user message is an event that:
  1. Updates the inner state
  2. Extracts signals for memory routing
  3. Decides if a background cycle (reflection, consolidation) is due
"""
from datetime import datetime, timedelta
from core.inner_state import InnerState
from core.memory.consolidation import ConsolidationMemory
import config


class CognitiveKernel:
    def __init__(self, inner_state: InnerState, lmcs: ConsolidationMemory):
        self.inner_state = inner_state
        self.lmcs = lmcs
        self._session_start = datetime.now()

    def on_user_message(self, content: str):
        """Process incoming user event."""
        self.inner_state.increment_turn()
        self._detect_open_loops(content)
        self._detect_tasks(content)

    def on_agent_response(self, content: str):
        """Process agent output for state signals."""
        self._extract_focus(content)
        self._detect_continuity_notes(content)

    def should_update_red_thread(self) -> bool:
        return self.inner_state.session_turn % config.RED_THREAD_INTERVAL == 0 \
               and self.inner_state.session_turn > 0

    def should_run_daily_reflection(self) -> bool:
        last = self.lmcs.last_run("daily_reflection")
        if last is None:
            return True
        last_ts = datetime.fromisoformat(last["ts"])
        return datetime.now() - last_ts > timedelta(hours=20)

    def should_run_weekly_essence(self) -> bool:
        last = self.lmcs.last_run("weekly_essence")
        if last is None:
            return False  # Run only after at least one daily reflection
        last_ts = datetime.fromisoformat(last["ts"])
        return datetime.now() - last_ts > timedelta(days=6)

    def should_consolidate_patterns(self) -> bool:
        last = self.lmcs.last_run("pattern_consolidation")
        if last is None:
            return self.inner_state.total_turns > 50
        last_ts = datetime.fromisoformat(last["ts"])
        return datetime.now() - last_ts > timedelta(hours=12)

    # --- Private signal extractors ---

    def _detect_open_loops(self, content: str):
        cl = content.lower()
        if any(phrase in cl for phrase in ["what about", "i wonder", "haven't finished",
                                            "we still need", "remind me", "to do"]):
            self.inner_state.add_open_loop(content[:120])

    def _detect_tasks(self, content: str):
        cl = content.lower()
        if any(phrase in cl for phrase in ["please", "can you", "could you", "i need you to",
                                            "help me", "create", "write", "build", "fix"]):
            self.inner_state.add_task(content[:120])

    def _extract_focus(self, content: str):
        # Use first sentence as focus signal
        sentences = [s.strip() for s in content.split(".") if len(s.strip()) > 10]
        if sentences:
            self.inner_state.set_focus(sentences[0][:100])

    def _detect_continuity_notes(self, content: str):
        cl = content.lower()
        if any(phrase in cl for phrase in ["i should remember", "worth noting", "important to note",
                                            "i'll keep in mind", "i want to remember"]):
            self.inner_state.add_continuity_note(content[:120])

    def session_age_minutes(self) -> float:
        return (datetime.now() - self._session_start).total_seconds() / 60
