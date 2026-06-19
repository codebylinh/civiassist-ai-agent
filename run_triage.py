"""
Customer Support Triage CLI.

Commands:
  python run_triage.py submit          — submit a new ticket
  python run_triage.py process <id>    — run triage on a ticket
  python run_triage.py process-all     — process all pending tickets
  python run_triage.py view <id>       — view ticket + classification + draft
  python run_triage.py queue           — list pending/in-progress tickets
  python run_triage.py metrics         — show pipeline stats
  python run_triage.py seed            — load demo tickets + KB entries
"""
import sys
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.text import Text
from rich import box

import pipeline          # triggers init_db()
import pipeline.ticket_store as db
from pipeline.workflow import run, ingest_and_triage

console = Console()

PRIORITY_COLORS = {
    "critical": "bold red",
    "high":     "red",
    "medium":   "yellow",
    "low":      "green",
}
ROUTING_COLORS = {
    "auto_resolve": "green",
    "tier1":        "cyan",
    "tier2":        "blue",
    "escalate":     "bold red",
}
STATUS_COLORS = {
    "pending":     "yellow",
    "in_progress": "cyan",
    "resolved":    "green",
    "escalated":   "bold red",
}


def cmd_submit():
    console.print(Panel("[bold]Submit New Support Ticket[/bold]", border_style="cyan"))
    subject = Prompt.ask("[bold]Subject[/bold]")
    console.print("[dim]Body (paste text, then press Enter twice):[/dim]")
    lines = []
    while True:
        line = input()
        if line == "" and lines and lines[-1] == "":
            break
        lines.append(line)
    body = "\n".join(lines).strip()
    if not body:
        console.print("[red]Body cannot be empty.[/red]")
        return

    ticket_id = db.create_ticket(subject, body, source="cli")
    console.print(f"\n[green]Ticket #{ticket_id} created.[/green]")

    if Confirm.ask("Run triage now?", default=True):
        cmd_process(ticket_id)


def cmd_process(ticket_id: int):
    ticket = db.get_ticket(ticket_id)
    if not ticket:
        console.print(f"[red]Ticket #{ticket_id} not found.[/red]")
        return

    with console.status(f"[cyan]Classifying ticket #{ticket_id}...[/cyan]", spinner="dots"):
        result = run(ticket_id)

    clf = result.classification
    priority_style = PRIORITY_COLORS.get(clf["priority"], "white")
    routing_style  = ROUTING_COLORS.get(clf["routing"], "white")

    console.print()
    console.print(Panel(
        f"[bold]Ticket #{ticket_id}:[/bold] {ticket['subject']}\n\n"
        f"Category:   [cyan]{clf['category']}[/cyan]\n"
        f"Priority:   [{priority_style}]{clf['priority']}[/{priority_style}]\n"
        f"Sentiment:  {clf['sentiment']}\n"
        f"Routing:    [{routing_style}]{clf['routing']}[/{routing_style}]\n"
        f"Confidence: {clf['confidence']:.0%}\n"
        f"Reasoning:  [dim]{clf['reasoning']}[/dim]\n\n"
        f"Action: [bold]{result.action}[/bold]\n"
        f"Reason: [dim]{result.reason}[/dim]",
        title="[bold]Triage Result[/bold]",
        border_style="green" if result.action == "auto_resolved" else "yellow",
    ))

    if result.draft:
        console.print()
        console.print(Panel(result.draft, title="[bold]Drafted Response[/bold]", border_style="blue"))


def cmd_process_all():
    pending = db.list_tickets(status="pending")
    if not pending:
        console.print("[dim]No pending tickets.[/dim]")
        return
    console.print(f"[cyan]Processing {len(pending)} pending tickets...[/cyan]\n")
    for t in pending:
        cmd_process(t["id"])
        console.print()


