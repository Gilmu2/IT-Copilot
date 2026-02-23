"""AI-driven Graph analysis commands: analyze-user, analyze-device, audit-intune."""

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from app.config import ConfigError
from app.graph_client import GraphClient, GraphClientError, _is_403, _safe_graph
from app.openai_client import OpenAIClient, OpenAIClientError

console = Console()

PERMISSION_MSG = "Insufficient Graph API permissions to perform this action. Contact admin."


def analyze_user_cmd(
    user: str = typer.Argument(..., help="User principal name, display name, or identifier to look up."),
    top: int = typer.Option(100, "--top", help="Max devices/users to fetch for lookup."),
) -> None:
    """Fetch user and device data from Graph, then produce an AI summary report."""
    limitations: list[str] = []
    try:
        graph = GraphClient()
    except GraphClientError as e:
        console.print(f"[red]Graph error: {e}[/red]")
        raise typer.Exit(1)

    user_info: dict | None = None
    users_data = _safe_graph(lambda: graph.get_users(top=top), default={}, limitations=limitations)
    if users_data and not limitations:
        value = users_data.get("value") or []
        for u in value:
            upn = (u.get("userPrincipalName") or "").lower()
            disp = (u.get("displayName") or "").lower()
            if user.lower() in upn or user.lower() in disp or user == u.get("id", ""):
                user_info = u
                break

    devices_data = _safe_graph(
        lambda: graph.get_managed_devices(top=min(top, 10000)),
        default={"value": []},
        limitations=limitations,
    )
    devices = (devices_data or {}).get("value") or []
    user_lower = user.lower()
    matching = [
        d for d in devices
        if user_lower in (d.get("userPrincipalName") or "").lower()
        or user_lower in (d.get("userDisplayName") or "").lower()
        or user == d.get("id", "")
    ]

    payload = {
        "query_user": user,
        "user_info": user_info,
        "managed_devices_count": len(matching),
        "managed_devices": matching[:20],
        "limitations": limitations,
    }
    if limitations:
        payload["limitation_note"] = PERMISSION_MSG

    try:
        system_prompt = _load_prompt("analyze_user")
        ai = OpenAIClient()
        summary = ai.generate_response(system_prompt, json.dumps(payload, default=str, indent=2))
    except ConfigError as e:
        console.print(f"[red]Configuration error: {e}[/red]")
        raise typer.Exit(1)
    except OpenAIClientError as e:
        console.print(f"[red]OpenAI / Azure OpenAI error: {e}[/red]")
        raise typer.Exit(1)

    if matching:
        table = Table(title="Managed devices for user")
        table.add_column("Device name", style="cyan")
        table.add_column("Model", style="green")
        table.add_column("OS", style="yellow")
        table.add_column("Status", style="dim")
        for d in matching[:10]:
            table.add_row(
                d.get("deviceName") or "",
                d.get("model") or "",
                d.get("operatingSystem") or "",
                d.get("managedDeviceStatus") or "",
            )
        console.print(table)
    if limitations:
        console.print(f"[yellow]{PERMISSION_MSG}[/yellow]")
    console.print(Panel(summary, title="AI summary", border_style="blue"))


def analyze_device_cmd(
    device_id: str = typer.Argument(..., help="Intune managed device ID."),
) -> None:
    """Fetch a single managed device from Graph and produce an AI executive summary."""
    try:
        graph = GraphClient()
    except GraphClientError as e:
        console.print(f"[red]Graph error: {e}[/red]")
        raise typer.Exit(1)
    limitations: list[str] = []
    device = _safe_graph(
        lambda: graph.get_managed_device(device_id),
        default=None,
        limitations=limitations,
    )
    if device is None:
        if limitations and any("403" in m for m in limitations):
            console.print(f"[yellow]{PERMISSION_MSG}[/yellow]")
        else:
            console.print("[yellow]Device not found or inaccessible.[/yellow]")
        raise typer.Exit(1)

    try:
        system_prompt = _load_prompt("analyze_device")
        ai = OpenAIClient()
        summary = ai.generate_response(system_prompt, json.dumps(device, default=str, indent=2))
    except ConfigError as e:
        console.print(f"[red]Configuration error: {e}[/red]")
        raise typer.Exit(1)
    except OpenAIClientError as e:
        console.print(f"[red]OpenAI / Azure OpenAI error: {e}[/red]")
        raise typer.Exit(1)

    table = Table(title="Device details")
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")
    for key in ("deviceName", "model", "operatingSystem", "managedDeviceStatus", "complianceState", "deviceEnrollmentType"):
        if key in device and device[key] is not None:
            table.add_row(key, str(device[key]))
    console.print(table)
    console.print(Panel(summary, title="AI summary", border_style="blue"))


