---
title: "Set up Windows access through WinRM"
description: "Configure the client, Windows remoting, and credentials for direct dev access or a production store tunnel."
tags: [windows, winrm, powershell, wsl, sshuttle, setup]
---

# Set up Windows access through WinRM

Use the same WinRM client in both environments. Discover the target PC's name and IP in the selected store's [Consul Nodes page](../diagnose_toolkit.md#discover-pcs-and-their-roles).

- **Dev stores (`dev`, `devlatest`, `qa`, `staging`):** connect directly to the Windows PC. Skip the sshuttle prerequisites and tunnel setup.
- **Prod stores:** run the client in WSL through the store's sshuttle tunnel.

```text
Dev: client → Windows LAN IP:5985
Prod:
WSL client → sshuttle → production Linux node → Windows LAN IP:5985
```

The client runs locally; no Python packages or WinRM client are installed on the node. For prod, sshuttle forwards TCP for the store CIDR, rather than bridging the whole network. With an explicit store code, the script reads `SUBNET_ID` from the production socat SSH StatefulSet and forwards `10.SUBNET_ID.0.0/16`. The Windows address must fall within that CIDR, and the selected node must be able to reach it.

Follow the [diagnosis permissions](../diagnose_agent.md#permissions). Reuse existing session authorization for setup and tunnel lifecycle; Windows configuration, service restarts, and other changes require authorization. Client commands are not automatically restricted to read-only operations.

## Prerequisites

For both environments, use the [repository-local Python environment](setup-python-venv.md), Windows credentials, and network access to the target PC.

For prod only, use WSL, `sshuttle`, a working firewall backend such as `iptables`, and the commands required by `scripts/store-sshuttle.sh`: `kubectl`, `ssh`, `nc` (netcat), `bash`, and `stat`. The wrapper also uses standard tools including `pgrep` and `ps`. `jq` is needed only for the legacy mode without a store-code argument. `sshpass` is required only when using the tunnel's optional SSH password file. The production Kubernetes context must be configured and authenticated, with permission to read the store socat StatefulSet as well as access and port-forward its service/pods:

```text
gke_infra-automate-production_us-west1_default-us-west1
```

For prod, the tunnel's SSH credentials and the Windows credentials are separate. `store-sshuttle.sh` uses its own SSH authentication; `WINRM_CREDENTIALS_FILE` is only for the Windows client. sshuttle needs local sudo privileges to install firewall rules. Its remote node also needs a compatible Python interpreter (sshuttle 2.0.0 requires Python 3.10+).

On Windows, WinRM must already be enabled, and the Windows account must have access to the PowerShell remoting endpoint. The firewall must permit TCP 5985 from the direct client's source address for dev, or the selected node's LAN address for prod. Use the actual connection source when checking Windows firewall rules.

## Setup

Run local commands from the ops-agent repository root unless stated otherwise.

### Local client

Follow [Set up the repo-local Python environment](setup-python-venv.md) to create or reuse `.venv` and install the pinned WinRM dependency. Use `.venv/bin/python` from the repository root for all client commands.

For prod only, install `sshuttle` and a firewall backend separately if missing, with authorization. On Ubuntu, the distribution packages are an option:

```bash
sudo apt-get install -y sshuttle iptables
```

### Windows remoting

An administrator can perform this one-time setup in **Windows PowerShell as Administrator**, when authorized:

```powershell
Enable-PSRemoting -Force
Get-Service WinRM
winrm enumerate winrm/config/listener
```

For a Public network profile, `Enable-PSRemoting -SkipNetworkProfileCheck -Force` permits setup but defaults to local-subnet access. Confirm the connection source is within that scope or have an administrator configure the required source scope. Avoid broadening access to all sources. A non-administrator account needs explicit endpoint permissions; local administrator accounts can encounter remote UAC restrictions. Resolve permissions with the Windows administrator rather than automatically disabling UAC filtering.

### Windows credentials

Supply the JSON file `${HOME}/.local/secrets/silica-prod-windows-password`. The client reads this exact file by default; it does not search the secrets directory. Despite the filename, the file contains both the username and password:

```json
{
  "username": "PCNAME\\username",
  "password": "your-windows-password"
}
```

Both keys are required and must contain strings; either or both may be empty (`""`). Windows and NTLM policy still determine whether those credentials can authenticate.

Use `DOMAIN\\username` in the JSON for a domain account. JSON requires backslashes to be escaped. Set `umask 077` before creating a new file, and keep the directory and existing credential file private:

```bash
chmod 700 "$HOME/.local/secrets"
chmod 600 "$HOME/.local/secrets/silica-prod-windows-password"
```

The client requires the file to be owned by the current local user, denies group/other permissions, and rejects paths resolving outside the secrets directory. No path argument or environment variable is needed for the default file. If an alternative is needed, `--credentials FILE` overrides `WINRM_CREDENTIALS_FILE`, which overrides the default filename. Select credentials for the target PC; the default filename does not restrict the client to prod. Keep credentials out of the repository, command arguments, logs, and incident reports. The client does not print them or include raw transport exceptions in errors.

### Prod only: start the tunnel in WSL terminal A

Skip this step for dev stores. For prod, from the ops-agent repository root, pass the target store code directly:

```bash
bash scripts/store-sshuttle.sh hkcwbmid --node 1
# Equivalent uppercase store code:
# bash scripts/store-sshuttle.sh HKCWBMID --node 1
```

Replace `hkcwbmid` with the target store and `1` with the selected node. Store codes are case-insensitive; `--store STORE_CODE` and `--cluster STORE_CODE` are alternatives to the positional argument. The script can run from any directory when called by its absolute path; no local `AGENTS.md` or `infra-cluster.json` is required. The diagnosis agent must still read store-specific instructions under the configured `SILICA_ENV_REPO` when available, as required by its workflow. Omitting `--node` uses the store SSH service instead of selecting a specific node.

For compatibility, calling the script without a store code still reads `AGENTS.md` and `.network.cidr` from `infra-cluster.json` in the current store directory.

Enter the local sudo and remote SSH credentials if prompted. Keep this terminal running while using WinRM. To inspect options without starting a tunnel:

```bash
bash scripts/store-sshuttle.sh --help
```

## Verification

From the repository root, confirm the local client can start:

```bash
uv pip check --python .venv/bin/python
.venv/bin/python scripts/windows-winrm-session.py --help
```

Expect no dependency errors and the client's help output. These checks do not open a remote session.

Verify end-to-end access using the Windows IP discovered in Consul. Connect directly for dev; for prod, first start the authorized tunnel and confirm the IP is within its forwarded CIDR:

```bash
.venv/bin/python scripts/windows-winrm-session.py \
  --host 10.26.1.50 \
  --command 'hostname; whoami; Get-Service WinRM'
```

The IP above is illustrative; replace it with the confirmed target. Expect the target hostname, authenticated Windows account, WinRM service status, and exit status 0.

## Usage

### Open a persistent session

Run from the ops-agent repository root. For prod, use a second WSL terminal while the tunnel runs in terminal A. The client reads the default credentials file automatically.

```bash
.venv/bin/python scripts/windows-winrm-session.py --host 10.26.1.50
```

Replace `10.26.1.50` with the actual Windows LAN IP. This example address is illustrative, not an inferred Windows inventory entry.

```powershell
PS remote> hostname
PS remote> whoami
PS remote> cd C:\Windows
PS remote> pwd
PS remote> $message = "Session is working"
PS remote> $message
PS remote> Get-Service WinRM
PS remote> Get-Process | Sort-Object CPU -Descending | Select-Object -First 10
PS remote> exit
```

Commands reuse one PowerShell runspace, preserving variables and the current directory. This client accepts one-line commands and prints output after each pipeline completes. It does not provide a full terminal, multiline input, remote input prompts such as `Read-Host`, or desktop/mouse control. Use noninteractive PowerShell commands. The session lasts only while the client and network connection remain alive; it does not resume after disconnecting.

### Agent or single-command use

Use `--command` for automation; it never opens an interactive prompt:

```bash
.venv/bin/python scripts/windows-winrm-session.py \
  --host 10.26.1.50 \
  --command 'hostname; whoami; Get-Service WinRM'
```

Wrap the PowerShell script in single quotes in Bash to preserve `$variables` and backslashes. Restrict agent diagnosis to approved read-only commands. A successful pipeline returns exit status 0; reported PowerShell errors or connection failures return 1, local configuration errors return 2, and interruption returns 130. Native executable exit codes are not automatically propagated; check them explicitly and raise a PowerShell error when needed, for example `some.exe; if ($LASTEXITCODE -ne 0) { throw "Command failed" }`.

The client uses NTLM with required message encryption on HTTP port 5985. Do not enable Basic authentication or `AllowUnencrypted`. If an HTTPS listener and a trusted certificate for the selected IP already exist, use `--https` (default port 5986). Certificate verification stays enabled. `--port` overrides either default. Environment HTTP proxies are bypassed so connections go directly to the PC for dev or through the LAN tunnel for prod.

### References

- [Microsoft: Enable-PSRemoting](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/enable-psremoting?view=powershell-5.1)
- [Microsoft: WinRM remoting security](https://learn.microsoft.com/en-us/powershell/scripting/security/remoting/winrm-security)
- [pypsrp client and runspace API](https://github.com/jborean93/pypsrp)
- [sshuttle requirements](https://sshuttle.readthedocs.io/en/stable/requirements.html)

## Troubleshooting

| Symptom                                   | Check                                                                                                                                                                                                                                 |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Client Python missing or dependency error | Follow [shared Python setup](setup-python-venv.md), then use the shared venv’s explicit Python executable.                                                                                                                            |
| Credentials rejected locally              | Check JSON escaping, file ownership, owner-only permissions, and that the resolved file is under `${HOME}/.local/secrets/`.                                                                                                           |
| Tunnel fails before WinRM                 | Confirm Kubernetes authentication/resource access, local sudo/firewall support, the SSH credentials, and node Python compatibility.                                                                                                   |
| WinRM timeout or connection refused       | For dev, confirm the client can reach the PC's listener/firewall on 5985 (or the configured port) directly. For prod, confirm sshuttle is running, the Windows IP belongs to the forwarded CIDR, and the node can reach the listener. |
| Authentication or access denied           | Confirm `PCNAME\\username` versus `DOMAIN\\username`, the password, endpoint permissions, local-account UAC restrictions, and whether policy permits NTLM. Do not weaken policy automatically.                                        |
| HTTPS certificate failure                 | Confirm trust and that the certificate matches the IP supplied to `--host`. This client accepts IPv4 addresses, not hostnames.                                                                                                        |
| Session drops                             | Restore direct connectivity for dev or the tunnel for prod, then reconnect. Session variables and location from the previous connection are lost.                                                                                     |

Use a WinRM command to test end-to-end connectivity; ICMP `ping` is not forwarded by this TCP tunnel. Error output reports transport exception types without raw request details. Record the target, timestamp, symptom, and error type for diagnosis without exposing credentials.

## Cleanup

Type `exit` or press Ctrl+D in the client to close the WinRM session. Ctrl+C interrupts the client and attempts to close its session; a lost network connection may delay remote cleanup. Closing a session does not undo commands already run.

For prod, stop sshuttle with Ctrl+C in terminal A only if this session started it, using the existing authorization. The wrapper stops the Kubernetes port-forward it created and leaves pre-existing forwards running. Do not run broad cleanup that would close someone else's tunnels. A pre-existing sshuttle process should remain running. Dev direct access has no sshuttle tunnel to stop.
