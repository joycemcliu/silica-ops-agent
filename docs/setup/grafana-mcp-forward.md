---
title: "Set up Grafana MCP forwarding"
description: "Prepare local tools and Kubernetes access for dev and prod Grafana MCP forwarding."
tags: [grafana, mcp, kubectl, port-forward, setup]
---

# Set up Grafana MCP forwarding

`scripts/grafana-mcp-forward.sh` uses `kubectl port-forward` to connect to the `grafana-mcp` service in the `monitoring` namespace in both environments. Run commands from the ops-agent repository root.

## Prerequisites

- macOS or WSL/Linux with Bash 3.2+, curl, flock, awk, tail, and standard utilities including `wc`.
- macOS uses the built-in `lsof` and the repository-local `.venv/bin/python` to detach the supervisor; follow [Python setup](setup-python-venv.md) and install `flock` with Homebrew as shown below. The detachment helper uses only Python's standard library. WSL/Linux uses `setsid` and `ss`: `flock` and `setsid` come from util-linux, and `ss` comes from iproute2.
- `kubectl` on PATH, or `KUBECTL_BIN` set to its executable path.
- Both Kubernetes contexts below configured and authenticated, including any required GKE credential plugin. Your account must be able to read the service, discover its backing pods, and port-forward to them.
- Local TCP ports `60007` and `60008` free on `127.0.0.1`, and write access to `.tools/grafana-mcp-forward/`.

| Environment | Kubernetes context | MCP URL | Required HTTP Host header |
| --- | --- | --- | --- |
| Dev | `gke_sandboxvr-ops-development_us-west1-a_default-us-west1-a` | `http://127.0.0.1:60007/mcp` | `localhost:60007` |
| Prod | `gke_sandboxvr-ops-production_us-west1_default-us-west1` | `http://127.0.0.1:60008/mcp` | `localhost:60008` |

Both forwards target service port `8000`. Configure the MCP clients to use these URLs and Host headers; `grafana_mcp_ops_dev` and `grafana_mcp_ops_prod` are labels, not hostname aliases managed by the script.

The human registers these endpoints in Hermes using the separate [Hermes Grafana MCP setup guide](hermes-grafana-mcp.md). Forwarding alone does not expose MCP tools to workers.

## Setup

Run the script as your normal user, without sudo, so kubectl retains your PATH and Kubernetes authentication. No sudo credentials or `/etc/hosts` changes are needed. On macOS, the forwarding script uses `.venv/bin/python -c` to create a new process session and replace itself with the Bash supervisor; no separate Python helper file is needed. Linux uses `setsid` and does not require Python. This separation keeps forwards alive when the launching terminal or agent command exits; `nohup` alone does not provide it. Port checks use `lsof` on macOS and `ss` on Linux. The system Bash and tail on macOS are supported.

On macOS, install the missing lock command with [Homebrew's flock formula](https://formulae.brew.sh/formula/flock):

```bash
brew install flock
```

Ensure the agent process can find Homebrew's bin directory (normally `/opt/homebrew/bin` on Apple Silicon or `/usr/local/bin` on Intel). Restart the agent after updating its inherited PATH. Keep the same `flock` locks on both platforms; no alternate locking mechanism is needed.

If kubectl is installed outside PATH, export its absolute path before starting:

```bash
export KUBECTL_BIN=/absolute/path/to/kubectl
```

Reuse your existing Kubernetes configuration and authentication for both contexts. The script passes each context explicitly and does not change your current context. Follow the [diagnosis permissions](../diagnose_agent.md#permissions) when opening or closing tunnels; reuse existing session authorization.

## Verification

Check the local prerequisites and configured contexts:

```bash
command -v "${KUBECTL_BIN:-kubectl}" bash curl flock awk tail wc
if [[ "$(uname -s)" == Darwin ]]; then
  command -v lsof
  .venv/bin/python --version
else
  command -v setsid ss
fi
"${KUBECTL_BIN:-kubectl}" config get-contexts
```

Confirm both contexts in the table are present. Once forwarding is authorized, start it and check connectivity:

```bash
./scripts/grafana-mcp-forward.sh start
./scripts/grafana-mcp-forward.sh status
```

`start` prints the kubectl path, context and port mappings, supervisor PID, live kubectl output, and readiness for each tunnel while waiting. It returns once both tunnels are reachable; forwarding then continues in the background.

Concurrent `start` calls wait on a startup lock before checking the supervisor PID, so only one caller launches it and the others reuse it. The [diagnosis startup script](../../scripts/diagnose-agent-session-start.sh) updates both configured repositories; it does not start or check these forwards.

`status` reports the supervisor and each forward separately, and exits nonzero if either forward is unreachable. Any HTTP response, including 404, confirms transport connectivity; this does not check MCP application health or require a `/health` route.

## Usage

Keep forwarding running between diagnosis sessions. Workers use `status` and, when necessary, `start` as described in the [diagnosis toolkit](../diagnose_toolkit.md#logs-metrics-and-traces), then refresh their MCP connections. Each forward reconnects independently after a process exit, with a 3-second retry delay. HTTP connectivity checks run every 5 seconds with a 2-second timeout; three consecutive connection failures restart that forward to recover stalled connections.

State and logs live in `.tools/grafana-mcp-forward/`. Follow later reconnections with:

```bash
tail -f .tools/grafana-mcp-forward/forward.log
```

## Troubleshooting

- **kubectl not found:** check PATH or set `KUBECTL_BIN`. Run without sudo.
- **Missing shell command:** install the required command listed in the startup error. On macOS, a missing `.venv/bin/python` requires the linked Python setup; Linux forwarding does not require Python.
- **`flock` missing on macOS:** run `brew install flock` and check the PATH inherited by the agent. macOS startup uses the Python detachment helper and `lsof`, so Linux-only `setsid` and `ss` are not required there.
- **Authentication or access errors:** inspect the kubectl output and confirm credentials, the required credential plugin, and access in the failing context.
- **Address already in use:** check for another listener on local port `60007` or `60008` before starting. On macOS, `lsof -nP -iTCP:60007 -iTCP:60008 -sTCP:LISTEN` identifies it. Existing kftray forwards can occupy both ports even when this script has no supervisor. To let this script manage them, first intentionally disable those two kftray entries. Preserve unrelated or pre-existing forwards; the script never stops them automatically.
- **Connection refused:** the forward is starting or reconnecting; inspect the log if it persists.
- **HTTP 404:** the HTTP server is reachable, but the requested route is absent. Use `/mcp` with the Host header in the table for MCP requests.
- **Supervisor running but a forward unreachable:** supervisor status alone does not establish tunnel connectivity. Check the per-environment status and log.

## Cleanup

Routine diagnosis does not stop these shared forwards. When the human intentionally takes Grafana MCP access offline, stop forwarding with:

```bash
./scripts/grafana-mcp-forward.sh stop
```

Coordinate with users of both environments before stopping these shared forwards.
