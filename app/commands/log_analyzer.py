"""Log command: analyze log files."""

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from app.config import ConfigError
from app.openai_client import OpenAIClient, OpenAIClientError

console = Console()

MAX_FILE_CHARS = 20_000
TRUNCATE_NOTE = "\n[Log truncated due to size]"


def _load_prompt(name: str) -> str:
    """Load prompt from app/prompts/{name}.txt."""
    prompts_dir = Path(__file__).resolve().parent.parent / "prompts"
    return (prompts_dir / f"{name}.txt").read_text(encoding="utf-8").strip()


def _read_log_content(log_path: Path) -> str:
    """Read log file safely; truncate to MAX_FILE_CHARS and append note if needed."""
    content = log_path.read_text(encoding="utf-8", errors="ignore")
    if len(content) > MAX_FILE_CHARS:
        content = content[:MAX_FILE_CHARS] + TRUNCATE_NOTE
    return content


def log_cmd(
    log_path: Path = typer.Argument(
        ...,
        help="Path to the log file to analyze.",
        path_type=Path,
        exists=False,
    ),
    save: Path | None = typer.Option(
        None,
        "--save",
        help="Save the analysis to this file (UTF-8).",
        path_type=Path,
    ),
) -> None:
    """Analyze a log file and return structured analysis (root cause, errors, remediation)."""
    if not log_path.exists():
        console.print(f"[red]File not found: {log_path}[/red]")
        raise typer.Exit(1)

    try:
        content = _read_log_content(log_path)
        system_prompt = _load_prompt("log_analyzer")
        client = OpenAIClient()
        response = client.generate_response(system_prompt, content)
    except ConfigError as e:
        console.print(f"[red]Configuration error: {e}[/red]")
        raise typer.Exit(1)
    except FileNotFoundError:
        console.print(f"[red]File not found: {log_path}[/red]")
        raise typer.Exit(1)
    except OpenAIClientError as e:
        console.print(f"[red]OpenAI / Azure OpenAI error: {e}[/red]")
        raise typer.Exit(1)

    console.print(Panel(response, title="Log Analysis", border_style="blue"))

    if save is not None:
        save.write_text(response, encoding="utf-8")
        console.print(f"[green]Saved to {save}[/green]")
