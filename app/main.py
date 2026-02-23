"""CLI entry point. Registers commands from command modules; no command logic here."""

import typer

from app.commands import analyze, analyze_log, check_permissions, copilot, doc_intune, documentation, graph, log_analyzer, suggest_fixes, trend_summary

app = typer.Typer(
    name="ai-it",
    help="Local enterprise AI CLI for IT engineers.",
)

app.add_typer(copilot.app, name="copilot")
app.add_typer(suggest_fixes.app, name="suggest-fixes")
app.add_typer(trend_summary.app, name="trend-summary")
app.add_typer(analyze_log.app, name="analyze-log")
app.add_typer(check_permissions.app, name="check-permissions")
app.command("log")(log_analyzer.log_cmd)
app.command("doc")(documentation.doc_cmd)
app.add_typer(graph.app, name="graph")
app.command("analyze-user")(analyze.analyze_user_cmd)
app.command("analyze-device")(analyze.analyze_device_cmd)
app.command("audit-intune")(analyze.audit_intune_cmd)
app.command("list-apps")(analyze.list_apps_cmd)
app.command("list-configs")(analyze.list_configs_cmd)
app.command("doc-intune")(doc_intune.doc_intune_cmd)


if __name__ == "__main__":
    app()