def cmd_view(ticket_id: int):
    ticket = db.get_ticket(ticket_id)
    if not ticket:
        console.print(f"[red]Ticket #{ticket_id} not found.[/red]")
        return

    clf      = db.get_classification(ticket_id)
    response = db.get_response(ticket_id)
    log      = db.get_log(ticket_id)

    status_style = STATUS_COLORS.get(ticket["status"], "white")

    console.print(Panel(
        f"[bold]#{ticket['id']}[/bold] {ticket['subject']}\n"
        f"Status: [{status_style}]{ticket['status']}[/{status_style}]  |  "
        f"Source: {ticket['source']}  |  Created: {ticket['created_at'][:16]}\n\n"
        f"{ticket['body']}",
        title="Ticket", border_style="cyan"
    ))

    if clf:
        console.print(Panel(
            f"Category: [cyan]{clf['category']}[/cyan]  |  "
            f"Priority: [{PRIORITY_COLORS.get(clf['priority'], 'white')}]{clf['priority']}[/{PRIORITY_COLORS.get(clf['priority'], 'white')}]  |  "
            f"Sentiment: {clf['sentiment']}  |  "
            f"Routing: [{ROUTING_COLORS.get(clf['routing'], 'white')}]{clf['routing']}[/{ROUTING_COLORS.get(clf['routing'], 'white')}]  |  "
            f"Confidence: {clf['confidence']:.0%}\n\n"
            f"[dim]{clf['reasoning']}[/dim]",
            title="Classification", border_style="yellow"
        ))

    if response:
        console.print(Panel(
            f"{response['draft']}\n\n[dim]Status: {response['status']}[/dim]",
            title="Response Draft", border_style="blue"
        ))

    if log:
        tbl = Table(box=box.SIMPLE, show_header=True)
        tbl.add_column("Time", style="dim", width=16)
        tbl.add_column("Action", style="bold")
        tbl.add_column("Details")
        for entry in log:
            tbl.add_row(
                entry["ts"][:16],
                entry["action"],
                (entry.get("reason") or entry.get("agent_notes") or "")[:80]
            )
        console.print(Panel(tbl, title="Triage Log", border_style="dim"))


def cmd_queue():
    tickets = db.list_tickets()
    if not tickets:
        console.print("[dim]No tickets.[/dim]")
        return

    tbl = Table(title="Ticket Queue", box=box.ROUNDED)
    tbl.add_column("#",        style="dim",  width=5)
    tbl.add_column("Subject",  width=40)
    tbl.add_column("Status",   width=12)
    tbl.add_column("Category", width=14)
    tbl.add_column("Priority", width=10)
    tbl.add_column("Routing",  width=14)
    tbl.add_column("Created",  width=16, style="dim")

    for t in tickets:
        status_style   = STATUS_COLORS.get(t["status"], "white")
        priority_style = PRIORITY_COLORS.get(t.get("priority") or "", "white")
        routing_style  = ROUTING_COLORS.get(t.get("routing") or "", "white")
        tbl.add_row(
            str(t["id"]),
            t["subject"][:38],
            f"[{status_style}]{t['status']}[/{status_style}]",
            t.get("category") or "[dim]—[/dim]",
            f"[{priority_style}]{t.get('priority') or '—'}[/{priority_style}]",
            f"[{routing_style}]{t.get('routing') or '—'}[/{routing_style}]",
            t["created_at"][:16],
        )

    console.print(tbl)


def cmd_metrics():
    m = db.metrics()
    tbl = Table(title="Pipeline Metrics", box=box.ROUNDED)
    tbl.add_column("Metric")
    tbl.add_column("Value", justify="right")

    tbl.add_row("Total tickets",   str(m["total"]))
    tbl.add_row("Auto-resolved",   str(m["auto_resolved"]))
    for status, count in sorted(m["by_status"].items()):
        style = STATUS_COLORS.get(status, "white")
        tbl.add_row(f"  [{style}]{status}[/{style}]", str(count))
    tbl.add_section()
    for cat, count in sorted(m["by_category"].items(), key=lambda x: -x[1]):
        tbl.add_row(f"  {cat}", str(count))
    tbl.add_section()
    for pri, count in sorted(m["by_priority"].items(), key=lambda x: -x[1]):
        style = PRIORITY_COLORS.get(pri, "white")
        tbl.add_row(f"  [{style}]{pri}[/{style}]", str(count))

    console.print(tbl)


