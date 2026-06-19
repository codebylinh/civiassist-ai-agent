"""
Architecture Agent — main entry point.

Run:  python main.py
Env:  ANTHROPIC_API_KEY=sk-...   (or set in .env)
"""
import sys
import signal
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text
from rich.rule import Rule

import config

console = Console()


def _check_ollama():
    import ollama
    try:
        client = ollama.Client(host=config.OLLAMA_HOST)
        models = [m.model for m in client.list().models]
        if not any(config.MODEL in m for m in models):
            console.print(f"[yellow]Model '{config.MODEL}' not found. Pulling it now...[/yellow]")
            console.print(f"  [dim]ollama pull {config.MODEL}[/dim]")
            client.pull(config.MODEL)
    except Exception as e:
        console.print(f"[red]Cannot reach Ollama at {config.OLLAMA_HOST}[/red]")
        console.print("Make sure Ollama is running:  [bold]ollama serve[/bold]")
        console.print(f"Error: {e}")
        sys.exit(1)


def _print_welcome(agent):
    console.print()
    console.print(Panel.fit(
        "[bold cyan]Architecture Agent[/bold cyan]\n"
        "Autonomous AI with persistent memory and identity continuity\n\n"
        f"Model: [yellow]{config.MODEL} (Ollama)[/yellow]  |  "
        f"Priority memories: [yellow]{agent.pms.total_count()}[/yellow]  |  "
        f"Total turns: [yellow]{agent.inner_state.total_turns}[/yellow]\n\n"
        "Type [bold]/help[/bold] for commands  |  [bold]/quit[/bold] to exit",
        title="[bold]Session Start[/bold]",
        border_style="cyan"
    ))
    console.print()


def _handle_command(cmd: str, agent) -> bool:
    """Handle slash commands. Returns True if handled."""
    cmd = cmd.strip().lower()

    if cmd == "/quit" or cmd == "/exit":
        console.print("\n[cyan]Ending session and summarizing...[/cyan]")
        agent.end_session()
        console.print("[green]Session saved. Goodbye.[/green]")
        sys.exit(0)

    elif cmd == "/help":
        console.print(Panel(
            "/quit          — End session and exit\n"
            "/state         — Show current inner state\n"
            "/memories      — Show top priority memories\n"
            "/personality   — Show personality state\n"
            "/rules         — Show self-written rules\n"
            "/reflect       — Run daily reflection now\n"
            "/sessions      — Show recent session summaries\n"
            "/profile       — Show user profile",
            title="Commands", border_style="dim"
        ))
        return True

    elif cmd == "/state":
        console.print(Panel(agent.inner_state.to_context_string(), title="Inner State", border_style="blue"))
        return True

    elif cmd == "/memories":
        console.print(Panel(agent.pms.to_context_string(), title="Priority Memories", border_style="green"))
        return True

    elif cmd == "/personality":
        console.print(Panel(agent.personality.state_summary(), title="Personality State", border_style="magenta"))
        return True

    elif cmd == "/rules":
        from core import identity
        rules = identity.load_self_rules()
        text = "\n".join(f"• {r}" for r in rules) if rules else "No self-rules yet."
        console.print(Panel(text, title="Self-Written Rules", border_style="yellow"))
        return True

    elif cmd == "/reflect":
        console.print("[cyan]Running daily reflection...[/cyan]")
        try:
            from core.reflection import run_daily_reflection
            run_daily_reflection(agent.episodic, agent.semantic, agent.lmcs, agent.pms)
            console.print("[green]Reflection complete.[/green]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
        return True

    elif cmd == "/sessions":
        sessions = agent.episodic.recent_sessions(5)
        if sessions:
            lines = []
            for s in sessions:
                lines.append(f"[{s['start_ts'][:10]}] ({s['turn_count']} turns) {s['summary']}")
            console.print(Panel("\n".join(lines), title="Recent Sessions", border_style="dim"))
        else:
            console.print("[dim]No completed sessions yet.[/dim]")
        return True

    elif cmd == "/profile":
        console.print(Panel(agent.user_profile.profile_summary(), title="User Profile", border_style="blue"))
        return True

    return False


def main():
    _check_ollama()

    console.print("[dim]Initializing agent...[/dim]")
    from core.agent import Agent
    agent = Agent()

    def _on_exit(sig, frame):
        console.print("\n[cyan]Saving session...[/cyan]")
        agent.end_session()
        sys.exit(0)

    signal.signal(signal.SIGINT, _on_exit)

    _print_welcome(agent)

    conversation_history: list[dict] = []

    while True:
        try:
            user_input = Prompt.ask("[bold green]You[/bold green]")
        except (EOFError, KeyboardInterrupt):
            agent.end_session()
            break

        if not user_input.strip():
            continue

        if user_input.startswith("/"):
            if _handle_command(user_input, agent):
                continue

        console.print()
        with console.status("[cyan]Thinking...[/cyan]", spinner="dots"):
            response, conversation_history = agent.chat(user_input, conversation_history)

        console.print(Rule(style="dim"))
        console.print(Text("Agent", style="bold cyan") + Text(f" (turn {agent.inner_state.session_turn})"))
        console.print()
        console.print(response)
        console.print()


if __name__ == "__main__":
    main()
