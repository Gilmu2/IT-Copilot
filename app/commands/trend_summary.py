"""trend-summary command: AI trend summary from Intune snapshot."""

import json
import re
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from app.config import ConfigError
from app.graph_client import GraphClient, GraphClientError
from app.openai_client import OpenAIClient, OpenAIClientError

console = Console()

PERMISSION_MSG = "Insufficient Graph API permissions to perform this action. Contact admin."


def _load_prompt(name: str) -> str:
    """Load prompt from app/prompts/{name}.txt."""
    prompts_dir = Path(__file__).resolve().parent.parent / "prompts"
    return (prompts_dir / f"{name}.txt").read_text(encoding="utf-8").strip()


def _parse_trend_response(response: str) -> tuple[list[tuple[str, str, str]], str]:
    """Parse AI response into table rows (Trend, Insight, Suggested Action) and executive summary."""
    rows: list[tuple[str, str, str]] = []
    summary = ""

    # Find Executive Summary line
    summary_match = re.search(r"Executive Summary:\s*(.+?)(?:\n|$)", response, re.DOTALL | re.IGNORECASE)
    if summary_match:
        summary = summary_match.group(1).strip()

    # Find table-like content: lines with pipes (Trend | Insight | Suggested Action)
    lines = response.split("\n")
    for line in lines:
        line = line.strip()
        if "|" in line and not re.match(r"^[-|\s]+$", line):
            parts = [p.strip() for p in line.split("|")]
            if len(parts) >= 3:
                # Skip header row if it looks like column names
                if re.match(r"(?i)trend|insight|action", parts[0]) and re.match(r"(?i)trend|insight|action", parts[1]):
                    continue
                rows.append((parts[0], parts[1], parts[2]))

    return rows, summary


app = typer.Typer(help="AI trend summary from Intune devices, apps, and configs.")


@app.callback(invoke_without_command=True)
def trend_summary_cmd(
    save: bool = typer.Option(False, "--save", help="Save output to reports/trend_summary_<timestamp>.txt"),
) -> None:
    """Fetch Intune data, get AI trend summary (top 3 trends + executive summary)."""
    limitations: list[str] = []
    try:
        graph = GraphClient()
    except GraphClientError as e:
        console.print(f"[red]Graph error: {e}[/red]")
        raise typer.Exit(1)

    snapshot = graph._build_intune_snapshot(limitations=limitations, top=10000)
    if snapshot is None:
        console.print("[yellow]Graph data unavailable (all endpoints failed or no permission). Cannot generate trend summary.[/yellow]")
        raise typer.Exit(1)

    if limitations:
        console.print(f"[yellow]{PERMISSION_MSG}[/yellow]")

    payload = json.dumps(snapshot, default=str, indent=2)
    try:
        system_prompt = _load_prompt("trend_summary")
        client = OpenAIClient()
        response = client.generate_response(system_prompt, payload)
    except ConfigError as e:
        console.print(f"[red]Configuration error: {e}[/red]")
        raise typer.Exit(1)
    except OpenAIClientError as e:
        console.print(f"[red]OpenAI / Azure OpenAI error: {e}[/red]")
        raise typer.Exit(1)

    rows, executive_summary = _parse_trend_response(response)

    if rows:
        table = Table(title="Top trends")
        table.add_column("Trend", style="cyan")
        table.add_column("Insight", style="green")
        table.add_column("Suggested Action", style="yellow")
        for trend, insight, action in rows:
            table.add_row(trend, insight, action)
        console.print(table)
    else:
        console.print(Panel(response, title="Trend summary", border_style="blue"))

    if executive_summary:
        console.print(Panel(executive_summary, title="Executive Summary", border_style="blue"))

    if save:
        reports_dir = Path("reports")
        reports_dir.mkdir(exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = reports_dir / f"trend_summary_{ts}.txt"
        out_path.write_text(response, encoding="utf-8")
        console.print(f"[green]Saved to {out_path}[/green]")
