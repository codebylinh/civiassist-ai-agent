"""
Community Safety CLI — manage resident complaints and safety alerts.

Commands:
  python run_community.py report           — resident files a complaint
  python run_community.py process <id>     — classify and draft responses for a complaint
  python run_community.py process-all      — process all unclassified complaints
  python run_community.py view <id>        — view complaint, classification, and drafts
  python run_community.py complaints       — list all open complaints by severity
  python run_community.py alerts           — list active safety alerts
  python run_community.py notify           — draft and log a notification to residents
  python run_community.py resolve <id>     — mark a complaint as resolved
  python run_community.py metrics          — community safety dashboard
  python run_community.py seed             — load demo complaints
"""
import sys
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich import box

import pipeline.community as db
from pipeline.community_workflow import process_complaint, ingest_and_process

console = Console()

SEV_COLORS = {
    "emergency": "bold red",
    "high":      "red",
    "medium":    "yellow",
    "low":       "green",
}
STATUS_COLORS = {
    "open":     "yellow",
    "resolved": "green",
}
URGENCY_COLORS = {
    "urgent":        "bold red",
    "normal":        "cyan",
    "informational": "dim",
}


def cmd_report():
    console.print(Panel("[bold]File a Community Safety Complaint[/bold]", border_style="yellow"))
    console.print("[dim]Describe the safety issue or nuisance caused by the nearby construction.[/dim]\n")

    description = Prompt.ask("[bold]What is happening?[/bold]")
    location    = Prompt.ask("Your address or nearest landmark", default="")
    name        = Prompt.ask("Your name (optional)", default="Anonymous")
    contact     = Prompt.ask("Phone or email for follow-up (optional)", default="")

    console.print()
    with console.status("[cyan]Assessing complaint...[/cyan]", spinner="dots"):
        result = ingest_and_process(description, location, name, contact)

    clf = result.classification
    sev_style = SEV_COLORS.get(clf["severity"], "white")

    console.print(Panel(
        f"Complaint [bold]#{result.complaint_id}[/bold] received.\n\n"
        f"Severity:  [{sev_style}]{clf['severity'].upper()}[/{sev_style}]\n"
        f"Type:      {clf['category']}\n"
        f"Risk:      [dim]{clf['public_risk']}[/dim]\n"
        f"Action:    [bold]{result.action}[/bold]\n"
        f"Deadline:  {result.deadline}",
        title="[bold]Complaint Acknowledged[/bold]",
        border_style=sev_style,
    ))

    if result.resident_response:
        console.print()
        console.print(Panel(
            result.resident_response,
            title="[bold]Response to You[/bold]",
            border_style="blue",
        ))

    if clf["severity"] == "emergency":
        console.print()
        console.print(Panel(
            "[bold red]This is an EMERGENCY.[/bold red]\n"
            "If there is immediate danger to life, call [bold]911[/bold] now.\n"
            "The site superintendent has been alerted.",
            border_style="bold red",
        ))


def cmd_process(complaint_id: int):
    complaint = db.get_complaint(complaint_id)
    if not complaint:
        console.print(f"[red]Complaint #{complaint_id} not found.[/red]")
        return

    with console.status(f"[cyan]Processing complaint #{complaint_id}...[/cyan]", spinner="dots"):
        result = process_complaint(complaint_id)

    clf = result.classification
    sev_style = SEV_COLORS.get(clf["severity"], "white")

    console.print()
    console.print(Panel(
        f"[bold]Complaint #{complaint_id}[/bold]\n"
        f"Severity:  [{sev_style}]{clf['severity'].upper()}[/{sev_style}]\n"
        f"Category:  {clf['category']}\n"
        f"Public risk: [dim]{clf['public_risk']}[/dim]\n"
        f"Routing:   {clf['routing']}\n"
        f"Confidence: {clf['confidence']:.0%}\n\n"
        f"Action:    [bold]{result.action}[/bold]\n"
        f"Deadline:  {result.deadline}",
        title="[bold]Triage Result[/bold]",
        border_style=sev_style,
    ))

    if result.resident_response:
        console.print(Panel(result.resident_response, title="[bold]Resident Response[/bold]", border_style="blue"))

    if result.construction_memo:
        console.print(Panel(result.construction_memo, title="[bold]Site Action Memo[/bold]", border_style="yellow"))


def cmd_process_all():
    with db._conn() as c:
        unclassified = c.execute(
            "SELECT c.id FROM complaints c "
            "LEFT JOIN complaint_classifications cc ON cc.complaint_id = c.id "
            "WHERE cc.id IS NULL AND c.status='open'"
        ).fetchall()
    ids = [r[0] for r in unclassified]
    if not ids:
        console.print("[dim]No unprocessed complaints.[/dim]")
        return
    console.print(f"[cyan]Processing {len(ids)} unclassified complaints...[/cyan]\n")
    for cid in ids:
        cmd_process(cid)
        console.print()


