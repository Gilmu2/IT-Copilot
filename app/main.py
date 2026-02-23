"""CLI entry point. Registers commands from command modules; no command logic here."""

import typer

from app.commands import copilot, documentation, log_analyzer

app = typer.Typer(
    name="ai-it",
    help="Local enterprise AI CLI for IT engineers.",
)

app.add_typer(copilot.app, name="copilot")
app.command("log")(log_analyzer.log_cmd)
app.command("doc")(documentation.doc_cmd)


if __name__ == "__main__":
    app()
