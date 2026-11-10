# Diagnosis toolkit

Use these tools to gather evidence during diagnosis.

Paths below are relative to this ops-agent repository. For installation and prerequisites, see the [setup guides](setup/INDEX.md).

## Environment access

Stores `dev`, `devlatest`, `qa`, and `staging` use the **dev** environment. All other stores use **prod**.

### Dev stores

Connect directly to these nodes:

| Store       | Node IPs                      |
| ----------- | ----------------------------- |
| `dev`       | `10.248.0.101`–`10.248.0.103` |
| `devlatest` | `10.242.0.101`–`10.242.0.103` |
| `qa`        | `10.252.0.101`–`10.252.0.103` |
| `staging`   | `10.250.0.101`–`10.250.0.103` |

Ports: Nomad `4646`, Consul `8500`, PostgreSQL `5432`, and platform web access `80`. Confirm the web protocol from the store configuration before connecting.

### Prod stores

- Use `scripts/store-port-forward.sh` to access Nomad, Consul, the platform HTTPS API, and PostgreSQL. Use the local addresses printed by the script.
- Use `scripts/store-port-forward-ssh.sh` to run approved commands on the store cluster's master node.
- Use `scripts/store-port-forward-cleanup.sh` when finished. Close only tunnels opened for this session.

### Discover PCs and their roles

In both dev and prod, use the selected store's Consul **Nodes** page to find node names and IP addresses. For example, the dev store's page is <http://<LAN IP>:8500/ui/dc1/nodes>. For prod, connect through `scripts/store-port-forward.sh` and use its printed Consul address, then open **Nodes**.

Node names provide hints about their platform roles:

| Name hint                         | Role                                                                                                          |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `master`                          | Linux PC forming part of the Nomad, Consul, PostgreSQL, and Traefik server infrastructure.                    |
| `video`                           | Windows PC for video rendering.                                                                               |
| `exp`                             | Windows PC running Unity/Photon server services; may have a USB webcam connected.                             |
| `r<room-name>`                    | PC providing services for that room; for example, `r3` mostly handles room 3.                                 |
| `h<room-name>`                    | Alias of `r<room-name>`; `h` means holodeck, the platform's name for a room.                                  |
| `webcam`                          | Linux PC with a USB webcam connected.                                                                         |
| `spc<room-string><player-number>` | Windows PC forming part of the Unity server; the name includes a room string and a player number from 1 to 6. |

Use these hints to select a candidate, then confirm its hostname, operating system, and running services before assuming its role.

### Remote Linux and Windows PCs

- **Dev stores (`dev`, `devlatest`, `qa`, `staging`):** connect directly to the PC IP discovered in Consul using SSH or WinRM. Do not run `scripts/store-sshuttle.sh` for these stores.
- **Prod stores:** use `scripts/store-sshuttle.sh STORE_CODE` to reach PCs on the store's LAN through a node. Store codes are case-insensitive; no store-directory working location is required. Add `--node N` to select a specific node; otherwise the store SSH service selects a backing node. Follow the diagnosis permissions linked above.
- Linux PCs in either environment: use `ssh USER@LINUX_IP` for an interactive shell, or `ssh USER@LINUX_IP 'COMMAND'` to run diagnostic or approved administration commands.
- Windows PCs in either environment: use `.venv/bin/python scripts/windows-winrm-session.py --host WINDOWS_IP --command 'POWERSHELL'` from the repository root. Omit `--command` for a persistent PowerShell session.
- Confirm the target PC belongs to the selected store. For prod, also confirm its IP is within the forwarded LAN CIDR. Remote commands follow the same permissions as local commands: read-only checks are allowed; changes require approval unless already authorized for the session.
- Close SSH and WinRM sessions when finished. Stop sshuttle only if started for this session; leave pre-existing tunnels running.

### Logs, metrics, and traces

- Use the MCP servers `grafana_mcp_ops_dev` for dev and `grafana_mcp_ops_prod` for prod. Read-only MCP queries do not require user approval.
- The human has already configured these servers in Hermes. Reuse the running connections.
- If a connection fails or tools are unavailable, run `./scripts/grafana-mcp-forward.sh status`. If forwarding is down, run `./scripts/grafana-mcp-forward.sh start`, then `./scripts/grafana-mcp-forward.sh status` to confirm both endpoints are reachable. These recovery operations are authorized by the diagnosis permissions.
- Refresh the MCP connections and available tools, then retry the read-only query. Hermes provides `/reload-mcp` as a session command, not a shell command. Use the session's refresh control when available; if the worker cannot invoke it, ask the human to run `/reload-mcp` in the affected Hermes session and then retry.
- If refresh does not restore the tools, report the failure to the human. Do not edit MCP configuration or substitute shell-based HTTP queries as part of this workflow.
- Leave Grafana forwarding running after diagnosis, including forwarding restored during the session.
