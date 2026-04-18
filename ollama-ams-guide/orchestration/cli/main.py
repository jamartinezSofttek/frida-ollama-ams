"""
CLI Interface for the Architect-Engineer Orchestration Framework
AMS L3 – Local AI Pipeline

Usage:
    python cli/main.py query "Analiza este stack trace..."
    python cli/main.py chat
    python cli/main.py file path/to/task.txt
    python cli/main.py sessions
    python cli/main.py export <session_id>

Run from the orchestration/ directory:
    cd ollama-ams-guide/orchestration
    python cli/main.py --help
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

# Ensure the orchestration/ directory is on sys.path so imports work
_ORCHESTRATION_DIR = Path(__file__).resolve().parent.parent
if str(_ORCHESTRATION_DIR) not in sys.path:
    sys.path.insert(0, str(_ORCHESTRATION_DIR))

import yaml
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from orchestrator import Orchestrator, OrchestratorResult
from memory.session_store import SessionStore
from router import build_router_from_config

console = Console()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = str(_ORCHESTRATION_DIR / "config.yaml")
BANNER = """
╔══════════════════════════════════════════════════════╗
║   🤖  Ollama AMS L3 – Architect-Engineer Pipeline    ║
║   Local AI Orchestration | Token-Saving Mode         ║
╚══════════════════════════════════════════════════════╝
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_config(config_path: str) -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _print_result(result: OrchestratorResult, verbose: bool = False) -> None:
    """Render an OrchestratorResult to the terminal using Rich."""
    console.print()
    console.print(Rule("[bold cyan]Resultado del Pipeline[/bold cyan]"))
    console.print(Markdown(result.summary))

    if verbose and result.details:
        console.print()
        console.print(Rule("[dim]Detalles por Subtarea[/dim]"))
        for detail in result.details:
            title = f"[bold]{detail['type']}[/bold] · {detail['model']} · conf: {detail.get('confidence','?')}"
            console.print(Panel(
                detail.get("finding", ""),
                title=title,
                border_style="dim",
                expand=False,
            ))

    console.print()
    # Stats footer
    stats = (
        f"[dim]⏱ {result.total_duration_seconds}s  "
        f"🔢 {result.total_tokens_used} tokens locales  "
        f"🗂 sesión: {result.session_id[:8]}...[/dim]"
    )
    console.print(stats)

    if result.warnings:
        for w in result.warnings:
            console.print(f"[yellow]⚠ {w}[/yellow]")


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_query(args: argparse.Namespace) -> None:
    """Execute a single query and print the result."""
    task = args.task
    if not task.strip():
        console.print("[red]Error: la tarea no puede estar vacía.[/red]")
        sys.exit(1)

    orchestrator = Orchestrator(config_path=args.config)
    session_id = args.session or None
    use_llm = not args.no_architect

    console.print(f"\n[bold cyan]Tarea:[/bold cyan] {task[:120]}")
    console.print("[dim]Procesando...[/dim]\n")

    result = orchestrator.run(task, session_id=session_id, use_architect_llm=use_llm)
    _print_result(result, verbose=args.verbose)

    if args.json:
        print(Orchestrator.result_to_json(result))


def cmd_chat(args: argparse.Namespace) -> None:
    """Interactive multi-turn chat session."""
    console.print(Panel(BANNER.strip(), style="bold blue"))

    orchestrator = Orchestrator(config_path=args.config)
    use_llm = not args.no_architect

    # Resume or start session
    if args.session:
        session_id = args.session
        console.print(f"[green]Retomando sesión:[/green] {session_id}")
    else:
        session_id = orchestrator.session_store.create_session()
        console.print(f"[green]Nueva sesión:[/green] {session_id}")

    console.print("[dim]Escribe tu tarea y presiona Enter. Comandos: /exit /sesion /limpiar[/dim]\n")

    while True:
        try:
            task = Prompt.ask("[bold cyan]AMS L3[/bold cyan]")
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Sesión terminada.[/dim]")
            break

        if not task.strip():
            continue

        # Built-in commands
        if task.lower() in ("/exit", "/salir", "/quit"):
            console.print("[dim]Sesión guardada. ¡Hasta pronto![/dim]")
            break
        if task.lower() in ("/sesion", "/session"):
            console.print(f"[dim]Session ID: {session_id}[/dim]")
            continue
        if task.lower() in ("/limpiar", "/clear"):
            console.clear()
            continue
        if task.lower().startswith("/export"):
            parts = task.split(maxsplit=1)
            out_path = parts[1] if len(parts) > 1 else None
            md = orchestrator.session_store.export_session(session_id, out_path)
            if not out_path:
                console.print(Markdown(md))
            else:
                console.print(f"[green]Sesión exportada a:[/green] {out_path}")
            continue

        console.print("[dim]Procesando...[/dim]")
        result = orchestrator.run(task, session_id=session_id, use_architect_llm=use_llm)
        _print_result(result, verbose=args.verbose)


