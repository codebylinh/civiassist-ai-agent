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
    """Load demo tickets and knowledge base entries."""
    console.print("[cyan]Seeding demo data...[/cyan]")

    # KB entries
    kb_entries = [
        ("billing",   "How do I cancel my subscription?",
         "Go to Account Settings → Billing → Cancel Subscription. Cancellation takes effect at the end of your billing period."),
        ("billing",   "I was charged twice",
         "Double charges are typically resolved within 3–5 business days. Please share your transaction ID and we will investigate immediately."),
        ("technical", "I cannot log in",
         "Try resetting your password via the 'Forgot Password' link. If the issue persists, clear browser cache and try incognito mode."),
        ("technical", "API returning 500 errors",
         "Check our status page for ongoing incidents. If none, share your request payload and we will escalate to engineering."),
        ("account",   "How do I change my email address",
         "Go to Account Settings → Profile → Email. You will receive a verification email at the new address."),
    ]
    for cat, issue, resolution in kb_entries:
        db.add_kb_entry(cat, issue, resolution)

    # Demo tickets
    demo_tickets = [
        ("Cannot access my account after password reset",
         "Hi, I reset my password yesterday but now I cannot log in at all. I keep getting 'Invalid credentials' even though I'm using the new password. I've tried 3 browsers. This is urgent as I have a presentation today."),
        ("Charged twice for the same month",
         "I noticed two charges of $49.99 on my credit card statement for the same billing period (March 2024). Please refund the duplicate charge immediately. My account email is user@example.com."),
        ("Feature request: dark mode",
         "Hi team! Would love to see a dark mode option in the dashboard. My eyes get tired looking at the bright interface for long work sessions. Keep up the great work!"),
        ("Your service is absolutely terrible - URGENT",
         "This is completely unacceptable. Your API has been down for 3 hours and I'm losing revenue every minute. I've sent 5 emails with no response. If this isn't fixed in the next hour I'm canceling and leaving a public review."),
        ("How do I export my data?",
         "Hello, I would like to export all my historical data as a CSV. Is there a way to do this from the dashboard? Thanks"),
    ]
    for subject, body in demo_tickets:
        tid = db.create_ticket(subject, body, source="demo")
        console.print(f"  Created ticket #{tid}: {subject[:50]}")

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
