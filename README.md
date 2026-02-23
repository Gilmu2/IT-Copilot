# ai_it_assistant

Local enterprise-grade AI CLI for IT engineers. Uses **Azure OpenAI** (or OpenAI) and will integrate with Microsoft Graph.

## Prerequisites

- macOS
- Python 3.11+
- Virtual environment (recommended)

## Setup

1. Create and activate a virtual environment:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Copy the environment template and configure for **Azure OpenAI** (or OpenAI):

   ```bash
   cp .env.example .env
   ```

   Edit `.env`:

   - **OPENAI_API_KEY** (required) – Your Azure OpenAI API key (or OpenAI key if not using Azure).
   - **AZURE_OPENAI_ENDPOINT** – Your Azure OpenAI endpoint, e.g. `https://your-resource.openai.azure.com`. If set, the app uses Azure OpenAI.
   - **AZURE_OPENAI_API_VERSION** – Optional; default is `2024-02-15-preview`.
   - The default model is `gpt-4o-mini`; with Azure this must match your **deployment name** in the Azure portal.

## Run

From the project root:

```bash
python -m app.main --help
```

Optional shell alias for the `ai-it` command:

```bash
alias ai-it='python -m app.main'
```

Then:

```bash
ai-it --help
ai-it copilot --help
ai-it log --help
ai-it doc --help
```

## Commands

- **copilot** – IT assistant (PowerShell, Azure, Intune, etc.)
- **log** – Log file analysis (legacy)
- **analyze-log** – Intelligent log analysis (Phase 11): pattern/anomaly detection, severity, escalation. Use `--file <path>`; optional `--type auto|intune|syslog`, `--save`, `--top N`.
- **doc** – Generate documentation from scripts
- **graph** – Microsoft Graph: `graph users`, `graph devices`, `graph groups` (requires Azure app registration with Graph permissions)
- **analyze-user** – AI report for a user (Graph user + managed devices, then OpenAI summary). Optional `--top N`. May show permission warning if User.Read.All is missing.
- **analyze-device** – AI executive summary for one Intune managed device by ID (device-only; no user mapping).
- **audit-intune** – Intune audit with AI insights: top apps, config coverage, compliance trends, gaps. Optional `--top N`.
- **list-apps** – List Intune mobile apps with AI summary (deployment coverage, gaps). Optional `--top N`.
- **list-configs** – List Intune device configurations with AI summary. Optional `--top N`.
- **doc-intune** – AI documentation from Intune snapshot. Use `--type executive|audit|sop|compliance-gap` (default: executive). Optional `--top N`, `--save` to write to `reports/doc_<type>_<timestamp>.txt`.
- **suggest-fixes** – AI remediation suggestions from Intune snapshot (devices, apps, configs). Sections: Immediate Actions, Self-Remediation, Escalation Required. Optional `--save` to write to `reports/suggest_fixes_<timestamp>.txt`.
- **trend-summary** – AI trend summary (top 3 trends + executive summary) from Intune snapshot. Optional `--save` to write to `reports/trend_summary_<timestamp>.txt`.
- **check-permissions** – Probe all registered Graph endpoints and show Available/Denied/Error (Phase 12). Optional `--save` to write to `reports/check_permissions_<timestamp>.txt`.

**Copilot** is context-aware: when your prompt contains Intune-related keywords (e.g. intune, device, compliance, mdm, endpoint, app deployment, configuration, managed), it fetches a lightweight Intune snapshot and injects it as system context. A footer shows "Intune context: included" or "Intune context: unavailable". Graph is optional and failures are ignored.

### Phase 7–8 (AI + Graph) and permissions

The AI-driven analyze commands use **only** Graph endpoints allowed by the app registration. Supported permissions (app-only) are:

- DeviceManagementApps.ReadWrite.All
- DeviceManagementConfiguration.ReadWrite.All
- DeviceManagementManagedDevices.ReadWrite.All
- DeviceManagementServiceConfig.Read.All
- Reports.Read.All

