---
title: "Set up Grafana MCP servers in Hermes"
description: "Human-managed configuration of dev and prod Grafana MCP servers for Hermes agents."
tags: [hermes, grafana, mcp, profiles, setup]
---

# Set up Grafana MCP servers in Hermes

The human completes this setup before starting diagnosis workers. Workers use the configured servers, restore forwarding when needed, and refresh their connections; they do not configure MCP servers.

## Prerequisites

- Hermes installed with HTTP MCP support. The shared configuration option below also requires Hermes managed-scope configuration support.
- Complete [Grafana MCP forwarding setup](grafana-mcp-forward.md) on the host running Hermes. Keep both forwards running between diagnosis sessions.
- Access to the Hermes configuration files for the intended profiles, or administrative access for host-wide configuration.
- Hermes must be able to reach `127.0.0.1:60007` and `127.0.0.1:60008`. For agents running in a container or on another host, use endpoints reachable from that runtime; its localhost is different.

## Setup

Back up the configuration file before editing. Merge the following entries into its existing `mcp_servers` mapping, preserving other servers and settings:

```yaml
mcp_servers:
  grafana_mcp_ops_dev:
    url: http://127.0.0.1:60007/mcp
    headers:
      Host: localhost:60007
  grafana_mcp_ops_prod:
    url: http://127.0.0.1:60008/mcp
    headers:
      Host: localhost:60008
```

Choose the configuration scope:

- **All local profiles:** use `/etc/hermes/config.yaml` on installations supporting managed-scope configuration. This shared layer takes precedence over profile settings. If the Hermes process has `HERMES_MANAGED_DIR` set, use `config.yaml` in that directory instead. Apply the shared configuration on each host running agents.
- **One profile:** use `~/.hermes/profiles/<profile>/config.yaml`, or `~/.hermes/config.yaml` for the default profile. Updating the default profile does not configure every named profile. For a custom Hermes home, use that home's `config.yaml`.

Use `grafana_mcp_ops_dev` and `grafana_mcp_ops_prod` consistently as server names. Remove obsolete `sandbox_dev_grafana` and `sandbox_prod_grafana` definitions from affected profiles to avoid duplicate registrations. Server names are configuration labels; the forwarding script does not create DNS aliases for them.

Ensure the worker's tool selection enables the configured MCP tools as well.

## Verification

From this repository's root, confirm forwarding:

```bash
./scripts/grafana-mcp-forward.sh status
```

If forwarding is down, restore it and check again:

```bash
./scripts/grafana-mcp-forward.sh start
./scripts/grafana-mcp-forward.sh status
```

In each affected Hermes session, run `/reload-mcp` to reconnect servers and refresh available tools, or start a new session. This is a Hermes session command, not a shell command. Restart workers or gateways that cannot reload their MCP connections.

Verify that both servers expose tools to the intended worker, then perform a read-only datasource listing through each server. Reachable forwarding alone does not verify MCP registration or tool exposure.

## Usage

Workers select `grafana_mcp_ops_dev` for dev stores and `grafana_mcp_ops_prod` for prod stores. See [Grafana MCP usage](../diagnose_agent.md#grafana-mcp-usage) and the [diagnosis toolkit](../diagnose_toolkit.md#logs-metrics-and-traces) for queries and connection recovery.

## Troubleshooting

- **Connection refused:** check forwarding from the Hermes runtime. Restore it with the forwarding script when needed.
- **Tools absent despite reachable endpoints:** check the affected profile's effective server configuration and tool selection, then run `/reload-mcp` in that session or restart the worker.
- **Old server names still appear:** remove obsolete profile definitions and refresh the affected sessions.
- **Profile edits have no effect:** check whether managed configuration overrides those keys.
- **HTTP Host rejection:** retain the explicit `Host` headers shown above, even if the connection URL uses another reachable address.

## Cleanup

To remove this integration, the human removes only these two server definitions from the applicable configuration, then reloads or restarts affected sessions. Preserve other servers and settings. Keep shared forwarding running unless intentionally taking the service offline; see [forwarding cleanup](grafana-mcp-forward.md#cleanup).
