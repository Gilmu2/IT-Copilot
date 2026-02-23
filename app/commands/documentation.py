"""Doc command: generate documentation from scripts/files."""

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from app.config import ConfigError
from app.openai_client import OpenAIClient, OpenAIClientError

console = Console()

MAX_FILE_CHARS = 20_000
TRUNCATE_NOTE = "\n[Content truncated due to size]"


def _load_prompt(name: str) -> str:
    """Load prompt from app/prompts/{name}.txt."""
    prompts_dir = Path(__file__).resolve().parent.parent / "prompts"
    return (prompts_dir / f"{name}.txt").read_text(encoding="utf-8").strip()


def _read_file_content(file_path: Path) -> str:
    """Read file safely; truncate to MAX_FILE_CHARS and append note if needed."""
    content = file_path.read_text(encoding="utf-8", errors="ignore")
    if len(content) > MAX_FILE_CHARS:
        content = content[:MAX_FILE_CHARS] + TRUNCATE_NOTE
    return content


def doc_cmd(
    file_path: Path = typer.Argument(
        ...,
        help="Path to the file to document (e.g. .ps1 script).",
        path_type=Path,
        exists=False,
    ),
    save: Path | None = typer.Option(
        None,
        "--save",
        help="Save the documentation to this file (UTF-8).",
        path_type=Path,
    ),
) -> None:
    """Generate structured documentation (summary, technical breakdown, dependencies, risks, rollback)."""
    if not file_path.exists():
        console.print(f"[red]File not found: {file_path}[/red]")
        raise typer.Exit(1)

    try:
        content = _read_file_content(file_path)
        system_prompt = _load_prompt("documentation")
        client = OpenAIClient()
        response = client.generate_response(system_prompt, content)
    except ConfigError as e:
        console.print(f"[red]Configuration error: {e}[/red]")
        raise typer.Exit(1)
    except FileNotFoundError:
        console.print(f"[red]File not found: {file_path}[/red]")
        raise typer.Exit(1)
    except OpenAIClientError as e:
        console.print(f"[red]OpenAI / Azure OpenAI error: {e}[/red]")
        raise typer.Exit(1)

    console.print(Panel(response, title="Generated Documentation", border_style="blue"))

    if save is not None:
        save.write_text(response, encoding="utf-8")
        console.print(f"[green]Saved to {save}[/green]")