If an endpoint requires a permission your app does not have (e.g. User.Read.All for user lookup), the CLI shows: **"Insufficient Graph API permissions to perform this action. Contact admin."** and continues with the data it can fetch. No tokens or secrets are printed.

## Quick test commands

From the project root with `.venv` activated and `.env` configured:

```bash
# CLI and help
python -m app.main --help
python -m app.main copilot --help
python -m app.main log --help
python -m app.main doc --help
python -m app.main graph --help
python -m app.main graph users --help

# OpenAI/Azure OpenAI (needs OPENAI_API_KEY and optionally Azure OpenAI vars)
python -m app.main copilot "Say hello in one sentence"

# Graph (needs AZURE_TENANT_ID, AZURE_CLIENT_ID, AZURE_CLIENT_SECRET and app permissions)
python -m app.main graph users --top 5
python -m app.main graph devices --top 5
python -m app.main graph groups --top 5

# Phase 7–8 AI + Graph (needs both Graph and OpenAI/Azure OpenAI configured)
python -m app.main analyze-device <managed-device-id>
python -m app.main audit-intune --top 100
python -m app.main list-apps --top 50
python -m app.main list-configs --top 50
# Phase 10: doc-intune report types (default: executive)
python -m app.main doc-intune
python -m app.main doc-intune --type executive
python -m app.main doc-intune --type executive --save
python -m app.main doc-intune --type audit
python -m app.main doc-intune --type audit --save
python -m app.main doc-intune --type sop
python -m app.main doc-intune --type sop --save
python -m app.main doc-intune --type compliance-gap
python -m app.main doc-intune --type compliance-gap --save
# Copilot with Intune context (prompt must mention "intune" or "managed device")
python -m app.main copilot "Summarize our Intune managed device posture"

# Phase 9: AI Copilot enhancements
python -m app.main suggest-fixes
python -m app.main suggest-fixes --save
python -m app.main trend-summary
python -m app.main trend-summary --save
python -m app.main copilot "tell me about intune compliance"
python -m app.main copilot "write a python script"

# Phase 11: Intelligent log analyzer
python -m app.main analyze-log --file path/to/log.log
python -m app.main analyze-log --file path/to/log.log --type intune --save
python -m app.main analyze-log --file path/to/syslog.log --top 50

# Phase 12: Graph permission check
python -m app.main check-permissions
python -m app.main check-permissions --save
```

For **log** and **doc** use a real file path. For **analyze-device** use a managed device ID from `graph devices`. No Graph calls use User.Read.All or Group.Read.All; permission-limited actions show a yellow warning and continue where possible.

### Phase 9 (AI Copilot enhancements)

- **suggest-fixes** fetches managed devices, mobile apps, and device configurations via Graph, builds a snapshot, and sends it to the AI. The response is shown as Rich panels: Immediate Actions, Self-Remediation, Escalation Required. Use `--save` to write to `reports/suggest_fixes_YYYYMMDD_HHMMSS.txt`.
- **trend-summary** uses the same snapshot and prompt file to produce a Rich table (Trend | Insight | Suggested Action) and an Executive Summary panel. Use `--save` to write to `reports/trend_summary_YYYYMMDD_HHMMSS.txt`.
- **copilot** checks the prompt for keywords (intune, device, compliance, mdm, endpoint, app deployment, configuration, managed). If matched, it fetches a lightweight Intune snapshot and prepends it as system context to the OpenAI call. The footer shows "Intune context: included" or "Intune context: unavailable". If Graph is unavailable or the prompt is not Intune-related, copilot runs with the original prompt only.

### Phase 10 (Enhanced documentation generator)

**doc-intune** supports four report types via `--type` (default: `executive`, backward compatible with Phase 8):

