"""Copilot command: IT assistant for Azure, Intune, PowerShell, etc."""

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from app.config import ConfigError
from app.openai_client import OpenAIClient, OpenAIClientError

console = Console()

app = typer.Typer(
    invoke_without_command=True,
    help="IT assistant for Azure, Entra ID, Intune, Windows, PowerShell.",
)

INTRUNE_KEYWORDS = (
    "intune",
    "device",
    "compliance",
    "mdm",
    "endpoint",
    "app deployment",
    "configuration",
    "managed",
)


def _load_prompt(name: str) -> str:
    """Load prompt from app/prompts/{name}.txt."""
    prompts_dir = Path(__file__).resolve().parent.parent / "prompts"
    return (prompts_dir / f"{name}.txt").read_text(encoding="utf-8").strip()


def _get_intune_system_context(prompt: str) -> tuple[str, bool]:
    """
    If prompt contains Intune-related keywords, fetch lightweight snapshot and return
    (context_block, included). If no keyword match or fetch fails, return ("", False).
    """
    if not any(k in prompt.lower() for k in INTRUNE_KEYWORDS):
        return "", False
    try:
        from app.graph_client import GraphClient

        graph = GraphClient()
        limitations: list[str] = []
        snapshot = graph._build_intune_snapshot(limitations=limitations, top=10000)
        if snapshot is None:
            return "", False
        lines = [
            "Current Intune environment snapshot (for context only):",
            f"- Total managed devices: {snapshot.get('total_devices', 0)}",
            f"- Compliant: {snapshot.get('compliant', 0)}, Non-compliant: {snapshot.get('non_compliant', 0)}, Unknown: {snapshot.get('unknown', 0)}",
            f"- Top non-compliant OS: {snapshot.get('top_non_compliant_os', [])}",
            f"- Device configurations: {snapshot.get('config_count', 0)}",
            f"- Mobile apps: {snapshot.get('app_count', 0)}",
        ]
        return "\n".join(lines), True
    except Exception:
        return "", False


@app.callback(invoke_without_command=True)
def copilot_callback(
    prompt: str = typer.Argument(
        ...,
        help="Your request for the IT assistant (e.g. a task or question).",
    ),
    save: Path | None = typer.Option(
        None,
        "--save",
        help="Save the response to this file (UTF-8).",
        path_type=Path,
    ),
) -> None:
    """Run the IT copilot with the given prompt."""
    system_prompt = _load_prompt("copilot")
    intune_context, intune_included = _get_intune_system_context(prompt)
    if intune_context:
        system_prompt = system_prompt + "\n\n" + intune_context
    user_input = prompt
    try:
        client = OpenAIClient()
        response = client.generate_response(system_prompt, user_input)
    except ConfigError as e:
        console.print(f"[red]Configuration error: {e}[/red]")
        raise typer.Exit(1)
    except OpenAIClientError as e:
        console.print(f"[red]OpenAI / Azure OpenAI error: {e}[/red]")
        raise typer.Exit(1)

    console.print(Panel(response, title="AI Copilot Response", border_style="blue"))

    if intune_included:
        console.print("[dim]Intune context: included[/dim]")
    else:
        console.print("[dim]Intune context: unavailable[/dim]")

    if save is not None:
        save.write_text(response, encoding="utf-8")
        console.print(f"[green]Saved to {save}[/green]")
