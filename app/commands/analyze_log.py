"""analyze-log command: intelligent log analysis with AI (Phase 11)."""

import json
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Literal

import typer
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table

from app.config import ConfigError, get_config
from app.openai_client import OpenAIClient, OpenAIClientError

console = Console()

LogTypeHint = Literal["auto", "intune", "syslog"]

INTRUNE_KEYWORDS = (
    "EnrollmentService",
    "MDMAgent",
    "IntuneManagement",
    "DeviceManagement",
    "ComplianceEngine",
    "PolicyManager",
)
SYSLOG_MONTHS = r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
SYSLOG_PATTERN = re.compile(
    rf"\b{SYSLOG_MONTHS}\s+\d{{1,2}}\s+\d{{1,2}}:\d{{2}}:\d{{2}}(?:\s|\.|$)",
    re.IGNORECASE,
)

SUSPICIOUS_PATTERNS = [
    ("authentication failure", re.compile(r"authentication failure|failed password|failed login", re.I)),
    ("enrollment failed", re.compile(r"enrollment failed|enrollment error", re.I)),
    ("policy not applied", re.compile(r"policy not applied|policy failed", re.I)),
    ("device not compliant", re.compile(r"device not compliant|compliance failed", re.I)),
    ("timeout", re.compile(r"timeout|connection timed out", re.I)),
    ("access denied", re.compile(r"access denied|permission denied", re.I)),
    ("certificate issue", re.compile(r"certificate.*(?:expired|invalid|failed)|(?:expired|invalid|failed).*certificate", re.I)),
    ("disk space", re.compile(r"disk.*(?:full|space)|(?:full|space).*disk", re.I)),
    ("memory exhausted", re.compile(r"memory.*(?:exhausted|out of memory)|(?:exhausted|out of memory)", re.I)),
]

SEVERITY_STYLES = {
    "Critical": "bold red",
    "High": "bold yellow",
    "Medium": "yellow",
    "Low": "green",
    "Unknown": "dim",
}


def _load_prompt(name: str) -> str:
    """Load prompt from app/prompts/{name}.txt."""
    prompts_dir = Path(__file__).resolve().parent.parent / "prompts"
    return (prompts_dir / f"{name}.txt").read_text(encoding="utf-8").strip()


def _read_and_preprocess(
    file_path: Path,
    log_type: LogTypeHint,
    top: int,
) -> tuple[list[str], str]:
    """
    Validate file, read lines, strip blanks, detect type if auto, return last `top` lines.
    Returns (lines, detected_type). Exits with red error if file missing/unreadable.
    """
    if not file_path.exists():
        console.print(f"[red]File not found: {file_path}[/red]")
        raise typer.Exit(1)
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError as e:
        console.print(f"[red]Cannot read file: {file_path} — {e}[/red]")
        raise typer.Exit(1)

    all_lines = [ln.strip() for ln in content.splitlines() if ln.strip()]
    if not all_lines:
        return [], "generic"

    if log_type != "auto":
        detected = log_type
    else:
        sample = " ".join(all_lines[:50])
        if any(kw in sample for kw in INTRUNE_KEYWORDS):
            detected = "intune"
        elif any(SYSLOG_PATTERN.search(ln) for ln in all_lines[:50]):
            detected = "syslog"
        else:
            detected = "generic"

    result_lines = all_lines[-top:] if len(all_lines) > top else all_lines
    return result_lines, detected


def _normalize_for_repeat(line: str) -> str:
    """Strip common leading timestamp patterns to normalize for repeated-message counting."""
    s = line
    s = re.sub(r"^\s*\d{4}-\d{2}-\d{2}[\sT]\d{2}:\d{2}:\d{2}(?:\.\d+)?\s*", "", s)
    s = re.sub(r"^\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{1,2}\s+\d{1,2}:\d{2}:\d{2}[^\s]*\s*", "", s, flags=re.I)
    return s.strip() or line


def _prescan_log(lines: list[str], detected_type: str) -> dict:
    """
    Lightweight pre-scan: error/warning counts, top 3 repeated messages,
    suspicious pattern names, time range (best-effort).
    """
    error_count = 0
    warning_count = 0
    for ln in lines:
        if re.search(r"\b(ERROR|Error|error|CRITICAL|FATAL)\b", ln):
            error_count += 1
        if re.search(r"\b(WARNING|Warning|WARN)\b", ln):
            warning_count += 1

    repeated_messages: list[str] = []
    if lines:
        normalized = [_normalize_for_repeat(ln) for ln in lines if ln.strip()]
        if normalized:
            counts = Counter(normalized)
            for msg, _ in counts.most_common(3):
                repeated_messages.append(msg[:80] + ("..." if len(msg) > 80 else ""))

    suspicious_patterns: list[str] = []
    for name, pat in SUSPICIOUS_PATTERNS:
        if any(pat.search(ln) for ln in lines):
            suspicious_patterns.append(name)

    time_range: str | None = None
    if lines:
        first_ln, last_ln = lines[0], lines[-1]
        # Extract best-effort timestamps (first/last non-empty)
        first_ts = first_ln[:30] if first_ln else None
        last_ts = last_ln[:30] if last_ln else None
        if first_ts or last_ts:
            time_range = f"{first_ts or '?'} — {last_ts or '?'}"

    return {
        "error_count": error_count,
        "warning_count": warning_count,
        "repeated_messages": repeated_messages,
        "suspicious_patterns": suspicious_patterns,
        "time_range": time_range,
    }


