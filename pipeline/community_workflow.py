"""
Community safety workflow — classifies a resident complaint, drafts
responses to both the resident and the construction team, and decides
the escalation path.
"""
import json
import re
import ollama
import config
from pipeline import community as db

# --- Classifier ---

_CLASSIFY_SYSTEM = """\
You are a community safety officer assessing complaints from residents near a construction zone.
Classify the complaint and return ONLY valid JSON.

Categories:
  noise | dust_air | debris_hazard | access_blocked | vibration_damage |
  traffic_disruption | structural_concern | water_flooding | emergency | general

Severity:
  emergency = immediate danger to life or property (respond now, may need 911)
  high      = safety risk, site must respond within 1 hour
  medium    = legitimate complaint, respond within 24 hours
  low       = inconvenience, respond within 48 hours

Public risk (what is at risk for the public):
  Write one sentence describing the specific risk to residents/pedestrians.

Routing:
  emergency_services  = call 911 and site superintendent immediately
  site_superintendent = site must take action within 1 hour
  project_manager     = needs coordination, respond within 24 hours
  city_inspector      = code/ordinance violation — city should be notified
  auto_acknowledge    = standard complaint — acknowledge and provide info

Return exactly:
{
  "category": "...",
  "severity": "...",
  "public_risk": "...",
  "routing": "...",
  "confidence": 0.0,
  "reasoning": "..."
}"""

_RESIDENT_RESPONSE_SYSTEM = """\
You are a community liaison writing to a resident who has filed a safety complaint
about nearby construction. Be:
- Empathetic and respectful — this is their home and neighbourhood
- Specific about what action is being taken and when
- Honest about timelines — never overpromise
- Clear about who to contact for follow-up or emergencies

For emergency or high-severity complaints: acknowledge urgency in the first sentence,
state the immediate action being taken, and provide an emergency contact number.

Keep the response to 3–4 short paragraphs. Sign off as "Community Safety Team".
Do not use construction jargon without explaining it."""

_CONSTRUCTION_MEMO_SYSTEM = """\
You are writing an internal action memo to the construction site superintendent
about a resident complaint that requires a site response.
Be direct and operational. State:
1. The complaint and its severity
2. The specific action required on site
3. The deadline for action and response
4. Documentation required (photos, logs, measurements)
Sign off as "Community Safety Coordinator"."""


def _llm(system: str, prompt: str, max_tokens: int = 400) -> str:
    client = ollama.Client(host=config.OLLAMA_HOST)
    response = client.chat(
        model=config.MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user",   "content": prompt},
        ],
        options={"num_predict": max_tokens, "temperature": 0.2},
    )
    return response.message.content.strip()


def _rule_fallback(description: str) -> dict:
    text = description.lower()
    category = "general"
    if any(w in text for w in ["noise", "loud", "banging", "drilling", "night", "11pm", "midnight"]):
        category = "noise"
    elif any(w in text for w in ["dust", "air", "particulate", "breathing", "asthma"]):
        category = "dust_air"
    elif any(w in text for w in ["debris", "falling", "rock", "material", "footpath", "sidewalk blocked by material"]):
        category = "debris_hazard"
    elif any(w in text for w in ["blocked", "cannot access", "driveway", "road closed", "no warning"]):
        category = "access_blocked"
    elif any(w in text for w in ["crack", "vibration", "shaking", "damage", "wall crack"]):
        category = "vibration_damage"
    elif any(w in text for w in ["traffic", "signal", "lane", "detour", "no sign"]):
        category = "traffic_disruption"
    elif any(w in text for w in ["structural", "collapse", "leaning", "unstable wall", "falling wall"]):
        category = "structural_concern"
    elif any(w in text for w in ["water", "mud", "flood", "runoff", "sewage"]):
        category = "water_flooding"
    elif any(w in text for w in ["emergency", "injury", "trapped", "fire", "gas leak", "collapse"]):
        category = "emergency"

    severity = "medium"
    if category == "emergency" or any(w in text for w in ["injury", "fire", "gas", "collapse", "trapped"]):
        severity = "emergency"
    elif any(w in text for w in ["unsafe", "danger", "risk", "child", "school", "hospital"]):
        severity = "high"
    elif any(w in text for w in ["minor", "small", "slight", "just letting you know"]):
        severity = "low"

    routing = "project_manager"
    if severity == "emergency":
        routing = "emergency_services"
    elif severity == "high":
        routing = "site_superintendent"
    elif category in ("noise",) and severity == "low":
        routing = "auto_acknowledge"

    return {
        "category":    category,
        "severity":    severity,
        "public_risk": "Risk to nearby residents and pedestrians.",
        "routing":     routing,
        "confidence":  0.55,
        "reasoning":   "Rule-based fallback.",
    }


def classify_complaint(description: str, location: str = "") -> dict:
    prompt = f"Location: {location or 'not specified'}\n\nComplaint:\n{description[:1500]}"
    try:
        raw = _llm(_CLASSIFY_SYSTEM, prompt, max_tokens=256)
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
            valid_cats = ["noise","dust_air","debris_hazard","access_blocked","vibration_damage",
                          "traffic_disruption","structural_concern","water_flooding","emergency","general"]
            valid_sevs = ["emergency","high","medium","low"]
            valid_rout = ["emergency_services","site_superintendent","project_manager",
                          "city_inspector","auto_acknowledge"]
            return {
                "category":    data.get("category",    "general")            if data.get("category")   in valid_cats else "general",
                "severity":    data.get("severity",    "medium")             if data.get("severity")   in valid_sevs else "medium",
                "public_risk": str(data.get("public_risk", ""))[:300],
                "routing":     data.get("routing",     "project_manager")    if data.get("routing")    in valid_rout else "project_manager",
                "confidence":  max(0.0, min(1.0, float(data.get("confidence", 0.5)))),
                "reasoning":   str(data.get("reasoning", ""))[:300],
            }
    except Exception:
        pass
    return _rule_fallback(description)


