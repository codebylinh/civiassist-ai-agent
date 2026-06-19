"""
Construction-specific tools available to the agent.
All project data is sandboxed to the local SQLite store.
"""
import pipeline.projects as proj

CONSTRUCTION_TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "list_projects",
            "description": "List all active construction/planning projects with their current phase and open items.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_project_summary",
            "description": "Get a full status summary for a project: phase, open RFIs, pending submittals, site issues.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_name": {"type": "string", "description": "Project name (partial match OK)"}
                },
                "required": ["project_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_project",
            "description": "Create a new project in the tracker.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name":        {"type": "string"},
                    "description": {"type": "string"},
                    "client":      {"type": "string"},
                    "location":    {"type": "string"},
                    "target_date": {"type": "string", "description": "YYYY-MM-DD"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "advance_project_phase",
            "description": "Move a project to the next phase.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_name": {"type": "string"},
                    "new_phase": {
                        "type": "string",
                        "description": "pre_design | schematic_design | design_development | construction_documents | permitting | bidding | construction | closeout | warranty",
                    },
                    "notes": {"type": "string"},
                },
                "required": ["project_name", "new_phase"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_rfi",
            "description": "Log a new RFI (Request for Information) for a project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_name":  {"type": "string"},
                    "subject":       {"type": "string"},
                    "question":      {"type": "string", "description": "Full RFI question text"},
                    "discipline":    {"type": "string", "description": "civil | structural | mechanical | electrical | architectural"},
                    "submitted_by":  {"type": "string"},
                    "due_date":      {"type": "string", "description": "YYYY-MM-DD"},
                },
                "required": ["project_name", "subject", "question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_rfis",
            "description": "List RFIs for a project, optionally filtered by status.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_name": {"type": "string"},
                    "status": {"type": "string", "description": "open | answered | closed"},
                },
                "required": ["project_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "log_site_issue",
            "description": "Log a site issue or field condition problem.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_name": {"type": "string"},
                    "description":  {"type": "string"},
                    "severity":     {"type": "string", "description": "critical | high | medium | low"},
                    "location":     {"type": "string", "description": "Location on site"},
                    "reported_by":  {"type": "string"},
                },
                "required": ["project_name", "description"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_site_issues",
            "description": "List open site issues for a project, ordered by severity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_name": {"type": "string"},
                },
                "required": ["project_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_submittal",
            "description": "Log a new submittal (shop drawing, product data, material sample).",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_name":  {"type": "string"},
                    "description":   {"type": "string"},
                    "spec_section":  {"type": "string", "description": "Spec section number e.g. 03 30 00"},
                    "submitted_by":  {"type": "string"},
                },
                "required": ["project_name", "description"],
            },
        },
    },
]


def dispatch_construction_tool(tool_name: str, tool_input: dict) -> str:
    proj.init_db()

    def _find_project(name: str) -> dict | None:
        return proj.get_project_by_name(name)

    if tool_name == "list_projects":
        projects = proj.list_projects()
        if not projects:
            return "No active projects."
        return proj.all_projects_summary()

    elif tool_name == "get_project_summary":
        p = _find_project(tool_input["project_name"])
        if not p:
            return f"Project '{tool_input['project_name']}' not found."
        return proj.project_summary(p["id"])

    elif tool_name == "create_project":
        pid = proj.create_project(
            name=tool_input["name"],
            description=tool_input.get("description", ""),
            client=tool_input.get("client", ""),
            location=tool_input.get("location", ""),
            target_date=tool_input.get("target_date", ""),
        )
        return f"[Project created: {tool_input['name']} (#{pid})]"

    elif tool_name == "advance_project_phase":
        p = _find_project(tool_input["project_name"])
        if not p:
            return f"Project '{tool_input['project_name']}' not found."
        proj.advance_phase(p["id"], tool_input["new_phase"], tool_input.get("notes", ""))
        return f"[{p['name']} advanced to phase: {tool_input['new_phase']}]"

    elif tool_name == "create_rfi":
        p = _find_project(tool_input["project_name"])
        if not p:
            return f"Project '{tool_input['project_name']}' not found."
        rfi_id = proj.create_rfi(
            project_id=p["id"],
            subject=tool_input["subject"],
            question=tool_input["question"],
            discipline=tool_input.get("discipline", "civil"),
            submitted_by=tool_input.get("submitted_by", ""),
            due_date=tool_input.get("due_date", ""),
        )
        rfis = proj.list_rfis(p["id"])
        rfi_number = rfis[-1]["rfi_number"] if rfis else f"RFI-{rfi_id}"
        return f"[RFI logged: {rfi_number} — {tool_input['subject']}]"

    elif tool_name == "list_rfis":
        p = _find_project(tool_input["project_name"])
        if not p:
            return f"Project '{tool_input['project_name']}' not found."
        rfis = proj.list_rfis(p["id"], status=tool_input.get("status"))
        if not rfis:
            return f"No RFIs found for {p['name']}."
        lines = [f"RFIs for {p['name']}:"]
        for r in rfis:
            lines.append(f"  [{r['rfi_number']}] [{r['status'].upper()}] {r['subject']}")
            if r.get("response"):
                lines.append(f"    → {r['response'][:80]}")
        return "\n".join(lines)

    elif tool_name == "log_site_issue":
        p = _find_project(tool_input["project_name"])
        if not p:
            return f"Project '{tool_input['project_name']}' not found."
        iid = proj.log_site_issue(
            project_id=p["id"],
            description=tool_input["description"],
            severity=tool_input.get("severity", "medium"),
            location=tool_input.get("location", ""),
            reported_by=tool_input.get("reported_by", ""),
        )
        return f"[Site issue #{iid} logged — severity: {tool_input.get('severity', 'medium')}]"

    elif tool_name == "list_site_issues":
        p = _find_project(tool_input["project_name"])
        if not p:
            return f"Project '{tool_input['project_name']}' not found."
        issues = proj.list_site_issues(p["id"])
        if not issues:
            return f"No open site issues for {p['name']}."
        lines = [f"Open site issues for {p['name']}:"]
        for i in issues:
            lines.append(f"  [{i['severity'].upper()}] {i['description'][:80]}")
        return "\n".join(lines)

    elif tool_name == "create_submittal":
        p = _find_project(tool_input["project_name"])
        if not p:
            return f"Project '{tool_input['project_name']}' not found."
        sid = proj.create_submittal(
            project_id=p["id"],
            description=tool_input["description"],
            spec_section=tool_input.get("spec_section", ""),
            submitted_by=tool_input.get("submitted_by", ""),
        )
        return f"[Submittal #{sid} logged: {tool_input['description'][:60]}]"

    return f"[Unknown construction tool: {tool_name}]"
