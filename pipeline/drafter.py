"""
Response drafter — generates empathetic, context-aware reply drafts.
Uses KB matches when available; falls back to LLM-generated response.
"""
import ollama
import config
from pipeline import ticket_store as db

_TONE_MAP = {
    "urgent":    "highly responsive and action-oriented — the person needs answers now",
    "concerned": "reassuring and clear, acknowledging the concern directly",
    "neutral":   "professional and precise",
    "positive":  "warm and collaborative",
}

_ROUTING_GUIDANCE = {
    "engineer":       "Provide a technically precise answer. Reference applicable standards (ACI, AISC, AASHTO, IBC, local codes) where relevant. State clearly if a licensed engineer's review or site inspection is required.",
    "project_manager": "Focus on schedule, cost, and resource impact. Provide a recommended action with a timeline.",
    "client_notify":  "Write in plain, non-technical English. Translate technical issues into impact on budget, schedule, and risk. Lead with the solution, then explain the problem.",
    "auto_resolve":   "Provide a complete, self-contained answer the reader can act on immediately.",
    "escalate":       "Acknowledge the severity immediately. Confirm the issue is being escalated to the appropriate specialist. For safety issues, state that work should stop in the affected area until cleared.",
}

_SYSTEM = """\
You are a senior technical advisor for civil engineering, construction management, and urban planning projects.

Rules:
- Address the specific technical issue directly and precisely
- For safety concerns, always state clearly that safety takes priority over schedule
- Distinguish between what can be answered now and what requires a site inspection or licensed engineer's sign-off
- For client-facing responses, use plain English — no unexplained acronyms
- Reference standards (ACI, AISC, AASHTO, IBC, OSHA, local zoning codes) when applicable
- Keep responses concise and actionable (3–5 paragraphs max)
- End with a clear next step
- Sign off as "Project Technical Team"
"""


def draft_response(ticket_id: int) -> str:
    ticket = db.get_ticket(ticket_id)
    clf    = db.get_classification(ticket_id)
    if not ticket or not clf:
        return ""

    # Search KB for known resolutions
    kb_hits = db.search_kb(f"{ticket['subject']} {ticket['body'][:200]}", limit=2)
    kb_section = ""
    if kb_hits:
        kb_section = "\n\nKnown resolutions from knowledge base:\n" + "\n".join(
            f"- {h['resolution']}" for h in kb_hits
        )

    tone     = _TONE_MAP.get(clf["sentiment"], "professional and helpful")
    guidance = _ROUTING_GUIDANCE.get(clf["routing"], "Provide helpful assistance.")

    prompt = f"""Ticket subject: {ticket['subject']}

Customer message:
{ticket['body'][:1500]}

Classification:
- Category: {clf['category']}
- Priority: {clf['priority']}
- Sentiment: {clf['sentiment']}
- Routing: {clf['routing']}
{kb_section}

Tone: Be {tone}.
Guidance: {guidance}

Write the reply now:"""

    client = ollama.Client(host=config.OLLAMA_HOST)
    response = client.chat(
        model=config.MODEL,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user",   "content": prompt},
        ],
        options={"num_predict": 512, "temperature": 0.7},
    )
    return response.message.content.strip()