def draft_resident_response(complaint_id: int) -> str:
    complaint = db.get_complaint(complaint_id)
    clf_row   = None
    with db._conn() as c:
        row = c.execute(
            "SELECT * FROM complaint_classifications WHERE complaint_id=?", (complaint_id,)
        ).fetchone()
        if row:
            clf_row = dict(row)

    if not complaint:
        return ""

    severity = clf_row["severity"] if clf_row else "medium"
    routing  = clf_row["routing"]  if clf_row else "project_manager"
    risk     = clf_row["public_risk"] if clf_row else ""

    emergency_line = ""
    if severity == "emergency":
        emergency_line = "\nIMPORTANT: This is classified as an EMERGENCY. The response must begin with immediate action steps and an emergency contact number (e.g. 24-hour site emergency line)."
    elif severity == "high":
        emergency_line = "\nThis is high severity — acknowledge that a response team is being dispatched within 1 hour."

    prompt = f"""Resident complaint reference: #{complaint_id}
Location: {complaint.get('location') or 'not specified'}
Reported by: {complaint.get('reported_by') or 'anonymous'}

Complaint:
{complaint['description']}

Classification:
- Category: {clf_row['category'] if clf_row else 'general'}
- Severity: {severity}
- Public risk identified: {risk}
- Routing: {routing}
{emergency_line}

Write the response to the resident now:"""

    return _llm(_RESIDENT_RESPONSE_SYSTEM, prompt, max_tokens=450)


def draft_construction_memo(complaint_id: int) -> str:
    complaint = db.get_complaint(complaint_id)
    clf_row   = None
    with db._conn() as c:
        row = c.execute(
            "SELECT * FROM complaint_classifications WHERE complaint_id=?", (complaint_id,)
        ).fetchone()
        if row:
            clf_row = dict(row)

    if not complaint:
        return ""

    severity = clf_row["severity"] if clf_row else "medium"
    deadline = {
        "emergency": "IMMEDIATELY — within 15 minutes",
        "high":      "Within 1 hour",
        "medium":    "Within 24 hours",
        "low":       "Within 48 hours",
    }.get(severity, "Within 24 hours")

    prompt = f"""Complaint #{complaint_id}
Location: {complaint.get('location') or 'not specified'}
Category: {clf_row['category'] if clf_row else 'general'}
Severity: {severity}
Response deadline: {deadline}
Public risk: {clf_row['public_risk'] if clf_row else 'unknown'}

Complaint text:
{complaint['description']}

Write the action memo to the site superintendent:"""

    return _llm(_CONSTRUCTION_MEMO_SYSTEM, prompt, max_tokens=350)


class ComplaintResult:
    def __init__(self, complaint_id: int, classification: dict,
                 resident_response: str, construction_memo: str,
                 action: str, deadline: str):
        self.complaint_id       = complaint_id
        self.classification     = classification
        self.resident_response  = resident_response
        self.construction_memo  = construction_memo
        self.action             = action
        self.deadline           = deadline


def process_complaint(complaint_id: int) -> ComplaintResult:
    complaint = db.get_complaint(complaint_id)
    if not complaint:
        raise ValueError(f"Complaint #{complaint_id} not found")

    # 1. Classify
    clf = classify_complaint(complaint["description"], complaint.get("location", ""))
    db.save_complaint_classification(
        complaint_id,
        category=clf["category"],
        severity=clf["severity"],
        public_risk=clf["public_risk"],
        routing=clf["routing"],
        confidence=clf["confidence"],
        reasoning=clf["reasoning"],
    )

    # 2. Draft responses
    resident_response = draft_resident_response(complaint_id)
    construction_memo = ""
    if clf["routing"] != "auto_acknowledge":
        construction_memo = draft_construction_memo(complaint_id)

    # 3. Safety alert for emergency/high
    if clf["severity"] in ("emergency", "high"):
        db.create_safety_alert(
            description=complaint["description"][:200],
            severity=clf["severity"],
            affected_area=complaint.get("location", ""),
        )

    # 4. Determine action and deadline
    deadline_map = {
        "emergency": "IMMEDIATELY — 15 minutes",
        "high":      "1 hour",
        "medium":    "24 hours",
        "low":       "48 hours",
    }
    action_map = {
        "emergency_services":   "ESCALATED — Emergency services + superintendent alerted",
        "site_superintendent":  "DISPATCHED — Site superintendent notified for immediate action",
        "project_manager":      "ASSIGNED — Project manager notified",
        "city_inspector":       "REPORTED — City inspector notified of potential violation",
        "auto_acknowledge":     "ACKNOWLEDGED — Standard response sent to resident",
    }

    action   = action_map.get(clf["routing"], "ASSIGNED")
    deadline = deadline_map.get(clf["severity"], "24 hours")

    return ComplaintResult(
        complaint_id, clf,
        resident_response, construction_memo,
        action, deadline
    )


def ingest_and_process(description: str, location: str = "",
                        reported_by: str = "", contact: str = "") -> ComplaintResult:
    cid = db.file_complaint(description, location, reported_by, contact)
    return process_complaint(cid)
