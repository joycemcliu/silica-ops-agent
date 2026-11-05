# Ops-agents

## Configuration

- At the start of each AI agent chat session, read the required root `config.env` for all shared environment variables and configuration.
- If `config.env` is missing, stop and tell the user to copy `config.example.env` to `config.env` and configure it. Do not use fallback values.
- Keep the loaded variables and values fixed throughout the session and use them for references in all docs and commands.
- Resolve relative configuration paths from this repository's root.
- If a required value is missing or invalid, stop the dependent work and tell the user to correct `config.env` and start a new session.

## Diagnosis

When troubleshooting or diagnosing a Silica environment issue, read and follow [Diagnose Agent instructions](docs/diagnose_agent.md). These instructions apply only to troubleshooting and diagnosis tasks.
