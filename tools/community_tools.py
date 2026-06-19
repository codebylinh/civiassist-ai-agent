"""
Community safety tools available to the agent.
Allows the agent to file complaints, check safety status,
draft notifications, and look up resolution status on behalf of
residents or the construction team.
"""
import pipeline.community as db
from pipeline.community_workflow import ingest_and_process, process_complaint

COMMUNITY_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "file_resident_complaint",
            "description": (
                "File a safety or nuisance complaint from a resident about nearby "
                "construction. Automatically classifies severity and routes to the "
                "right responder."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "description":   {"type": "string", "description": "Full description of the issue"},
                    "location":      {"type": "string", "description": "Street address or landmark near the issue"},
                    "reported_by":   {"type": "string", "description": "Resident name (optional)"},
                    "contact":       {"type": "string", "description": "Phone or email for follow-up (optional)"},
                },
                "required": ["description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_complaint_status",
            "description": "Look up the status and resolution of a previously filed complaint.",
            "parameters": {
                "type": "object",
                "properties": {
                    "complaint_id": {"type": "integer", "description": "Complaint reference number"},
                },
                "required": ["complaint_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_open_complaints",
            "description": "List all open resident complaints, ordered by severity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "severity": {"type": "string", "description": "Filter by severity: emergency | high | medium | low"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_active_safety_alerts",
            "description": "Get all active public safety alerts near construction zones.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_safety_alert",
            "description": "Create a public safety alert for a hazard affecting residents near the site.",
            "parameters": {
                "type": "object",
                "properties": {
                    "description":   {"type": "string"},
                    "severity":      {"type": "string", "description": "emergency | high | medium | low"},
                    "project_name":  {"type": "string"},
                    "affected_area": {"type": "string", "description": "Streets or area affected"},
                },
                "required": ["description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "send_resident_notification",
            "description": (
                "Draft and log a notification from the construction team to nearby "
                "residents — e.g. advance notice of noisy work, road closures, or "
                "resolution of a previously reported issue."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "title":         {"type": "string", "description": "Short notification title"},
                    "message":       {"type": "string", "description": "Full notification message"},
                    "project_name":  {"type": "string"},
                    "urgency":       {"type": "string", "description": "urgent | normal | informational"},
                    "target_area":   {"type": "string", "description": "Affected streets or radius"},
                },
                "required": ["title", "message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "resolve_complaint",
            "description": "Mark a complaint as resolved, recording the action taken and notifying the resident.",
            "parameters": {
                "type": "object",
                "properties": {
                    "complaint_id":    {"type": "integer"},
                    "action_taken":    {"type": "string", "description": "What was done to resolve the issue"},
                    "resolved_by":     {"type": "string"},
                    "resident_notice": {"type": "string", "description": "Message to send the resident"},
                },
                "required": ["complaint_id", "action_taken"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "community_safety_summary",
            "description": "Get an overview of current community safety status: open complaints, active alerts, recent notifications.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def dispatch_community_tool(tool_name: str, tool_input: dict) -> str:
    db.init_db()

    if tool_name == "file_resident_complaint":
        result = ingest_and_process(
            description=tool_input["description"],
            location=tool_input.get("location", ""),
            reported_by=tool_input.get("reported_by", ""),
            contact=tool_input.get("contact", ""),
        )
        clf = result.classification
        lines = [
            f"[Complaint #{result.complaint_id} filed]",
            f"Severity: {clf['severity'].upper()}  |  Category: {clf['category']}",
            f"Action: {result.action}",
            f"Response deadline: {result.deadline}",
            f"Public risk: {clf['public_risk']}",
        ]
        if clf["severity"] == "emergency":
            lines.insert(0, "⚠ EMERGENCY — Emergency services and site superintendent have been alerted.")
        if result.resident_response:
            lines += ["", "--- Resident response drafted ---", result.resident_response]
        if result.construction_memo:
            lines += ["", "--- Site action memo ---", result.construction_memo]
        return "\n".join(lines)

    elif tool_name == "check_complaint_status":
        cid = tool_input["complaint_id"]
        complaint  = db.get_complaint(cid)
        resolution = db.get_resolution(cid)
        if not complaint:
            return f"Complaint #{cid} not found."
        lines = [
            f"Complaint #{cid} — Status: {complaint['status'].upper()}",
            f"Filed: {complaint['created_at'][:16]}",
            f"Issue: {complaint['description'][:200]}",
        ]
        if resolution:
            lines += [
                f"Resolved: {resolution['created_at'][:16]}",
                f"Action taken: {resolution['action_taken']}",
            ]
            if resolution.get("resident_notice"):
                lines.append(f"Notice to resident: {resolution['resident_notice']}")
        return "\n".join(lines)

    elif tool_name == "list_open_complaints":
        complaints = db.list_complaints(
            status="open",
            severity=tool_input.get("severity"),
        )
        if not complaints:
            return "No open complaints."
        lines = [f"Open complaints ({len(complaints)}):"]
        for c in complaints:
            sev = c.get("severity") or "unclassified"
            lines.append(
                f"  #{c['id']} [{sev.upper()}] {c['description'][:70]}  ({c['created_at'][:10]})"
            )
        return "\n".join(lines)

    elif tool_name == "get_active_safety_alerts":
        alerts = db.active_safety_alerts()
        if not alerts:
            return "No active safety alerts."
        lines = [f"Active safety alerts ({len(alerts)}):"]
        for a in alerts:
            lines.append(
                f"  [{a['severity'].upper()}] {a['description'][:80]}"
                + (f" — {a['affected_area']}" if a.get("affected_area") else "")
            )
        return "\n".join(lines)

    elif tool_name == "create_safety_alert":
        aid = db.create_safety_alert(
            description=tool_input["description"],
            severity=tool_input.get("severity", "high"),
            project_name=tool_input.get("project_name", ""),
            affected_area=tool_input.get("affected_area", ""),
        )
        return f"[Safety alert #{aid} created — severity: {tool_input.get('severity', 'high').upper()}]"

    elif tool_name == "send_resident_notification":
        nid = db.create_notification(
            title=tool_input["title"],
            message=tool_input["message"],
            project_name=tool_input.get("project_name", ""),
            urgency=tool_input.get("urgency", "normal"),
            target_area=tool_input.get("target_area", ""),
        )
        return f"[Notification #{nid} logged: '{tool_input['title']}']"

    elif tool_name == "resolve_complaint":
        db.resolve_complaint(
            complaint_id=tool_input["complaint_id"],
            action_taken=tool_input["action_taken"],
            resolved_by=tool_input.get("resolved_by", ""),
            resident_notice=tool_input.get("resident_notice", ""),
        )
        return f"[Complaint #{tool_input['complaint_id']} resolved]"

    elif tool_name == "community_safety_summary":
        m      = db.community_metrics()
        alerts = db.active_safety_alerts()
        notifs = db.recent_notifications(5)
        lines  = [
            f"Community Safety Summary",
            f"Total complaints: {m['total_complaints']}  |  Open: {m['open_complaints']}  |  Emergencies: {m['emergencies']}",
            f"Active safety alerts: {m['active_alerts']}",
        ]
        if alerts:
            lines.append("\nActive alerts:")
            for a in alerts:
                lines.append(f"  [{a['severity'].upper()}] {a['description'][:70]}")
        if m["by_category"]:
            lines.append("\nComplaints by category:")
            for cat, cnt in sorted(m["by_category"].items(), key=lambda x: -x[1]):
                lines.append(f"  {cat}: {cnt}")
        if notifs:
            lines.append("\nRecent notifications sent:")
            for n in notifs:
                lines.append(f"  [{n['urgency']}] {n['title']} ({n['created_at'][:10]})")
        return "\n".join(lines)

    return f"[Unknown community tool: {tool_name}]"
