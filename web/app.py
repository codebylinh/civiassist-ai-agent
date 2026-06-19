"""
FastAPI web application — serves the browser UI and JSON API.
"""
import os
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

import pipeline.community as community_db
import pipeline.projects as proj_db
import pipeline.ticket_store as ticket_db
from pipeline.community_workflow import ingest_and_process, process_complaint
from pipeline.workflow import run as triage_run, ingest_and_triage

BASE = Path(__file__).parent
templates = Jinja2Templates(directory=str(BASE / "templates"))

app = FastAPI(title="civil-agent")

# Serve static files if any
static_dir = BASE / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Global agent instance + conversation state
_agent = None
_conversation_history: list[dict] = []


def get_agent():
    global _agent
    if _agent is None:
        from core.agent import Agent
        _agent = Agent()
    return _agent


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    community_db.init_db()
    proj_db.init_db()
    ticket_db.init_db()

    cm     = community_db.community_metrics()
    alerts = community_db.active_safety_alerts()
    projects = proj_db.list_projects()
    tickets  = ticket_db.list_tickets(status="pending", limit=5)

    return templates.TemplateResponse("index.html", {
        "request":  request,
        "metrics":  cm,
        "alerts":   alerts[:3],
        "projects": projects[:5],
        "tickets":  tickets,
    })


@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    return templates.TemplateResponse("chat.html", {"request": request})


@app.get("/complaints", response_class=HTMLResponse)
async def complaints_page(request: Request):
    community_db.init_db()
    complaints = community_db.list_complaints()
    alerts     = community_db.active_safety_alerts()
    return templates.TemplateResponse("complaints.html", {
        "request":    request,
        "complaints": complaints,
        "alerts":     alerts,
    })


@app.get("/projects", response_class=HTMLResponse)
async def projects_page(request: Request):
    proj_db.init_db()
    projects = proj_db.list_projects()
    return templates.TemplateResponse("projects.html", {
        "request":  request,
        "projects": projects,
    })


@app.get("/triage", response_class=HTMLResponse)
async def triage_page(request: Request):
    ticket_db.init_db()
    tickets = ticket_db.list_tickets()
    metrics = ticket_db.metrics()
    return templates.TemplateResponse("triage.html", {
        "request": request,
        "tickets": tickets,
        "metrics": metrics,
    })


# ---------------------------------------------------------------------------
# API — Chat
# ---------------------------------------------------------------------------

@app.post("/api/chat")
async def api_chat(request: Request):
    global _conversation_history
    body = await request.json()
    message = body.get("message", "").strip()
    if not message:
        return JSONResponse({"error": "Empty message"}, status_code=400)
    try:
        agent = get_agent()
        response, _conversation_history = agent.chat(message, _conversation_history)
        return {"response": response}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/chat/reset")
async def api_chat_reset():
    global _conversation_history, _agent
    if _agent:
        try:
            _agent.end_session()
        except Exception:
            pass
    _agent = None
    _conversation_history = []
    return {"status": "reset"}


# ---------------------------------------------------------------------------
# API — Community Complaints
# ---------------------------------------------------------------------------

@app.post("/api/complaints")
async def api_file_complaint(request: Request):
    body = await request.json()
    try:
        result = ingest_and_process(
            description=body.get("description", ""),
            location=body.get("location", ""),
            reported_by=body.get("reported_by", ""),
            contact=body.get("contact", ""),
        )
        clf = result.classification
        return {
            "complaint_id":      result.complaint_id,
            "severity":          clf["severity"],
            "category":          clf["category"],
            "public_risk":       clf["public_risk"],
            "action":            result.action,
            "deadline":          result.deadline,
            "resident_response": result.resident_response,
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/complaints/{complaint_id}/process")
async def api_process_complaint(complaint_id: int):
    try:
        result = process_complaint(complaint_id)
        return {
            "complaint_id":      result.complaint_id,
            "classification":    result.classification,
            "resident_response": result.resident_response,
            "construction_memo": result.construction_memo,
            "action":            result.action,
            "deadline":          result.deadline,
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/complaints/{complaint_id}/resolve")
async def api_resolve_complaint(complaint_id: int, request: Request):
    body = await request.json()
    community_db.resolve_complaint(
        complaint_id,
        action_taken=body.get("action_taken", ""),
        resolved_by=body.get("resolved_by", ""),
        resident_notice=body.get("resident_notice", ""),
    )
    return {"status": "resolved"}


@app.get("/api/complaints/{complaint_id}")
async def api_get_complaint(complaint_id: int):
    complaint  = community_db.get_complaint(complaint_id)
    resolution = community_db.get_resolution(complaint_id)
    if not complaint:
        return JSONResponse({"error": "Not found"}, status_code=404)
    with community_db._conn() as c:
        clf_row = c.execute(
            "SELECT * FROM complaint_classifications WHERE complaint_id=?", (complaint_id,)
        ).fetchone()
    return {
        "complaint":       complaint,
        "classification":  dict(clf_row) if clf_row else None,
        "resolution":      resolution,
    }


# ---------------------------------------------------------------------------
# API — Projects
# ---------------------------------------------------------------------------

@app.post("/api/projects")
async def api_create_project(request: Request):
    body = await request.json()
    pid = proj_db.create_project(
        name=body.get("name", ""),
        description=body.get("description", ""),
        client=body.get("client", ""),
        location=body.get("location", ""),
        target_date=body.get("target_date", ""),
    )
    return {"project_id": pid}


@app.get("/api/projects/{project_id}/summary")
async def api_project_summary(project_id: int):
    summary = proj_db.project_summary(project_id)
    return {"summary": summary}


@app.post("/api/projects/{project_id}/rfis")
async def api_create_rfi(project_id: int, request: Request):
    body = await request.json()
    rfi_id = proj_db.create_rfi(
        project_id=project_id,
        subject=body.get("subject", ""),
        question=body.get("question", ""),
        discipline=body.get("discipline", "civil"),
        submitted_by=body.get("submitted_by", ""),
    )
    return {"rfi_id": rfi_id}


@app.post("/api/projects/{project_id}/issues")
async def api_log_issue(project_id: int, request: Request):
    body = await request.json()
    iid = proj_db.log_site_issue(
        project_id=project_id,
        description=body.get("description", ""),
        severity=body.get("severity", "medium"),
        location=body.get("location", ""),
        reported_by=body.get("reported_by", ""),
    )
    return {"issue_id": iid}


# ---------------------------------------------------------------------------
# API — Triage
# ---------------------------------------------------------------------------

@app.post("/api/triage")
async def api_triage(request: Request):
    body = await request.json()
    try:
        result = ingest_and_triage(
            subject=body.get("subject", ""),
            body=body.get("body", ""),
            source="web",
        )
        return {
            "ticket_id":     result.ticket_id,
            "classification": result.classification,
            "draft":         result.draft,
            "action":        result.action,
            "reason":        result.reason,
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/triage/{ticket_id}/process")
async def api_process_ticket(ticket_id: int):
    try:
        result = triage_run(ticket_id)
        return {
            "ticket_id":      result.ticket_id,
            "classification": result.classification,
            "action":         result.action,
        }
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
