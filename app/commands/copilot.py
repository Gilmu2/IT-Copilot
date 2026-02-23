"""Copilot command: IT assistant for Azure, Intune, PowerShell, etc."""

import typer

app = typer.Typer(
    invoke_without_command=True,
    help="IT assistant for Azure, Entra ID, Intune, Windows, PowerShell.",
)


@app.callback(invoke_without_command=True)
def copilot_callback(
    prompt: str = typer.Argument(
        ...,
        help="Your request for the IT assistant (e.g. a task or question).",
    ),
) -> None:
    """Run the IT copilot with the given prompt."""
    # Phase 1: stub. Phase 4: load prompt from prompts/copilot.txt, call OpenAI, Rich output.
    typer.echo("Phase 1 – not implemented. Use prompts/copilot.txt in Phase 4.")
