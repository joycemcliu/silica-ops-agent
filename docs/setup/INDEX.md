# Setup guides

Run setup commands from the repository root unless a guide states otherwise.

| Guide | Purpose | Keywords |
| --- | --- | --- |
| [Shared Python environment](setup-python-venv.md) | Create or reuse the shared Python venv and install the pinned WinRM dependency. | Python, venv, uv, dependencies, WinRM |
| [Grafana MCP forwarding](grafana-mcp-forward.md) | Prepare local tools and Kubernetes access for dev and prod Grafana MCP forwarding. | Grafana, MCP, Kubernetes, kubectl, port forwarding, automatic reconnection |
| [Hermes Grafana MCP configuration](hermes-grafana-mcp.md) | Human setup of dev and prod Grafana MCP servers for Hermes profiles and workers. | Hermes, Grafana, MCP, profiles, shared configuration |
| [Production Windows access through WinRM](windows-winrm.md) | Configure the WSL client, Windows remoting, credentials, and production store tunnel. | Windows, WinRM, PowerShell, WSL, sshuttle, credentials, production |

To add a guide, copy [_TEMPLATE.md](_TEMPLATE.md) to `<topic>.md`, replace the example content, and add a link to this index.