- **--type executive** – One-paragraph overview, three bullet highlights, one recommended next step. Single Rich panel "Executive Summary". Prompt: `doc_executive.txt`.
- **--type audit** – Technical audit: Environment Overview, Compliance Analysis, Configuration Coverage, App Deployment Status, Findings & Recommendations. Five Rich panels. Prompt: `doc_audit.txt`.
- **--type sop** – Standard Operating Procedures: Onboarding a new device, Responding to non-compliant device, Deploying a new app, Reviewing configuration policies. Four Rich panels (one per SOP). Prompt: `doc_sop.txt`.
- **--type compliance-gap** – Compliance Gap Summary, Root Cause Hypotheses, Gap-by-Gap Breakdown (with High/Medium/Low priority), Remediation Roadmap. Four Rich panels. Prompt: `doc_compliance_gap.txt`.

All types use `_build_intune_snapshot(limitations, top=500)`; no duplicate fetch logic. `--save` writes plain text (no Rich/ANSI) to `reports/doc_<type>_YYYYMMDD_HHMMSS.txt`. Running `doc-intune` with no flags behaves as `--type executive`.

### Phase 11 (Intelligent log analyzer)

**analyze-log** analyzes a log file with AI and local pre-scan:

- **--file** (required): path to the log file.
- **--type**: `auto` (default), `intune`, or `syslog` — format hint for detection.
- **--save**: write plain-text report to `reports/analyze_log_YYYYMMDD_HHMMSS.txt`.
- **--top**: max lines to send to AI (default 200).

Output: Rich rule (Log Analysis: &lt;filename&gt;), severity badge (Critical/High/Medium/Low), pre-scan table (errors, warnings, suspicious patterns, repeated messages, time range), five AI sections as panels (Log Overview, Detected Patterns and Anomalies, Severity Assessment, Escalation Recommendations, Suggested Next Steps), and footer (lines analyzed, log type, model). No Graph API calls; log analysis only.

```bash
python -m app.main analyze-log --file path/to/intune.log
python -m app.main analyze-log --file path/to/syslog.log --type syslog
python -m app.main analyze-log --file path/to/file.log --save
python -m app.main analyze-log --file path/to/file.log --top 50
```

### Phase 12 (Extensibility and permission-aware Graph)

**check-permissions** probes all endpoints in `ENDPOINT_REGISTRY` (real API calls with `$top=1` or minimal POST), then displays a Rich table: Permission Area | Endpoint | Status | Notes. Status is color-coded: ✓ Available (green), ✗ Denied (red), ⚠ Error (yellow). A summary panel shows counts; border is green if all currently-granted endpoints are Available, yellow otherwise. Footer shows probed-at timestamp and tenant ID (first 8 chars). Use `--save` to write plain text to `reports/check_permissions_YYYYMMDD_HHMMSS.txt`. If Graph is not configured (.env missing), prints red error and exits.

**Extensibility:** All Graph calls use `_safe_graph()` in `app/graph_client.py`. To add a new Graph endpoint:

1. **ENDPOINT_REGISTRY** in `app/graph_client.py` — add one dict: `area`, `endpoint`, `method`, `params` (or `json_body` for POST), `currently_granted`.
2. **GraphClient** — add a new method (e.g. `get_xyz()`) that calls `_request()` or uses `_safe_graph(lambda: self._request(...), default=..., limitations=...)`.
3. **Commands** — add a new command in `app/commands/` if you need a CLI for that endpoint.

No changes to `main.py`, existing commands, or prompt files are required when adding an endpoint; `check-permissions` reads from the registry and will show the new endpoint automatically.

## Configuration (for future development)

- All AI calls go through `OpenAIClient` in `app/openai_client.py`. It uses **Azure OpenAI** when `AZURE_OPENAI_ENDPOINT` is set in config, otherwise OpenAI.
- Config is loaded from `.env` via `app/config.py` (`get_config()`). No hardcoded secrets or endpoints; new features should use the same config and client.
