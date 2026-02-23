"""Graph command group: users, devices, groups (Microsoft Graph)."""

import typer
from rich.console import Console
from rich.table import Table

from app.graph_client import GraphClient, GraphClientError, _safe_graph

console = Console()

PERMISSION_MSG = "Insufficient Graph API permissions to perform this action. Contact admin."

app = typer.Typer(
    help="Microsoft Graph: users, Intune devices, groups (requires Azure app registration).",
)


@app.command("users")
def users_cmd(
    top: int = typer.Option(10, "--top", help="Maximum number of users to return."),
) -> None:
    """List users from Microsoft Graph."""
    try:
        client = GraphClient()
    except GraphClientError as e:
        console.print(f"[red]Graph error: {e}[/red]")
        raise typer.Exit(1)
    limitations: list[str] = []
    data = _safe_graph(lambda: client.get_users(top=top), default={"value": []}, limitations=limitations)
    if limitations:
        console.print(f"[yellow]{PERMISSION_MSG}[/yellow]")

    value = (data or {}).get("value") or []
    if not value:
        console.print("[dim]No users returned.[/dim]")
        return

    table = Table(title="Users")
    table.add_column("Display Name", style="cyan")
    table.add_column("User Principal Name", style="green")
    table.add_column("Id", style="dim")
    for u in value:
        table.add_row(
            u.get("displayName") or "",
            u.get("userPrincipalName") or "",
            u.get("id") or "",
        )
    console.print(table)


@app.command("devices")
def devices_cmd(
    top: int = typer.Option(10, "--top", help="Maximum number of devices to return."),
) -> None:
    """List Intune managed devices from Microsoft Graph."""
    try:
        client = GraphClient()
    except GraphClientError as e:
        console.print(f"[red]Graph error: {e}[/red]")
        raise typer.Exit(1)
    limitations: list[str] = []
    data = _safe_graph(lambda: client.get_managed_devices(top=top), default={"value": []}, limitations=limitations)
    if limitations:
        console.print(f"[yellow]{PERMISSION_MSG}[/yellow]")

    value = (data or {}).get("value") or []
    if not value:
        console.print("[dim]No managed devices returned.[/dim]")
        return

    table = Table(title="Managed Devices (Intune)")
    table.add_column("Device Name", style="cyan")
    table.add_column("Model", style="green")
    table.add_column("OS", style="yellow")
    table.add_column("Status", style="dim")
    for d in value:
        table.add_row(
            d.get("deviceName") or "",
            d.get("model") or "",
            d.get("operatingSystem") or "",
            d.get("managedDeviceStatus") or "",
        )
    console.print(table)


@app.command("groups")
def groups_cmd(
    top: int = typer.Option(10, "--top", help="Maximum number of groups to return."),
) -> None:
    """List groups from Microsoft Graph."""
    try:
        client = GraphClient()
    except GraphClientError as e:
        console.print(f"[red]Graph error: {e}[/red]")
        raise typer.Exit(1)
    limitations: list[str] = []
    data = _safe_graph(lambda: client.get_groups(top=top), default={"value": []}, limitations=limitations)
    if limitations:
        console.print(f"[yellow]{PERMISSION_MSG}[/yellow]")

    value = (data or {}).get("value") or []
    if not value:
        console.print("[dim]No groups returned.[/dim]")
        return

    table = Table(title="Groups")
    table.add_column("Display Name", style="cyan")
    table.add_column("Id", style="dim")
    for g in value:
        table.add_row(g.get("displayName") or "", g.get("id") or "")
    console.print(table)
