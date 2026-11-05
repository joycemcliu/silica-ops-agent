# Ops-agents

## Configuration

- At the start of each AI agent chat session, read the required root `config.env` for all shared environment variables and configuration.
- If `config.env` is missing, stop and tell the user to copy `config.example.env` to `config.env` and configure it. Do not use fallback values.
- Keep the loaded variables and values fixed throughout the session and use them for references in all docs and commands.
- Resolve relative configuration paths from this repository's root.
- If a required value is missing or invalid, stop the dependent work and tell the user to correct `config.env` and start a new session.

## Shared Python environment

- Use `${HOME}/.local/share/silica-ops-agent/venvs/diagnose/bin/python` for all Python commands and tools in this repository, including development and diagnosis. Reuse this shared venv across tasks and sessions.
- Run Python with this explicit interpreter path; activation is optional. Use `uv pip` commands with `--python` pointing to this interpreter when managing dependencies.


## Diagnosis

When troubleshooting or diagnosing a Silica environment issue, read and follow [Diagnose Agent instructions](docs/diagnose_agent.md). These instructions apply only to troubleshooting and diagnosis tasks.
