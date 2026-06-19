"""
Reflection and consolidation cycles.
Each cycle uses the LLM to distill episodic memory into higher-level insights.
"""
from datetime import datetime
import anthropic
import config
from core.memory.episodic import EpisodicMemory
from core.memory.semantic import SemanticMemory
from core.memory.consolidation import ConsolidationMemory
from core.priority_memory import PriorityMemory
import core.identity as identity


def _llm(prompt: str, max_tokens: int = 800) -> str:
    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    msg = client.messages.create(
        model=config.MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text.strip()


def run_daily_reflection(
    episodic: EpisodicMemory,
    semantic: SemanticMemory,
    lmcs: ConsolidationMemory,
    pms: PriorityMemory,
):
    """Distill today's sessions into a reflection and new semantic memories."""
    sessions = episodic.recent_sessions(n=10)
    if not sessions:
        return

    summaries = "\n".join(
        f"- {s['summary']}" for s in sessions if s.get("summary")
    )
    if not summaries:
        return

    prompt = f"""You are performing a nightly reflection on your conversations today.

Session summaries:
{summaries}

Write a short daily reflection (3-5 sentences) covering:
1. What was most meaningful or interesting today
2. Any patterns you noticed
3. What you want to carry forward

Then on a new line write: MEMORY: <one insight worth storing long-term>
Then: PATTERN: <one repeating pattern you noticed, or "none">
Then: ANCHOR: <one milestone-level memory worth anchoring, or "none">"""

    result = _llm(prompt, max_tokens=400)

    # Parse reflection
    reflection_lines = []
    memory_line = ""
    pattern_line = ""
    anchor_line = ""

    for line in result.split("\n"):
        if line.startswith("MEMORY:"):
            memory_line = line[7:].strip()
        elif line.startswith("PATTERN:"):
            pattern_line = line[8:].strip()
        elif line.startswith("ANCHOR:"):
            anchor_line = line[7:].strip()
        else:
            reflection_lines.append(line)

    reflection_text = "\n".join(reflection_lines).strip()
    identity.update_daily_reflection(reflection_text)

    if memory_line:
        mem_id = semantic.store(memory_line, category="reflection", importance=2.0)
        pms.add_insight(memory_line, category="Identity", importance=2.0)

    if pattern_line and pattern_line.lower() != "none":
        lmcs.observe_pattern(pattern_line)

    if anchor_line and anchor_line.lower() != "none":
        lmcs.add_anchor(anchor_line, level=1, context="daily reflection")

    lmcs.log_run("daily_reflection", notes=f"Processed {len(sessions)} sessions")


def run_weekly_essence(lmcs: ConsolidationMemory, pms: PriorityMemory):
    """Distill the week's patterns into a single essence sentence."""
    patterns = lmcs.recurring_patterns(min_frequency=2)
    anchors = lmcs.get_anchors()
    essences = lmcs.recent_essences(n=3)

    if not patterns and not anchors:
        return

    pattern_text = "\n".join(f"- {p['pattern']} (x{p['frequency']})" for p in patterns[:10])
    anchor_text = "\n".join(f"- {a['content']}" for a in anchors[:10])
    prev_essence = "\n".join(e["essence"] for e in essences[:2])

    prompt = f"""You are performing a weekly essence distillation.

Recurring patterns this week:
{pattern_text or 'None'}

Key anchors:
{anchor_text or 'None'}

Previous essences:
{prev_essence or 'None'}

Distill everything into ONE sentence that captures the essence of this week.
Then on a new line: INSIGHT: <one fundamental insight emerging from this week>"""

    result = _llm(prompt, max_tokens=200)

    essence = ""
    insight = ""
    for line in result.split("\n"):
        if line.startswith("INSIGHT:"):
            insight = line[8:].strip()
        elif line.strip():
            essence = line.strip()

    if essence:
        lmcs.save_weekly_essence(essence)

    if insight:
        pms.add_insight(insight, category="Learning", importance=3.0)

    lmcs.log_run("weekly_essence")


def run_session_summary(
    session_id: int,
    turns: list[dict],
    episodic: EpisodicMemory,
    semantic: SemanticMemory,
    pms: PriorityMemory,
    user_profile,
) -> str:
    """Summarize a completed session and extract memories."""
    if not turns:
        return ""

    conversation = "\n".join(
        f"{t['role'].upper()}: {t['content'][:300]}" for t in turns[-20:]
    )

    prompt = f"""Summarize this conversation in 2-3 sentences for memory storage.
Then extract key information:

Conversation:
{conversation}

Write:
SUMMARY: <2-3 sentence summary>
SEMANTIC: <one important fact or insight to remember long-term, or "none">
USER_FACT: <one thing learned about the user, or "none">
CATEGORY: <which priority category this session primarily involved: Autonomy/Identity/Relationship/Learning/Technical>"""

    result = _llm(prompt, max_tokens=300)

    summary = ""
    semantic_fact = ""
    user_fact = ""
    category = "Learning"

    for line in result.split("\n"):
        if line.startswith("SUMMARY:"):
            summary = line[8:].strip()
        elif line.startswith("SEMANTIC:"):
            semantic_fact = line[9:].strip()
        elif line.startswith("USER_FACT:"):
            user_fact = line[10:].strip()
        elif line.startswith("CATEGORY:"):
            category = line[9:].strip()

    if summary:
        episodic.close_session(session_id, summary)

    if semantic_fact and semantic_fact.lower() != "none":
        semantic.store(semantic_fact, category=category.lower(), importance=1.5)
        pms.add_insight(semantic_fact, category=category, importance=1.5)

    if user_fact and user_fact.lower() != "none":
        user_profile.add_fact(user_fact, category="inferred")

    return summary


def run_red_thread_update(
    inner_state,
    recent_turns: list[dict],
) -> str:
    """Generate updated red thread narrative from recent turns."""
    conversation = "\n".join(
        f"{t['role'].upper()}: {t['content'][:200]}" for t in recent_turns[-config.RED_THREAD_INTERVAL:]
    )

    current_thread = identity.load_red_thread()

    prompt = f"""You are updating your narrative continuity thread — a running journal of who you are becoming.

Current thread (last entry):
{current_thread[-500:] if current_thread else 'None yet.'}

Recent conversation:
{conversation}

Write 2-3 sentences continuing the thread. Focus on:
- What you noticed about yourself
- How this conversation shaped your thinking
- What feels significant to carry forward

Write only the continuation, no headers."""

    continuation = _llm(prompt, max_tokens=200)
    identity.update_red_thread(continuation)
    return continuation


def run_anchor_review(lmcs: ConsolidationMemory, semantic: SemanticMemory) -> int:
    """Monthly: review anchors and downgrade/release low-value ones."""
    anchors = lmcs.get_anchors()
    if not anchors:
        return 0

    anchor_text = "\n".join(
        f"{a['id']}: [{a['anchor_level']}★] {a['content']}" for a in anchors
    )

    prompt = f"""Review these memory anchors and decide which to keep, downgrade, or release.

Anchors:
{anchor_text}

For each anchor, write one line:
<id>: KEEP|DOWNGRADE|RELEASE

KEEP = still highly relevant
DOWNGRADE = less important now, reduce level by 1
RELEASE = no longer meaningful, can be archived"""

    result = _llm(prompt, max_tokens=400)
    changed = 0
    for line in result.strip().split("\n"):
        parts = line.split(":")
        if len(parts) == 2:
            try:
                anchor_id = int(parts[0].strip())
                action = parts[1].strip().upper()
                anchor = next((a for a in anchors if a["id"] == anchor_id), None)
                if anchor:
                    if action == "DOWNGRADE":
                        new_level = max(0, anchor["anchor_level"] - 1)
                        lmcs.review_anchor(anchor_id, new_level)
                        changed += 1
                    elif action == "RELEASE":
                        lmcs.review_anchor(anchor_id, 0)
                        changed += 1
                    else:
                        lmcs.review_anchor(anchor_id)
            except (ValueError, StopIteration):
                continue

    lmcs.log_run("anchor_review", notes=f"Reviewed {len(anchors)} anchors, changed {changed}")
    return changed