def audit_intune_cmd(
    top: int = typer.Option(100, "--top", help="Max devices, apps, and configs to fetch."),
) -> None:
    """Aggregate Intune devices, apps, and configurations; produce an AI audit summary."""
    limitations: list[str] = []
    try:
        graph = GraphClient()
    except GraphClientError as e:
        console.print(f"[red]Graph error: {e}[/red]")
        raise typer.Exit(1)

    devices_data = _safe_graph(lambda: graph.get_managed_devices(top=top), default={"value": []}, limitations=limitations)
    devices = devices_data.get("value") or []

    apps_data = _safe_graph(lambda: graph.get_mobile_apps(top=top), default={"value": []}, limitations=limitations)
    apps = apps_data.get("value") or []

    configs_data = _safe_graph(lambda: graph.get_device_configurations(top=top), default={"value": []}, limitations=limitations)
    configs = configs_data.get("value") or []

    # Build rich payload for AI: top apps, config list, device breakdown by OS/compliance
    app_summary = [{"displayName": a.get("displayName"), "@odata.type": a.get("@odata.type")} for a in apps[:50]]
    config_summary = [{"displayName": c.get("displayName"), "id": c.get("id")} for c in configs[:50]]
    os_counts: dict[str, int] = {}
    compliance_counts: dict[str, int] = {}
    for d in devices:
        os_name = d.get("operatingSystem") or "Unknown"
        os_counts[os_name] = os_counts.get(os_name, 0) + 1
        comp = d.get("complianceState") or "unknown"
        compliance_counts[comp] = compliance_counts.get(comp, 0) + 1

    payload = {
        "managed_devices_count": len(devices),
        "mobile_apps_count": len(apps),
        "device_configurations_count": len(configs),
        "devices_by_os": os_counts,
        "devices_by_compliance": compliance_counts,
        "mobile_apps_sample": app_summary,
        "device_configurations_sample": config_summary,
        "limitations": limitations,
    }
    if limitations:
        payload["limitation_note"] = PERMISSION_MSG

    try:
        system_prompt = _load_prompt("audit_intune")
        ai = OpenAIClient()
        summary = ai.generate_response(system_prompt, json.dumps(payload, default=str, indent=2))
    except ConfigError as e:
        console.print(f"[red]Configuration error: {e}[/red]")
        raise typer.Exit(1)
    except OpenAIClientError as e:
        console.print(f"[red]OpenAI / Azure OpenAI error: {e}[/red]")
        raise typer.Exit(1)

    table = Table(title="Intune audit counts")
    table.add_column("Resource", style="cyan")
    table.add_column("Count", style="green")
    table.add_row("Managed devices", str(len(devices)))
    table.add_row("Mobile apps", str(len(apps)))
    table.add_row("Device configurations", str(len(configs)))
    console.print(table)
    if limitations:
        console.print(f"[yellow]{PERMISSION_MSG}[/yellow]")
    console.print(Panel(summary, title="AI audit summary", border_style="blue"))


def list_apps_cmd(
    top: int = typer.Option(100, "--top", help="Max mobile apps to fetch."),
) -> None:
    """List Intune mobile apps with an AI summary (deployment coverage, gaps)."""
    limitations: list[str] = []
    try:
        graph = GraphClient()
    except GraphClientError as e:
        console.print(f"[red]Graph error: {e}[/red]")
        raise typer.Exit(1)

    apps_data = _safe_graph(lambda: graph.get_mobile_apps(top=top), default={"value": []}, limitations=limitations)
    apps = apps_data.get("value") or []

    payload = {"mobile_apps_count": len(apps), "mobile_apps": apps[:50], "limitations": limitations}
    if limitations:
        payload["limitation_note"] = PERMISSION_MSG

    try:
        system_prompt = _load_prompt("list_apps")
        ai = OpenAIClient()
        summary = ai.generate_response(system_prompt, json.dumps(payload, default=str, indent=2))
    except ConfigError as e:
        console.print(f"[red]Configuration error: {e}[/red]")
        raise typer.Exit(1)
    except OpenAIClientError as e:
        console.print(f"[red]OpenAI / Azure OpenAI error: {e}[/red]")
        raise typer.Exit(1)

    table = Table(title="Mobile apps")
    table.add_column("Display name", style="cyan")
    table.add_column("Type", style="green")
    for a in apps[:20]:
        table.add_row(a.get("displayName") or "", (a.get("@odata.type") or "").replace("#microsoft.graph.", ""))
    console.print(table)
    if limitations:
        console.print(f"[yellow]{PERMISSION_MSG}[/yellow]")
    console.print(Panel(summary, title="AI summary", border_style="blue"))


def list_configs_cmd(
    top: int = typer.Option(100, "--top", help="Max device configurations to fetch."),
) -> None:
    """List Intune device configurations with an AI summary (coverage, gaps)."""
    limitations: list[str] = []
    try:
        graph = GraphClient()
    except GraphClientError as e:
        console.print(f"[red]Graph error: {e}[/red]")
        raise typer.Exit(1)

    configs_data = _safe_graph(
        lambda: graph.get_device_configurations(top=top), default={"value": []}, limitations=limitations
    )
    configs = configs_data.get("value") or []

    payload = {"device_configurations_count": len(configs), "device_configurations": configs[:50], "limitations": limitations}
    if limitations:
        payload["limitation_note"] = PERMISSION_MSG

    try:
        system_prompt = _load_prompt("list_configs")
        ai = OpenAIClient()
        summary = ai.generate_response(system_prompt, json.dumps(payload, default=str, indent=2))
    except ConfigError as e:
        console.print(f"[red]Configuration error: {e}[/red]")
        raise typer.Exit(1)
    except OpenAIClientError as e:
        console.print(f"[red]OpenAI / Azure OpenAI error: {e}[/red]")
        raise typer.Exit(1)

    table = Table(title="Device configurations")
    table.add_column("Display name", style="cyan")
    table.add_column("Id", style="dim")
    for c in configs[:20]:
        table.add_row(c.get("displayName") or "", (c.get("id") or "")[:36])
    console.print(table)
    if limitations:
        console.print(f"[yellow]{PERMISSION_MSG}[/yellow]")
    console.print(Panel(summary, title="AI summary", border_style="blue"))