def cmd_file(args: argparse.Namespace) -> None:
    """Read a task from a text file and execute it."""
    task_path = Path(args.file)
    if not task_path.exists():
        console.print(f"[red]Archivo no encontrado:[/red] {args.file}")
        sys.exit(1)

    task = task_path.read_text(encoding="utf-8").strip()
    if not task:
        console.print("[red]El archivo está vacío.[/red]")
        sys.exit(1)

    console.print(f"[bold]Archivo:[/bold] {args.file}")
    console.print(f"[dim]{task[:200]}...[/dim]\n" if len(task) > 200 else f"[dim]{task}[/dim]\n")

    orchestrator = Orchestrator(config_path=args.config)
    result = orchestrator.run(task, session_id=args.session, use_architect_llm=not args.no_architect)
    _print_result(result, verbose=args.verbose)

    if args.output:
        out = Path(args.output)
        out.write_text(result.summary, encoding="utf-8")
        console.print(f"[green]Resultado guardado en:[/green] {args.output}")

    if args.json:
        print(Orchestrator.result_to_json(result))


def cmd_sessions(args: argparse.Namespace) -> None:
    """List all stored sessions."""
    config = _load_config(args.config)
    store = SessionStore(config["memory"])
    sessions = store.list_sessions()

    if not sessions:
        console.print("[dim]No hay sesiones guardadas.[/dim]")
        return

    table = Table(title="Sesiones Guardadas", show_lines=True)
    table.add_column("ID", style="cyan", no_wrap=True)
    table.add_column("Creada", style="dim")
    table.add_column("Actualizada", style="dim")
    table.add_column("Turnos", justify="right")

    for s in sessions:
        table.add_row(
            s["session_id"][:36],
            s["created_at"][:19].replace("T", " "),
            s["updated_at"][:19].replace("T", " "),
            str(s["turns"]),
        )

    console.print(table)


def cmd_export(args: argparse.Namespace) -> None:
    """Export a session to Markdown."""
    config = _load_config(args.config)
    store = SessionStore(config["memory"])
    md = store.export_session(args.session_id, args.output)

    if not args.output:
        console.print(Markdown(md))
    else:
        console.print(f"[green]Sesión exportada a:[/green] {args.output}")


def cmd_route(args: argparse.Namespace) -> None:
    """Show routing analysis for a task without executing it."""
    config = _load_config(args.config)
    router = build_router_from_config(config)
    explanation = router.explain(args.task)
    console.print(Panel(explanation, title="[bold]Routing Analysis[/bold]", style="dim"))


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ams-ai",
        description="Ollama AMS L3 Architect-Engineer CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python cli/main.py query "Analiza este stack trace de Java..."
  python cli/main.py chat
  python cli/main.py chat --session abc123
  python cli/main.py file tasks/incidente.txt --output resultado.md
  python cli/main.py sessions
  python cli/main.py export abc123 --output sesion.md
  python cli/main.py route "revisa este script python con un bug"
        """,
    )

    parser.add_argument(
        "--config", default=DEFAULT_CONFIG,
        help=f"Path to config.yaml (default: {DEFAULT_CONFIG})"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Show per-subtask details in output"
    )
    parser.add_argument(
        "--no-architect", action="store_true",
        help="Skip architect LLM decomposition; use keyword routing instead"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- query ---
    p_query = subparsers.add_parser("query", help="Execute a single task")
    p_query.add_argument("task", help="Task description")
    p_query.add_argument("--session", help="Resume an existing session ID")
    p_query.add_argument("--json", action="store_true", help="Also print JSON output")
    p_query.set_defaults(func=cmd_query)

    # --- chat ---
    p_chat = subparsers.add_parser("chat", help="Interactive multi-turn session")
    p_chat.add_argument("--session", help="Resume an existing session ID")
    p_chat.set_defaults(func=cmd_chat)

    # --- file ---
    p_file = subparsers.add_parser("file", help="Execute a task from a text file")
    p_file.add_argument("file", help="Path to task .txt file")
    p_file.add_argument("--session", help="Resume an existing session ID")
    p_file.add_argument("--output", help="Save Markdown result to this file")
    p_file.add_argument("--json", action="store_true", help="Also print JSON output")
    p_file.set_defaults(func=cmd_file)

    # --- sessions ---
    p_sessions = subparsers.add_parser("sessions", help="List saved sessions")
    p_sessions.set_defaults(func=cmd_sessions)

    # --- export ---
    p_export = subparsers.add_parser("export", help="Export a session to Markdown")
    p_export.add_argument("session_id", help="Session ID to export")
    p_export.add_argument("--output", help="Save to this file path")
    p_export.set_defaults(func=cmd_export)

    # --- route ---
    p_route = subparsers.add_parser("route", help="Show routing analysis without executing")
    p_route.add_argument("task", help="Task description to analyze")
    p_route.set_defaults(func=cmd_route)

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    # Silence root logger unless DEBUG requested via env var
    log_level = os.environ.get("AMS_LOG_LEVEL", "WARNING").upper()
    logging.basicConfig(level=getattr(logging, log_level, logging.WARNING))

    try:
        args.func(args)
    except FileNotFoundError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[dim]Interrumpido por el usuario.[/dim]")
        sys.exit(0)
    except Exception as exc:
        console.print(f"[red]Error inesperado:[/red] {exc}")
        if log_level == "DEBUG":
            raise
        sys.exit(1)


if __name__ == "__main__":
    main()
