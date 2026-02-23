# ai_it_assistant

Local enterprise-grade AI CLI for IT engineers. Integrates with OpenAI and (later) Microsoft Graph.

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

3. Copy the environment template and set your keys:

   ```bash
   cp .env.example .env
   # Edit .env and set OPENAI_API_KEY (required for OpenAI features)
   ```

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

## Commands (planned)

- **copilot** – IT assistant (PowerShell, Azure, Intune, etc.)
- **log** – Log file analysis
- **doc** – Generate documentation from scripts

Implementation is added incrementally by phase.
