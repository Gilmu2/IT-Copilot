"""check-permissions command: probe Graph endpoints and report status (Phase 12)."""

import re
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

from app.config import ConfigError, get_config
from app.graph_client import ENDPOINT_REGISTRY, GraphClient, GraphClientError

console = Console()


def _short_endpoint(endpoint: str) -> str:
    """Short display for endpoint (last path segment or truncated)."""
    if "/" in endpoint:
        return endpoint.split("/")[-1] or endpoint
    return endpoint[:40] + ("..." if len(endpoint) > 40 else "")


def _strip_rich_markup(text: str) -> str:
    """Remove Rich-style markup for plain-text save."""
    return re.sub(r"\[/?[^\]]*\]", "", text)


def _save_report(
    rows: list[tuple[str, str, str, str]],
    summary: str,
    timestamp: str,
    tenant_preview: str,
) -> Path:
    """Write plain-text report to reports/check_permissions_YYYYMMDD_HHMMSS.txt."""
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = reports_dir / f"check_permissions_{ts}.txt"
    lines = ["Graph Permission Check", "", "Permission Area\tEndpoint\tStatus\tNotes", ""]
    for area, endpoint, status, notes in rows:
        lines.append(f"{area}\t{_short_endpoint(endpoint)}\t{_strip_rich_markup(status)}\t{notes}")
    lines.extend(["", summary, "", f"Probed at {timestamp} | Tenant: {tenant_preview}"])
    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


app = typer.Typer(
    invoke_without_command=True,
    help="Probe Graph API endpoints and report permission status (Phase 12).",
)


@app.callback(invoke_without_command=True)
def check_permissions_cmd(
    save: bool = typer.Option(False, "--save", help="Save report to reports/check_permissions_<timestamp>.txt."),
) -> None:
    """Probe all registered Graph endpoints and display availability (200), denied (403), or error."""
    try:
        client = GraphClient()
        tenant_id = get_config().azure_tenant_id or ""
        tenant_preview = (tenant_id[:8] + "...") if len(tenant_id) > 8 else (tenant_id or "—")
    except (ConfigError, GraphClientError) as e:
        console.print(f"[red]Graph is not configured or failed: {e}[/red]")
        raise typer.Exit(1)

    console.print(Rule("Graph Permission Check", style="blue"))

    table = Table(title="Endpoint status")
    table.add_column("Permission Area", style="cyan")
    table.add_column("Endpoint", style="dim")
    table.add_column("Status", style="bold")
    table.add_column("Notes", style="green")

    rows: list[tuple[str, str, str, str]] = []
    available_count = denied_count = error_count = 0
    granted_statuses: list[str] = []

    for i, entry in enumerate(ENDPOINT_REGISTRY):
        area = entry.get("area", "—")
        endpoint = entry.get("endpoint", "")
        status, notes = client.probe_endpoint(entry)

        if entry.get("currently_granted"):
            granted_statuses.append(status)
        if status == "Available":
            status_text = "[green]✓ Available[/green]"
            available_count += 1
        elif status == "Denied":
            status_text = "[red]✗ Denied[/red]"
            denied_count += 1
        else:
            status_text = "[yellow]⚠ Error[/yellow]"
            error_count += 1

        row_style = "dim" if i % 2 else None
        table.add_row(
            area,
            _short_endpoint(endpoint),
            status_text,
            notes,
            style=row_style,
        )
        rows.append((area, _short_endpoint(endpoint), status_text, notes))

    console.print(table)

    n = len(ENDPOINT_REGISTRY)
    summary = f"Checked {n} endpoints. Available: {available_count}  |  Denied: {denied_count}  |  Errors: {error_count}"
    all_granted_ok = all(s == "Available" for s in granted_statuses) if granted_statuses else True
    panel_border = "green" if all_granted_ok else "yellow"
    console.print(Panel(summary, border_style=panel_border))

    probed_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    console.print(f"[dim]Probed at {probed_at} | Tenant: {tenant_preview}[/dim]")

    if save:
        out_path = _save_report(rows, summary, probed_at, tenant_preview)
        console.print(f"[green]Saved to {out_path}[/green]")
