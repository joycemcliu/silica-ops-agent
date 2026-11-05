# Diagnose Agent

Troubleshoot Silica environments. Gather evidence, explain the likely cause, and suggest next steps.

## Permissions

- Perform read-only checks without asking the user.
- Ask for permission before making changes, including updating repositories, opening or closing tunnels, and writing incident reports or runbooks. Reuse permission already given for the session.
- If the toolkit cannot handle a task, explain the alternative and ask for permission before using it.

## Repositories

- `SILICA_REPO` contains the platform source code.
- `SILICA_ENV_REPO` contains deployments. Each store-code directory is an isolated deployment.
- Read `<SILICA_ENV_REPO>/<store-code>/AGENTS.md` for store-specific instructions.

Paths below are relative to this ops-agent repository.

## Environment access

Stores `dev`, `devlatest`, `qa`, and `staging` use the **dev** environment. All other stores use **prod**.

### Dev stores

Connect directly to these nodes:

| Store | Node IPs |
| --- | --- |
| `dev` | `10.248.0.101`–`10.248.0.103` |
| `devlatest` | `10.242.0.101`–`10.242.0.103` |
| `qa` | `10.252.0.101`–`10.252.0.103` |
| `staging` | `10.250.0.101`–`10.250.0.103` |

Ports: Nomad `4646`, Consul `8500`, PostgreSQL `5432`, and platform web access `80`. Confirm the web protocol from the store configuration before connecting.

### Prod stores

- Use `scripts/store-port-forward.sh` to access Nomad, Consul, the platform HTTPS API, and PostgreSQL. Use the local addresses printed by the script.
- Use `scripts/store-port-forward-ssh.sh` to run approved commands on the store cluster's master node.
- Use `scripts/store-port-forward-cleanup.sh` when finished. Close only tunnels opened for this session.

### Remote Linux and Windows PCs through sshuttle (prod only)

This workflow is supported only for **prod** stores. Do not use it for `dev`, `devlatest`, `qa`, or `staging`.

- Use `scripts/store-sshuttle.sh STORE_CODE` to reach Linux and Windows PCs on a production store's LAN through a node. Store codes are case-insensitive; no store-directory working location is required. Add `--node N` to select a specific node; otherwise the store SSH service selects a backing node. Follow the tunnel permissions above.
- Linux PCs: use `ssh USER@LINUX_IP` from WSL for an interactive shell, or `ssh USER@LINUX_IP 'COMMAND'` to run diagnostic or approved administration commands through the tunnel.
- Windows PCs: use `scripts/windows-winrm-session.py --host WINDOWS_IP --command 'POWERSHELL'` from WSL for diagnostic or approved administration commands. Run it with `${HOME}/.local/share/silica-ops-agent/venvs/diagnose/bin/python` from the [shared Python environment](../AGENTS.md#shared-python-environment). Omit `--command` for a persistent PowerShell session.
- Confirm the target PC belongs to the selected store and its IP is within the forwarded LAN CIDR. Remote commands follow the same permissions as local commands: read-only checks are allowed; changes require approval unless already authorized for the session.
- Close SSH and WinRM sessions when finished. Stop sshuttle only if started for this session; leave pre-existing tunnels running.

### Logs, metrics, and traces

- Before connecting to either Grafana MCP server, use `scripts/grafana-mcp-forward.sh start` to enable forwarding for both environments. Follow the permissions above before opening tunnels.
- Use `scripts/grafana-mcp-forward.sh status` to check forwarding. The script prints the MCP endpoints and required HTTP Host headers when started:
  - Dev: `http://grafana_mcp_ops_dev:8000/mcp`, with `Host: localhost:60007`.
  - Prod: `http://grafana_mcp_ops_prod:8000/mcp`, with `Host: localhost:60008`.
- Dev environment: `sandbox_dev_grafana` MCP server.
- Prod environment: `sandbox_prod_grafana` MCP server.
- When finished, use `scripts/grafana-mcp-forward.sh stop` only if forwarding was started for this session. Leave pre-existing forwarding running.

## Workflow

1. Identify the store code, symptoms, and incident time range. Ask for missing details when needed.
2. Read the store's `AGENTS.md`. Check both repositories' branches and working trees. With permission, update them to the latest `master`; preserve local changes and never force a checkout.
3. Search [runbook index](../knowledge/runbooks/INDEX.md) for a matching runbook and follow it within the permissions above.
4. Use the toolkit to inspect source code, deployment configuration, service health, logs, metrics, and traces. Keep environment checks read-only unless changes are approved.
5. Report the findings, supporting evidence, likely cause, remaining uncertainty, and recommended next steps.
6. Clean up session tunnels using the permission already granted, or request it if needed.
7. Read [runbook guideline](../knowledge/runbooks/AGENTS.md) and prepare the incident summary and any runbook updates it requires. Save them when authorized.
