"""
Production ticket classifier — zero-shot classification via Ollama.

Outputs a structured classification with confidence and reasoning.
Falls back to rule-based heuristics if the LLM returns malformed JSON.
"""
import json
import re
import ollama
import config

# Valid labels for each dimension
CATEGORIES = ["billing", "technical", "account", "feature_request", "complaint", "general"]
PRIORITIES  = ["critical", "high", "medium", "low"]
SENTIMENTS  = ["angry", "frustrated", "neutral", "satisfied"]
ROUTINGS    = ["auto_resolve", "tier1", "tier2", "escalate"]

_SYSTEM = """\
You are a customer support ticket classifier. Analyze the ticket and return ONLY valid JSON.

Classification dimensions:
- category: billing | technical | account | feature_request | complaint | general
- priority: critical | high | medium | low
  (critical=system down/data loss, high=blocking work, medium=workaround exists, low=minor)
- sentiment: angry | frustrated | neutral | satisfied
- routing: auto_resolve | tier1 | tier2 | escalate
  (auto_resolve=clear FAQ answer, tier1=standard support, tier2=technical, escalate=management)
- confidence: 0.0–1.0
- reasoning: one sentence explaining the classification

Return exactly this JSON structure, no other text:
{
  "category": "...",
  "priority": "...",
  "sentiment": "...",
  "routing": "...",
  "confidence": 0.0,
  "reasoning": "..."
}"""


def _rule_based_fallback(subject: str, body: str) -> dict:
    """Heuristic classifier used when LLM output is unparseable."""
    text = (subject + " " + body).lower()

    category = "general"
    if any(w in text for w in ["payment", "invoice", "charge", "refund", "billing", "subscription", "price"]):
        category = "billing"
    elif any(w in text for w in ["error", "bug", "crash", "broken", "not working", "failed", "500", "exception"]):
        category = "technical"
    elif any(w in text for w in ["login", "password", "account", "access", "permission", "locked"]):
        category = "account"
    elif any(w in text for w in ["feature", "suggestion", "would be nice", "please add", "request"]):
        category = "feature_request"
    elif any(w in text for w in ["terrible", "worst", "unacceptable", "disgusting", "ridiculous", "lawsuit"]):
        category = "complaint"

    priority = "medium"
    if any(w in text for w in ["urgent", "asap", "immediately", "critical", "down", "data loss", "security"]):
        priority = "critical"
    elif any(w in text for w in ["important", "blocking", "can't work", "cannot proceed"]):
        priority = "high"
    elif any(w in text for w in ["minor", "small", "cosmetic", "when you get a chance"]):
        priority = "low"

    sentiment = "neutral"
    if any(w in text for w in ["furious", "outraged", "disgusted", "terrible", "worst", "hate"]):
        sentiment = "angry"
    elif any(w in text for w in ["frustrated", "annoyed", "disappointed", "unhappy"]):
        sentiment = "frustrated"
    elif any(w in text for w in ["thanks", "great", "love", "awesome", "happy"]):
        sentiment = "satisfied"

    routing = "tier1"
    if priority == "critical" or sentiment == "angry":
        routing = "escalate"
    elif category == "technical":
        routing = "tier2"
    elif category in ("general", "account") and priority in ("low", "medium"):
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
    """Clamp all fields to valid label sets."""
    return {
        "category":   data.get("category", "general") if data.get("category") in CATEGORIES else "general",
        "priority":   data.get("priority", "medium")  if data.get("priority")  in PRIORITIES else "medium",
        "sentiment":  data.get("sentiment", "neutral") if data.get("sentiment") in SENTIMENTS else "neutral",
        "routing":    data.get("routing", "tier1")    if data.get("routing")   in ROUTINGS   else "tier1",
        "confidence": max(0.0, min(1.0, float(data.get("confidence", 0.5)))),
        "reasoning":  str(data.get("reasoning", ""))[:500],
    }


def classify(subject: str, body: str) -> dict:
    """
    Classify a support ticket. Returns a validated classification dict.
    Always returns a result — falls back to heuristics on LLM failure.
    """
    prompt = f"Subject: {subject}\n\nBody:\n{body[:1500]}"
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

        # Extract JSON even if wrapped in markdown code fences
        json_match = re.search(r"\{.*\}", raw, re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            return _validate(data)
    except Exception:
        pass

    return _rule_based_fallback(subject, body)


def batch_classify(tickets: list[dict]) -> list[dict]:
    """Classify a list of ticket dicts (each with 'subject', 'body', 'id')."""
    results = []
    for t in tickets:
        clf = classify(t.get("subject", ""), t.get("body", ""))
        clf["ticket_id"] = t["id"]
        results.append(clf)
    return results
