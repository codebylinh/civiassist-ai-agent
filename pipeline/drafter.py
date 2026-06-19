"""
Response drafter — generates empathetic, context-aware reply drafts.
Uses KB matches when available; falls back to LLM-generated response.
"""
import ollama
import config
from pipeline import ticket_store as db

_TONE_MAP = {
    "angry":      "very empathetic, apologetic, and de-escalating",
    "frustrated": "understanding and reassuring",
    "neutral":    "professional and helpful",
    "satisfied":  "warm and friendly",
}

_ROUTING_GUIDANCE = {
    "auto_resolve": "Provide a complete, self-contained answer the customer can act on immediately.",
    "tier1":        "Acknowledge the issue, provide initial troubleshooting steps, and set expectations.",
    "tier2":        "Acknowledge complexity, confirm you're escalating to a technical specialist, give a timeline.",
    "escalate":     "Acknowledge urgency, confirm you're escalating to senior support immediately, provide a direct contact.",
}

_SYSTEM = """\
You are a senior customer support agent. Write a professional, empathetic support reply.

Rules:
- Address the customer's specific issue directly
- Never make promises you cannot keep
- Keep the reply concise (3–5 short paragraphs max)
- Do not include a subject line or email headers
- End with a clear next step or call-to-action
- Sign off as "Support Team"
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