def cmd_view(complaint_id: int):
    complaint  = db.get_complaint(complaint_id)
    resolution = db.get_resolution(complaint_id)
    if not complaint:
        console.print(f"[red]Complaint #{complaint_id} not found.[/red]")
        return

    with db._conn() as c:
        clf_row = c.execute(
            "SELECT * FROM complaint_classifications WHERE complaint_id=?", (complaint_id,)
        ).fetchone()
        clf = dict(clf_row) if clf_row else {}

    status_style = STATUS_COLORS.get(complaint["status"], "white")
    sev_style    = SEV_COLORS.get(clf.get("severity", ""), "white")

    console.print(Panel(
        f"[bold]Complaint #{complaint['id']}[/bold]  "
        f"[{status_style}]{complaint['status'].upper()}[/{status_style}]\n"
        f"Filed: {complaint['created_at'][:16]}  |  "
        f"By: {complaint.get('reported_by') or 'Anonymous'}  |  "
        f"Location: {complaint.get('location') or 'N/A'}\n\n"
        f"{complaint['description']}",
        title="Complaint", border_style="cyan"
    ))

    if clf:
        console.print(Panel(
            f"Category: [cyan]{clf['category']}[/cyan]  |  "
            f"Severity: [{sev_style}]{clf['severity'].upper()}[/{sev_style}]  |  "
            f"Routing: {clf['routing']}  |  Confidence: {clf['confidence']:.0%}\n\n"
            f"Public risk: [dim]{clf.get('public_risk', '')}[/dim]\n"
            f"Reasoning:   [dim]{clf.get('reasoning', '')}[/dim]",
            title="Classification", border_style="yellow"
        ))

    if resolution:
        console.print(Panel(
            f"Action taken: {resolution['action_taken']}\n"
            f"Resolved by:  {resolution.get('resolved_by') or 'N/A'}\n"
            f"Resolved at:  {resolution['created_at'][:16]}\n\n"
            + (f"Notice to resident:\n{resolution['resident_notice']}" if resolution.get("resident_notice") else ""),
            title="Resolution", border_style="green"
        ))


def cmd_complaints():
    complaints = db.list_complaints(status="open")
    if not complaints:
        console.print("[green]No open complaints.[/green]")
        return

    tbl = Table(title=f"Open Complaints ({len(complaints)})", box=box.ROUNDED)
    tbl.add_column("#",          width=5,  style="dim")
    tbl.add_column("Severity",   width=11)
    tbl.add_column("Category",   width=18)
    tbl.add_column("Description",width=45)
    tbl.add_column("Location",   width=20)
    tbl.add_column("Filed",      width=11, style="dim")

    for c in complaints:
        sev = c.get("severity") or "—"
        sev_style = SEV_COLORS.get(sev, "white")
        tbl.add_row(
            str(c["id"]),
            f"[{sev_style}]{sev.upper()}[/{sev_style}]",
            c.get("category") or "[dim]unclassified[/dim]",
            c["description"][:43],
            (c.get("location") or "")[:18],
            c["created_at"][:10],
        )

    console.print(tbl)


def cmd_alerts():
    alerts = db.active_safety_alerts()
    if not alerts:
        console.print("[green]No active safety alerts.[/green]")
        return

    tbl = Table(title=f"Active Safety Alerts ({len(alerts)})", box=box.ROUNDED)
    tbl.add_column("Severity",    width=11)
    tbl.add_column("Description", width=55)
    tbl.add_column("Area",        width=20)
    tbl.add_column("Created",     width=11, style="dim")

    for a in alerts:
        sev_style = SEV_COLORS.get(a["severity"], "white")
        tbl.add_row(
            f"[{sev_style}]{a['severity'].upper()}[/{sev_style}]",
            a["description"][:53],
            (a.get("affected_area") or "")[:18],
            a["created_at"][:10],
        )

    console.print(tbl)


def cmd_notify():
    console.print(Panel("[bold]Send Notification to Residents[/bold]", border_style="cyan"))
    title       = Prompt.ask("[bold]Notification title[/bold]")
    message     = Prompt.ask("Message")
    target_area = Prompt.ask("Target area (streets / radius)", default="")
    urgency     = Prompt.ask("Urgency", choices=["urgent", "normal", "informational"], default="normal")
    project     = Prompt.ask("Project name (optional)", default="")

    nid = db.create_notification(title, message, project, urgency, target_area)
    console.print(f"\n[green]Notification #{nid} logged.[/green]")


def cmd_resolve(complaint_id: int):
    complaint = db.get_complaint(complaint_id)
    if not complaint:
        console.print(f"[red]Complaint #{complaint_id} not found.[/red]")
        return

    console.print(Panel(f"#{complaint['id']}: {complaint['description'][:100]}", title="Complaint"))
    action         = Prompt.ask("[bold]Action taken to resolve[/bold]")
    resolved_by    = Prompt.ask("Resolved by", default="")
    resident_notice = Prompt.ask("Message for the resident (optional)", default="")

    db.resolve_complaint(complaint_id, action, resolved_by, resident_notice)
    console.print(f"\n[green]Complaint #{complaint_id} marked resolved.[/green]")