def cmd_seed():
    """Load construction/civil engineering demo tickets and knowledge base entries."""
    console.print("[cyan]Seeding construction domain demo data...[/cyan]")

    # Knowledge base entries
    kb_entries = [
        ("rfi",
         "Rebar spacing conflict between structural drawings and architectural",
         "Issue an RFI to the structural engineer of record immediately. Do not place concrete until the conflict is resolved and a written response is received. Document the RFI with drawing revision numbers and conflicting details."),
        ("site_issue",
         "Unexpected rock encountered during excavation",
         "Stop excavation in the affected area. Notify the geotechnical engineer and project manager within 24 hours. Document with photos and survey coordinates. A change order will likely be required — do not proceed without owner authorization on scope and cost."),
        ("safety",
         "Worker fell into unprotected excavation",
         "STOP all work in the area immediately. Call emergency services if injury occurred. Notify OSHA (within 8 hours for hospitalization). Preserve the scene. Contact the project safety officer and legal team. Do not resume work until a safety review is completed and corrective measures are in place."),
        ("permit_approval",
         "Building permit application timeline",
         "Typical permit timelines: residential 2–6 weeks, commercial 6–16 weeks, infrastructure varies by jurisdiction. Submit complete, coordinated documents to avoid re-review cycles. Pre-application meetings with the AHJ (Authority Having Jurisdiction) can reduce review time significantly."),
        ("budget_cost",
         "What triggers a change order",
         "Change orders are required for any change to contract scope, schedule, or price. Common triggers: owner-directed changes, unforeseen site conditions (differing site conditions clause), design errors/omissions, code changes post-contract. Always get a signed CO before proceeding with changed work."),
        ("design_review",
         "Minimum concrete cover requirements",
         "Per ACI 318: footings cast against earth = 3 inches; slabs on grade = 1.5 inches; beams/columns exposed to weather = 2 inches; walls exposed to weather = 1.5 inches (≤#5 bar) or 2 inches (≥#6). Verify with project specifications which may require greater cover."),
        ("schedule",
         "Critical path method for construction scheduling",
         "The critical path is the longest sequence of dependent activities determining project duration. Float (slack) = zero on critical path activities. Delays on the critical path directly delay project completion. Use CPM software (Primavera P6, MS Project) to identify and monitor critical path activities weekly."),
        ("zoning_planning",
         "How to apply for a zoning variance",
         "A variance permits deviation from zoning standards when strict application causes undue hardship. Process: pre-application meeting → formal application with site plan → staff report → public hearing (notice required 10–21 days prior) → board decision → appeal period. Hardship must be demonstrated; self-created hardship is generally not grounds for a variance."),
        ("submittal",
         "Submittal review stamps and what they mean",
         "Approved: fabricate/install as submitted. Approved as Noted: fabricate/install per reviewer's markups. Revise and Resubmit: corrections required before proceeding — resubmit for review. Rejected: does not meet contract requirements — resubmit with compliant product. Fabrication before approval is at contractor's risk."),
        ("client_inquiry",
         "Client asking for project status update",
         "Provide a brief update covering: (1) current phase and % complete, (2) schedule status vs. baseline, (3) any active issues affecting budget or timeline, (4) next milestone and target date. Use plain language — avoid acronyms. Always end with the next action item and who is responsible."),
    ]
    for cat, issue, resolution in kb_entries:
        db.add_kb_entry(cat, issue, resolution)

    # Demo tickets
    demo_tickets = [
        ("RFI: Footing depth conflict between geotech report and structural drawings",
         "The geotech report recommends minimum footing depth of 4'-0\" below grade due to expansive clay. However, the structural drawings show 3'-0\" depth for interior spread footings. Which takes precedence? We are scheduled to start footing excavation Monday and cannot proceed without clarification. Project: Northgate Community Center."),

        ("URGENT: Worker injury on site — excavation collapse",
         "A section of the trench wall collapsed at the Main Street water main project this morning (approx. 9:15 AM). One worker was partially buried. Emergency services responded and the worker was taken to hospital. OSHA has been notified. The site is shut down. We need immediate guidance on next steps and documentation requirements."),

        ("Change order dispute — rock excavation at Riverside Road",
         "The contractor is claiming $85,000 for rock excavation encountered at 6ft depth, which they say qualifies as a differing site condition. The original geotech report indicated rock at 10–12ft. We have reviewed the boring logs and believe the contractor had sufficient information. Can you advise on how to evaluate this claim?"),

        ("Client inquiry: When will the Maple Avenue bridge be open to traffic?",
         "Hi, I'm a resident near the Maple Avenue bridge construction. The project has been going on for 8 months now. The original completion date shown on the sign was October 15th and it's now November. Nobody seems to be able to give us a straight answer. When will it open? Who can I contact?"),

        ("Stormwater permit question: Does our site need a SWPPP?",
         "We're breaking ground on a 3.5-acre commercial development next month. Our contractor is asking whether we need a Stormwater Pollution Prevention Plan. We are disturbing about 2.8 acres. The site drains to a creek that is a tributary of a state-designated water quality impaired water body."),
    ]
    for subject, body in demo_tickets:
        tid = db.create_ticket(subject, body, source="demo")
        console.print(f"  Created ticket #{tid}: {subject[:60]}")

    console.print(f"\n[green]Seeded {len(kb_entries)} KB entries and {len(demo_tickets)} tickets.[/green]")
    console.print("Run [bold]python run_triage.py process-all[/bold] to triage them.")


def main():
    args = sys.argv[1:]
    if not args:
        console.print(__doc__)
        return

    cmd = args[0].lower()

    if cmd == "submit":
        cmd_submit()
    elif cmd == "process":
        if len(args) < 2:
            console.print("[red]Usage: process <ticket_id>[/red]")
            return
        cmd_process(int(args[1]))
    elif cmd == "process-all":
        cmd_process_all()
    elif cmd == "view":
        if len(args) < 2:
            console.print("[red]Usage: view <ticket_id>[/red]")
            return
        cmd_view(int(args[1]))
    elif cmd == "queue":
        cmd_queue()
    elif cmd == "metrics":
        cmd_metrics()
    elif cmd == "seed":
        cmd_seed()
    else:
        console.print(f"[red]Unknown command: {cmd}[/red]")
        console.print(__doc__)


if __name__ == "__main__":
    main()
