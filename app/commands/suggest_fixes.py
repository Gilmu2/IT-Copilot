"""suggest-fixes command: AI remediation suggestions from Intune snapshot."""

import json
import re
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from app.config import ConfigError
from app.graph_client import GraphClient, GraphClientError
from app.openai_client import OpenAIClient, OpenAIClientError

console = Console()

PERMISSION_MSG = "Insufficient Graph API permissions to perform this action. Contact admin."


def _load_prompt(name: str) -> str:
    """Load prompt from app/prompts/{name}.txt."""
    prompts_dir = Path(__file__).resolve().parent.parent / "prompts"
    return (prompts_dir / f"{name}.txt").read_text(encoding="utf-8").strip()


def _section_text(content: str, header: str) -> str:
    """Extract text under a ## header until the next ## or end."""
    pattern = rf"##\s*{re.escape(header)}\s*\n(.*?)(?=##\s|\Z)"
    match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
    return match.group(1).strip() if match else ""


app = typer.Typer(help="AI remediation suggestions from Intune devices, apps, and configs.")


@app.callback(invoke_without_command=True)
def suggest_fixes_cmd(
    save: bool = typer.Option(False, "--save", help="Save output to reports/suggest_fixes_<timestamp>.txt"),
) -> None:
    """Fetch Intune data, get AI remediation suggestions, and display as Immediate Actions / Self-Remediation / Escalation."""
    limitations: list[str] = []
    try:
        graph = GraphClient()
    except GraphClientError as e:
        console.print(f"[red]Graph error: {e}[/red]")
        raise typer.Exit(1)

    snapshot = graph._build_intune_snapshot(limitations=limitations, top=10000)
    if snapshot is None:
        console.print("[yellow]Graph data unavailable (all endpoints failed or no permission). Cannot generate suggestions.[/yellow]")
        raise typer.Exit(1)

    if limitations:
        console.print(f"[yellow]{PERMISSION_MSG}[/yellow]")

    payload = json.dumps(snapshot, default=str, indent=2)
    try:
        system_prompt = _load_prompt("suggest_fixes")
        client = OpenAIClient()
        response = client.generate_response(system_prompt, payload)
    except ConfigError as e:
        console.print(f"[red]Configuration error: {e}[/red]")
        raise typer.Exit(1)
    except OpenAIClientError as e:
        console.print(f"[red]OpenAI / Azure OpenAI error: {e}[/red]")
        raise typer.Exit(1)

    immediate = _section_text(response, "Immediate Actions")
    self_remed = _section_text(response, "Self-Remediation")
    escalation = _section_text(response, "Escalation Required")

    if immediate:
        console.print(Panel(immediate, title="Immediate Actions", border_style="red"))
    if self_remed:
        console.print(Panel(self_remed, title="Self-Remediation", border_style="green"))
    if escalation:
        console.print(Panel(escalation, title="Escalation Required", border_style="yellow"))
    if not (immediate or self_remed or escalation):
        console.print(Panel(response, title="Remediation Suggestions", border_style="blue"))

    if save:
        reports_dir = Path("reports")
        reports_dir.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = reports_dir / f"suggest_fixes_{ts}.txt"
        out_path.write_text(response, encoding="utf-8")
        console.print(f"[green]Saved to {out_path}[/green]")
