"""doc-intune command: AI-generated documentation from Intune snapshot (Phase 10: executive, audit, sop, compliance-gap)."""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Literal

import typer
from rich.console import Console
from rich.panel import Panel

from app.config import ConfigError
from app.graph_client import GraphClient, GraphClientError
from app.openai_client import OpenAIClient, OpenAIClientError

console = Console()

PERMISSION_MSG = "Insufficient Graph API permissions to perform this action. Contact admin."

ReportType = Literal["executive", "audit", "sop", "compliance-gap"]

PROMPT_MAP: dict[ReportType, str] = {
    "executive": "doc_executive",
    "audit": "doc_audit",
    "sop": "doc_sop",
    "compliance-gap": "doc_compliance_gap",
}


def _load_prompt(name: str) -> str:
    """Load prompt from app/prompts/{name}.txt."""
    prompts_dir = Path(__file__).resolve().parent.parent / "prompts"
    return (prompts_dir / f"{name}.txt").read_text(encoding="utf-8").strip()


def _parse_sections(ai_text: str) -> list[tuple[str, str]]:
    """
    Parse AI response by splitting on lines starting with ##.
    Returns list of (title, content) tuples. Content is stripped; leading/trailing blank lines removed.
    """
    sections: list[tuple[str, str]] = []
    pattern = re.compile(r"^##\s+(.+)$", re.MULTILINE)
    matches = list(pattern.finditer(ai_text))
    for i, m in enumerate(matches):
        title = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(ai_text)
        content = ai_text[start:end].strip()
        sections.append((title, content))
    if not sections and ai_text.strip():
        sections.append(("Report", ai_text.strip()))
    return sections


def _render_sections(sections: list[tuple[str, str]], border_style: str = "blue") -> None:
    """Render each (title, content) as a Rich panel."""
    for title, content in sections:
        if content:
            console.print(Panel(content, title=title, border_style=border_style))


def _strip_rich_markup(text: str) -> str:
    """Remove Rich/ANSI-style markup so saved file is plain text."""
    return re.sub(r"\[/?[^\]]*\]", "", text)


def _save_report(plain_text: str, report_type: ReportType) -> Path:
    """Write plain text to reports/doc_<type>_YYYYMMDD_HHMMSS.txt. Creates reports/ if needed. Returns path."""
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = reports_dir / f"doc_{report_type}_{ts}.txt"
    out_path.write_text(_strip_rich_markup(plain_text), encoding="utf-8")
    return out_path


def doc_intune_cmd(
    report_type: ReportType = typer.Option(
        "executive",
        "--type",
        help="Report type: executive, audit, sop, or compliance-gap.",
    ),
    save: bool = typer.Option(False, "--save", help="Save output to reports/doc_<type>_<timestamp>.txt."),
    top: int = typer.Option(10000, "--top", help="Max devices, apps, and configs to fetch for snapshot (uses pagination for 3k+)."),
) -> None:
    """Generate AI documentation from Intune snapshot. Default --type executive (executive summary)."""
    limitations: list[str] = []
    try:
        graph = GraphClient()
    except GraphClientError as e:
        console.print(f"[red]Graph error: {e}[/red]")
        raise typer.Exit(1)

    snapshot = graph._build_intune_snapshot(limitations=limitations, top=top)
    if snapshot is None:
        console.print(
            "[yellow]Graph data unavailable (all endpoints failed or no permission). Cannot generate report.[/yellow]"
        )
        raise typer.Exit(1)

    if limitations:
        console.print(f"[yellow]{PERMISSION_MSG}[/yellow]")

    prompt_name = PROMPT_MAP[report_type]
    payload = json.dumps(snapshot, default=str, indent=2)
    try:
        system_prompt = _load_prompt(prompt_name)
        client = OpenAIClient()
        ai_text = client.generate_response(system_prompt, payload)
    except ConfigError as e:
        console.print(f"[red]Configuration error: {e}[/red]")
        raise typer.Exit(1)
    except OpenAIClientError as e:
        console.print(f"[red]OpenAI / Azure OpenAI error: {e}[/red]")
        raise typer.Exit(1)

    if report_type == "executive":
        console.print(Panel(ai_text.strip(), title="Executive Summary", border_style="blue"))
    else:
        sections = _parse_sections(ai_text)
        _render_sections(sections, border_style="blue")

    if save:
        out_path = _save_report(ai_text, report_type)
        console.print(f"[green]Saved to {out_path}[/green]")
