"""
Construction/civil engineering ticket classifier — zero-shot via Ollama.

Classifies queries from engineers, planners, and clients across the
project lifecycle. Falls back to rule-based heuristics on LLM failure.
"""
import json
import re
import ollama
import config

CATEGORIES = [
    "rfi",              # Request for Information / technical clarification
    "site_issue",       # Field condition, weather delay, utility conflict
    "design_review",    # Drawing/spec review, design comment, engineering question
    "permit_approval",  # Permit status, inspection, code compliance
    "budget_cost",      # Cost estimate, change order, invoice, budget query
    "schedule",         # Timeline, delay, milestone, progress update
    "safety",           # Safety incident, hazard, OSHA concern
    "client_inquiry",   # Client asking about progress, photos, status
    "zoning_planning",  # Land use, zoning, environmental, community input
    "submittal",        # Shop drawing, product data, material sample review
    "general",
]

PRIORITIES = ["critical", "high", "medium", "low"]
# critical = safety incident / work stopped / structural concern
# high     = schedule-blocking / permit rejected / major RFI
# medium   = design comment / cost question / routine inquiry
# low      = informational / general question

SENTIMENTS = ["urgent", "concerned", "neutral", "positive"]

ROUTINGS = [
    "engineer",         # Needs structural/civil engineer review
    "project_manager",  # Needs PM decision (schedule, budget, resources)
    "client_notify",    # Client needs to be informed/consulted
    "auto_resolve",     # Standard FAQ — can be answered from knowledge base
    "escalate",         # Safety, structural risk, legal, insurance
]

_SYSTEM = """\
You are a classifier for a construction and civil engineering project management system.
Analyze the incoming query and return ONLY valid JSON — no other text.

Context: queries come from civil engineers, construction engineers, urban planners, and clients.

Classification dimensions:
- category: rfi | site_issue | design_review | permit_approval | budget_cost | schedule | safety | client_inquiry | zoning_planning | submittal | general
- priority: critical | high | medium | low
  (critical=safety incident/work stopped/structural risk, high=schedule-blocking/permit rejected, medium=review needed/cost question, low=informational)
- sentiment: urgent | concerned | neutral | positive
- routing: engineer | project_manager | client_notify | auto_resolve | escalate
  (escalate for any safety, structural, or legal issue)
- confidence: 0.0–1.0
- reasoning: one sentence

Return exactly:
{
  "category": "...",
  "priority": "...",
  "sentiment": "...",
  "routing": "...",
  "confidence": 0.0,
  "reasoning": "..."
}"""


def _rule_based_fallback(subject: str, body: str) -> dict:
    text = (subject + " " + body).lower()

    category = "general"
    if any(w in text for w in ["rfi", "request for information", "clarification", "confirm detail"]):
        category = "rfi"
    elif any(w in text for w in ["safety", "injury", "osha", "hazard", "accident", "ppe", "fall", "excavation collapse"]):
        category = "safety"
    elif any(w in text for w in ["site", "field", "condition", "weather", "delay", "utility", "conflict", "soil"]):
        category = "site_issue"
    elif any(w in text for w in ["drawing", "spec", "design", "review", "comment", "structural", "load", "calculation"]):
        category = "design_review"
    elif any(w in text for w in ["permit", "inspection", "approval", "code", "compliance", "certificate"]):
        category = "permit_approval"
    elif any(w in text for w in ["cost", "budget", "change order", "invoice", "estimate", "price", "overrun"]):
        category = "budget_cost"
    elif any(w in text for w in ["schedule", "timeline", "delay", "milestone", "completion", "progress"]):
        category = "schedule"
    elif any(w in text for w in ["submittal", "shop drawing", "product data", "sample", "material approval"]):
        category = "submittal"
    elif any(w in text for w in ["zoning", "land use", "environmental", "eia", "community", "master plan", "variance"]):
        category = "zoning_planning"
    elif any(w in text for w in ["client", "owner", "update", "status", "photo", "when will", "how is"]):
        category = "client_inquiry"

    priority = "medium"
    if any(w in text for w in ["safety", "injury", "collapse", "emergency", "stopped", "halt", "critical", "structural failure"]):
        priority = "critical"
    elif any(w in text for w in ["urgent", "asap", "blocking", "cannot proceed", "permit rejected", "overdue"]):
        priority = "high"
    elif any(w in text for w in ["minor", "fyi", "when you get a chance", "low priority", "general question"]):
        priority = "low"

    sentiment = "neutral"
    if any(w in text for w in ["urgent", "asap", "immediately", "emergency", "critical"]):
        sentiment = "urgent"
    elif any(w in text for w in ["concerned", "worried", "issue", "problem", "risk", "delay"]):
        sentiment = "concerned"
    elif any(w in text for w in ["great", "good", "happy", "pleased", "excellent"]):
        sentiment = "positive"

    routing = "engineer"
    if category == "safety":
        routing = "escalate"
        priority = "critical"
    elif category in ("budget_cost", "schedule"):
        routing = "project_manager"
    elif category == "client_inquiry":
        routing = "client_notify"
    elif category in ("general",) and priority == "low":
        routing = "auto_resolve"

    return {
        "category": category,
        "priority": priority,
        "sentiment": sentiment,
        "routing": routing,
        "confidence": 0.55,
        "reasoning": "Rule-based fallback classification.",
    }


def _validate(data: dict) -> dict:
    return {
        "category":   data.get("category",  "general")  if data.get("category")  in CATEGORIES else "general",
        "priority":   data.get("priority",  "medium")   if data.get("priority")  in PRIORITIES else "medium",
        "sentiment":  data.get("sentiment", "neutral")  if data.get("sentiment") in SENTIMENTS else "neutral",
        "routing":    data.get("routing",   "engineer") if data.get("routing")   in ROUTINGS   else "engineer",
        "confidence": max(0.0, min(1.0, float(data.get("confidence", 0.5)))),
        "reasoning":  str(data.get("reasoning", ""))[:500],
    }


def classify(subject: str, body: str) -> dict:
    prompt = f"Subject: {subject}\n\nMessage:\n{body[:1500]}"
    client = ollama.Client(host=config.OLLAMA_HOST)

    try:
        response = client.chat(
            model=config.MODEL,
            messages=[
                {"role": "system", "content": _SYSTEM},
                {"role": "user",   "content": prompt},
            ],
            options={"num_predict": 256, "temperature": 0.1},
        )
        raw = response.message.content.strip()
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            return _validate(data)
    except Exception:
        pass

    return _rule_based_fallback(subject, body)


def batch_classify(tickets: list[dict]) -> list[dict]:
    results = []
    for t in tickets:
        clf = classify(t.get("subject", ""), t.get("body", ""))
        clf["ticket_id"] = t["id"]
        results.append(clf)
    return results
