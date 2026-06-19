"""
Triage workflow — the full agent pipeline for a single ticket.

Steps:
  1. Classify
  2. Persist classification
  3. KB lookup
  4. Draft response
  5. Auto-resolve or queue for human review
  6. Log every decision
"""
from pipeline import ticket_store as db
from pipeline.classifier import classify
from pipeline.drafter import draft_response

# Thresholds
AUTO_RESOLVE_CONFIDENCE = 0.80   # min classifier confidence for auto-resolution
AUTO_RESOLVE_ROUTINGS   = {"auto_resolve"}
ESCALATE_ROUTINGS       = {"escalate"}
CRITICAL_PRIORITIES     = {"critical"}


class TriageResult:
    def __init__(self, ticket_id: int, classification: dict,
                 draft: str, action: str, reason: str):
        self.ticket_id      = ticket_id
        self.classification = classification
        self.draft          = draft
        self.action         = action
        self.reason         = reason

    def __repr__(self):
        return (
            f"TriageResult(ticket={self.ticket_id}, "
            f"action={self.action}, "
            f"category={self.classification['category']}, "
            f"priority={self.classification['priority']})"
        )


def run(ticket_id: int) -> TriageResult:
    """
    Run the full triage pipeline on a ticket.
    Ticket must already exist in the store.
    """
    ticket = db.get_ticket(ticket_id)
    if not ticket:
        raise ValueError(f"Ticket {ticket_id} not found")

    # 1. Classify
    clf = classify(ticket["subject"], ticket["body"])
    db.save_classification(
        ticket_id,
        category=clf["category"],
        priority=clf["priority"],
        sentiment=clf["sentiment"],
        routing=clf["routing"],
        confidence=clf["confidence"],
        reasoning=clf["reasoning"],
    )
    db.log_action(ticket_id, "classified",
                  reason=clf["reasoning"],
                  notes=f"confidence={clf['confidence']:.2f}")

    # 2. Draft response
    try:
        draft = draft_response(ticket_id)
    except Exception as e:
        draft = ""
        db.log_action(ticket_id, "draft_failed", reason=str(e))

    if draft:
        db.save_response(ticket_id, draft)
        db.log_action(ticket_id, "draft_created")

    # 3. Decide action
    action, reason = _decide_action(clf, draft)

    # 4. Update ticket status
    db.update_ticket_status(ticket_id, _status_for_action(action))
    db.log_action(ticket_id, action, reason=reason)

    if action == "auto_resolved":
        db.approve_response(ticket_id)

    return TriageResult(ticket_id, clf, draft, action, reason)


def _decide_action(clf: dict, draft: str) -> tuple[str, str]:
    priority = clf["priority"]
    routing  = clf["routing"]
    conf     = clf["confidence"]

    if priority in CRITICAL_PRIORITIES:
        return "escalated", "Critical priority — escalated to senior support immediately."

    if routing in ESCALATE_ROUTINGS:
        return "escalated", f"Classifier routed to escalate ({clf['reasoning']})."

    if (routing in AUTO_RESOLVE_ROUTINGS
            and conf >= AUTO_RESOLVE_CONFIDENCE
            and draft):
        return "auto_resolved", f"High-confidence auto-resolution (conf={conf:.2f})."

    if routing == "tier2":
        return "queued_tier2", "Technical issue — queued for tier-2 specialist."

    return "queued_tier1", "Queued for tier-1 agent review."


def _status_for_action(action: str) -> str:
    return {
        "auto_resolved": "resolved",
        "escalated":     "escalated",
        "queued_tier2":  "in_progress",
        "queued_tier1":  "in_progress",
    }.get(action, "in_progress")


def run_batch(ticket_ids: list[int]) -> list[TriageResult]:
    """Process multiple tickets in sequence."""
    return [run(tid) for tid in ticket_ids]


def ingest_and_triage(subject: str, body: str, source: str = "api") -> TriageResult:
    """Convenience function: create ticket + run full pipeline in one call."""
    ticket_id = db.create_ticket(subject, body, source)
    return run(ticket_id)