def _extract_overall_severity(severity_section_text: str) -> str:
    """Return first occurrence of Critical, High, Medium, or Low in section text; else Unknown."""
    text = severity_section_text or ""
    for level in ("Critical", "High", "Medium", "Low"):
        if re.search(rf"\b{re.escape(level)}\b", text, re.I):
            return level
    return "Unknown"


def _parse_sections(ai_text: str) -> list[tuple[str, str]]:
    """Parse AI response by splitting on ## SectionName. Returns list of (title, content)."""
    sections: list[tuple[str, str]] = []
    pattern = re.compile(r"^##\s+(.+)$", re.MULTILINE)
    matches = list(pattern.finditer(ai_text))
    for i, m in enumerate(matches):
        title = m.group(1).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(ai_text)
        content = ai_text[start:end].strip()
        sections.append((title, content))
    if not sections and ai_text.strip():
        sections.append(("Report", ai_text.strip()))
    return sections


def _severity_border_style(severity: str) -> str:
    """Map severity to panel border style."""
    if severity == "Critical":
        return "red"
    if severity in ("High", "Medium"):
        return "yellow"
    if severity == "Low":
        return "green"
    return "dim"


def _render_output(
    sections: list[tuple[str, str]],
    prescan: dict,
    detected_type: str,
    filename: str,
    severity: str,
    lines_count: int,
    model_name: str,
) -> None:
    """Header rule, severity badge, prescan table, five panels, footer."""
    console.print(Rule(f"Log Analysis: {filename}", style="blue"))

    badge_style = SEVERITY_STYLES.get(severity, SEVERITY_STYLES["Unknown"])
    console.print(f"[{badge_style}]● {severity.upper()}[/{badge_style}]")

    table = Table(title="Pre-scan summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Errors", str(prescan.get("error_count", 0)))
    table.add_row("Warnings", str(prescan.get("warning_count", 0)))
    table.add_row("Suspicious Patterns", str(len(prescan.get("suspicious_patterns") or [])))
    top_repeated = (prescan.get("repeated_messages") or [])[:1]
    table.add_row("Repeated Messages (top 1)", top_repeated[0] if top_repeated else "—")
    table.add_row("Time Range", prescan.get("time_range") or "—")
    console.print(table)

    border = _severity_border_style(severity)
    for title, content in sections:
        if content:
            console.print(Panel(content, title=title, border_style=border))

    console.print(
        f"[dim]Lines analyzed: {lines_count} | Log type: {detected_type} | Model: {model_name}[/dim]"
    )


def _strip_rich_markup(text: str) -> str:
    """Remove Rich-style markup for plain-text save."""
    return re.sub(r"\[/?[^\]]*\]", "", text)


def _save_report(
    ai_text: str,
    prescan: dict,
    severity: str,
    detected_type: str,
    lines_count: int,
) -> Path:
    """Write plain-text report to reports/analyze_log_YYYYMMDD_HHMMSS.txt."""
    reports_dir = Path("reports")
    reports_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = reports_dir / f"analyze_log_{ts}.txt"
    header = f"Log Analysis Report\nSeverity: {severity}\nLog type: {detected_type}\nLines analyzed: {lines_count}\n"
    header += f"Errors: {prescan.get('error_count', 0)} | Warnings: {prescan.get('warning_count', 0)}\n"
    header += f"Time range: {prescan.get('time_range') or '—'}\n\n"
    body = _strip_rich_markup(ai_text)
    out_path.write_text(header + body, encoding="utf-8")
    return out_path


app = typer.Typer(
    invoke_without_command=True,
    help="Intelligent log analysis with pattern detection and AI (Phase 11).",
)


@app.callback(invoke_without_command=True)
def analyze_log_cmd(
    file: Path = typer.Option(..., "--file", "-f", help="Path to the log file.", path_type=Path),
    type: LogTypeHint = typer.Option("auto", "--type", "-t", help="Log format hint: auto, intune, or syslog."),
    save: bool = typer.Option(False, "--save", "-s", help="Save report to reports/analyze_log_<timestamp>.txt."),
    top: int = typer.Option(200, "--top", "-n", help="Max number of log lines to send to AI."),
) -> None:
    """Analyze a log file with AI: detect patterns, severity, and escalation recommendations."""
    lines, detected_type = _read_and_preprocess(file, type, top)

    if not lines:
        console.print("[yellow]Log file is empty or contains no non-blank lines. Nothing to analyze.[/yellow]")
        raise typer.Exit(1)

    prescan = _prescan_log(lines, detected_type)

    payload = {
        "log_type_detected": detected_type,
        "line_count": len(lines),
        "prescan_summary": prescan,
        "log_lines": lines,
    }
    prompt_content = _load_prompt("analyze_log")
    user_input = json.dumps(payload, default=str, indent=2)

    try:
        client = OpenAIClient()
        ai_text = client.generate_response(prompt_content, user_input)
    except ConfigError as e:
        console.print(f"[red]Configuration error: {e}[/red]")
        raise typer.Exit(1)
    except OpenAIClientError as e:
        console.print(f"[red]OpenAI / Azure OpenAI error: {e}[/red]")
        raise typer.Exit(1)

    sections = _parse_sections(ai_text)
    severity_text = next((c for t, c in sections if "Severity" in t or "severity" in t), "")
    severity = _extract_overall_severity(severity_text)

    model_name = get_config().azure_openai_deployment
    _render_output(
        sections,
        prescan,
        detected_type,
        file.name,
        severity,
        len(lines),
        model_name,
    )

    if save:
        out_path = _save_report(ai_text, prescan, severity, detected_type, len(lines))
        console.print(f"[green]Saved to {out_path}[/green]")
