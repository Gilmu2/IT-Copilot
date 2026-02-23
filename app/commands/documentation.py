"""Doc command: generate documentation from scripts/files."""

import pathlib

import typer


def doc_cmd(
    file_path: pathlib.Path = typer.Argument(
        ...,
        help="Path to the file to document (e.g. .ps1 script).",
        path_type=pathlib.Path,
        exists=False,
    ),
) -> None:
    """Generate structured documentation (summary, technical breakdown, dependencies, risks, rollback)."""
    # Phase 1: stub. Phase 4: read file, send to documentation prompt, Rich output.
    typer.echo("Phase 1 – not implemented. Use prompts/documentation.txt in Phase 4.")
