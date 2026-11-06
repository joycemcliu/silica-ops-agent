# Diagnosis toolkit

Use these tools to gather evidence during diagnosis.

Paths below are relative to this ops-agent repository. For installation and prerequisites, see the [setup guides](setup/INDEX.md).

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

- Use `scripts/store-sshuttle.sh STORE_CODE` to reach Linux and Windows PCs on a production store's LAN through a node. Store codes are case-insensitive; no store-directory working location is required. Add `--node N` to select a specific node; otherwise the store SSH service selects a backing node. Follow the diagnosis permissions linked above.
- Linux PCs: use `ssh USER@LINUX_IP` from WSL for an interactive shell, or `ssh USER@LINUX_IP 'COMMAND'` to run diagnostic or approved administration commands through the tunnel.
- Windows PCs: use `scripts/windows-winrm-session.py --host WINDOWS_IP --command 'POWERSHELL'` from WSL for diagnostic or approved administration commands. Run it with `${HOME}/.local/share/silica-ops-agent/venvs/diagnose/bin/python` from the [shared Python environment](../AGENTS.md#shared-python-environment). Omit `--command` for a persistent PowerShell session.
- Confirm the target PC belongs to the selected store and its IP is within the forwarded LAN CIDR. Remote commands follow the same permissions as local commands: read-only checks are allowed; changes require approval unless already authorized for the session.
- Close SSH and WinRM sessions when finished. Stop sshuttle only if started for this session; leave pre-existing tunnels running.

### Logs, metrics, and traces

- Before connecting, run `scripts/grafana-mcp-forward.sh start` for both environments. Follow the diagnosis permissions linked above.
- Check connectivity with `scripts/grafana-mcp-forward.sh status`.
- Use `sandbox_dev_grafana` for dev and `sandbox_prod_grafana` for prod.
- When finished, run `scripts/grafana-mcp-forward.sh stop` only if forwarding was started for this session. Leave pre-existing forwarding running.
