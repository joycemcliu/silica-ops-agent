---
title: "Set up Grafana MCP forwarding"
description: "Prepare local tools and Kubernetes access for dev and prod Grafana MCP forwarding."
tags: [grafana, mcp, kubectl, port-forward, setup]
---

# Set up Grafana MCP forwarding

`scripts/grafana-mcp-forward.sh` uses `kubectl port-forward` to connect to the `grafana-mcp` service in the `monitoring` namespace in both environments. Run commands from the ops-agent repository root.

## Prerequisites

- WSL/Linux with Bash supporting `wait -n`, curl, flock, setsid, ss, awk, and GNU tail, plus standard utilities including `wc`. `flock` and `setsid` come from util-linux; `ss` comes from iproute2.
- `kubectl` on PATH, or `KUBECTL_BIN` set to its executable path.
- Both Kubernetes contexts below configured and authenticated, including any required GKE credential plugin. Your account must be able to read the service, discover its backing pods, and port-forward to them.
- Local TCP ports `60007` and `60008` free on `127.0.0.1`, and write access to `.tools/grafana-mcp-forward/`.

| Environment | Kubernetes context | MCP URL | Required HTTP Host header |
| --- | --- | --- | --- |
| Dev | `gke_sandboxvr-ops-development_us-west1-a_default-us-west1-a` | `http://127.0.0.1:60007/mcp` | `localhost:60007` |
| Prod | `gke_sandboxvr-ops-production_us-west1_default-us-west1` | `http://127.0.0.1:60008/mcp` | `localhost:60008` |

Both forwards target service port `8000`. Configure the MCP clients to use these URLs and Host headers; `grafana_mcp_ops_dev` and `grafana_mcp_ops_prod` are labels, not hostname aliases managed by the script.

## Setup

Run the script as your normal user, without sudo, so kubectl retains your PATH and Kubernetes authentication. No Python environment, sudo credentials, or `/etc/hosts` changes are needed. The script uses `setsid` to keep forwarding alive after the calling terminal exits and `ss` to check for occupied local ports.

If kubectl is installed outside PATH, export its absolute path before starting:

```bash
export KUBECTL_BIN=/absolute/path/to/kubectl
```

Reuse your existing Kubernetes configuration and authentication for both contexts. The script passes each context explicitly and does not change your current context. Follow the [diagnosis permissions](../diagnose_agent.md#permissions) when opening or closing tunnels; reuse existing session authorization.

## Verification

Check the local prerequisites and configured contexts:

```bash
command -v "${KUBECTL_BIN:-kubectl}" bash curl flock setsid ss awk tail wc
"${KUBECTL_BIN:-kubectl}" config get-contexts
```

Confirm both contexts in the table are present. Once forwarding is authorized, start it and check connectivity:

```bash
./scripts/grafana-mcp-forward.sh start
./scripts/grafana-mcp-forward.sh status
```

`start` prints the kubectl path, context and port mappings, supervisor PID, live kubectl output, and readiness for each tunnel while waiting. It returns once both tunnels are reachable; forwarding then continues in the background.

`status` reports the supervisor and each forward separately, and exits nonzero if either forward is unreachable. Any HTTP response, including 404, confirms transport connectivity; this does not check MCP application health or require a `/health` route.

## Usage

Use `start`, `status`, and `stop` as described in the [diagnosis workflow](../diagnose_agent.md#logs-metrics-and-traces). Each forward reconnects independently after a process exit, with a 3-second retry delay. HTTP connectivity checks run every 5 seconds with a 2-second timeout; three consecutive connection failures restart that forward to recover stalled connections.

State and logs live in `.tools/grafana-mcp-forward/`. Follow later reconnections with:

```bash
tail -f .tools/grafana-mcp-forward/forward.log
```

## Troubleshooting

- **kubectl not found:** check PATH or set `KUBECTL_BIN`. Run without sudo.
- **Missing shell command:** install the required command listed in the startup error; Python is not required.
- **Authentication or access errors:** inspect the kubectl output and confirm credentials, the required credential plugin, and access in the failing context.
- **Address already in use:** check for another listener on local port `60007` or `60008` before starting. Preserve unrelated or pre-existing forwards.
- **Connection refused:** the forward is starting or reconnecting; inspect the log if it persists.
- **HTTP 404:** the HTTP server is reachable, but the requested route is absent. Use `/mcp` with the Host header in the table for MCP requests.
- **Supervisor running but a forward unreachable:** supervisor status alone does not establish tunnel connectivity. Check the per-environment status and log.

## Cleanup

When finished, stop forwarding only if it was started for your session:

```bash
./scripts/grafana-mcp-forward.sh stop
```

Leave pre-existing forwarding running.