def cmd_metrics():
    m      = db.community_metrics()
    alerts = db.active_safety_alerts()
    notifs = db.recent_notifications(5)

    tbl = Table(title="Community Safety Dashboard", box=box.ROUNDED)
    tbl.add_column("Metric")
    tbl.add_column("Value", justify="right")

    tbl.add_row("Total complaints",   str(m["total_complaints"]))
    tbl.add_row("Open",               str(m["open_complaints"]))
    tbl.add_row("Emergencies",        f"[bold red]{m['emergencies']}[/bold red]")
    tbl.add_row("Active safety alerts", str(m["active_alerts"]))
    tbl.add_section()
    for sev in ["emergency", "high", "medium", "low"]:
        cnt = m["by_severity"].get(sev, 0)
        style = SEV_COLORS.get(sev, "white")
        tbl.add_row(f"  [{style}]{sev}[/{style}]", str(cnt))
    tbl.add_section()
    for cat, cnt in sorted(m["by_category"].items(), key=lambda x: -x[1]):
        tbl.add_row(f"  {cat}", str(cnt))

    console.print(tbl)

    if alerts:
        console.print()
        console.print(Panel(
            "\n".join(
                f"[{SEV_COLORS.get(a['severity'], 'white')}]{a['severity'].upper()}[/{SEV_COLORS.get(a['severity'], 'white')}]  "
                f"{a['description'][:70]}"
                for a in alerts
            ),
            title="Active Safety Alerts", border_style="red"
        ))


def cmd_seed():
    console.print("[cyan]Seeding demo community complaints...[/cyan]")
    demos = [
        ("Construction noise at 11PM woke my family",
         "The drilling and compacting on Oak Street has been going on past 11PM for three nights in a row. My children cannot sleep. This cannot be legal.",
         "23 Oak Street", "Maria Santos", "maria@email.com"),

        ("URGENT: Fence collapsed onto sidewalk — children walk here for school",
         "The hoarding fence on the north side of the Elm Avenue site has partially collapsed onto the footpath. It's blocking the sidewalk and there are loose boards with nails sticking out. Children from Jefferson Elementary walk past here every morning at 8AM. This needs to be fixed TODAY.",
         "Elm Avenue near 4th Street", "James Okoro", ""),

        ("Thick dust cloud covered my car and garden every day this week",
         "The excavation work on the corner site has been throwing up huge dust clouds with no water suppression. My car is coated, my vegetable garden is ruined, and I can smell it inside my house. My wife has asthma. Please send someone to inspect.",
         "12 Maple Drive", "Susan Chen", "susan.chen@gmail.com"),

        ("Crack appeared in my living room wall since pile driving started",
         "Since the pile driving began on Monday, a crack has appeared in my living room wall that was not there before. It runs from the corner of the window to the ceiling — about 60cm long. I am very concerned about structural damage to my home. I need someone to inspect immediately.",
         "8 Birchwood Lane", "Robert Andersen", "r.andersen@outlook.com"),

        ("Road closed without warning — cannot get to work",
         "Cedar Road was closed this morning with no advance notice at all. I had no idea and was 45 minutes late to work. There are no detour signs either. A lot of people in this neighbourhood depend on that road. How long will this last and why weren't we notified?",
         "Cedar Road and 2nd Avenue", "Tony Williams", ""),
    ]
    for desc, body, loc, name, contact in demos:
        cid = db.file_complaint(body, loc, name, contact)
        console.print(f"  Filed complaint #{cid}: {desc[:60]}")

    console.print(f"\n[green]Seeded {len(demos)} complaints.[/green]")
    console.print("Run [bold]python run_community.py process-all[/bold] to triage them.")


def main():
    db.init_db()
    args = sys.argv[1:]
    if not args:
        console.print(__doc__)
        return

    cmd = args[0].lower()

    if cmd == "report":
        cmd_report()
    elif cmd == "process":
        if len(args) < 2:
            console.print("[red]Usage: process <complaint_id>[/red]")
            return
        cmd_process(int(args[1]))
    elif cmd == "process-all":
        cmd_process_all()
    elif cmd == "view":
        if len(args) < 2:
            console.print("[red]Usage: view <complaint_id>[/red]")
            return
        cmd_view(int(args[1]))
    elif cmd == "complaints":
        cmd_complaints()
    elif cmd == "alerts":
        cmd_alerts()
    elif cmd == "notify":
        cmd_notify()
    elif cmd == "resolve":
        if len(args) < 2:
            console.print("[red]Usage: resolve <complaint_id>[/red]")
            return
        cmd_resolve(int(args[1]))
    elif cmd == "metrics":
        cmd_metrics()
    elif cmd == "seed":
        cmd_seed()
    else:
        console.print(f"[red]Unknown command: {cmd}[/red]")
        console.print(__doc__)


if __name__ == "__main__":
    main()
