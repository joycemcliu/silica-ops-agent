# ops-agent

A shared, read-only operations assistant with portable repository knowledge.
The [implementation plan](IMPLEMENTATION_PLAN.md) defines the phased rollout;
[AGENTS.md](AGENTS.md) is the canonical policy for every harness.

## Status

Phase 0 is complete; Phase 1 is in progress. The SSH helper and OpenAPI GET path
policy have fake-backed tests. API transport awaits the credential-boundary
choice below, so Phase 1 acceptance is not yet complete. No production access,
Slack gateway, harness integration, or solver execution is enabled.

The owner changed Phase 1 scope: **do not build a session launcher**, use
**password authentication to an SSH pod**, and **include internal REST APIs**.
These decisions supersede the corresponding original plan items.

## Development

Requires Bash, Git, Make, Python 3, PyYAML, jsonschema, ShellCheck, Bats, and
Gitleaks. On Ubuntu, install the system packages `make python3-yaml
python3-jsonschema`. If the other tools are unavailable, `make dev-tools`
downloads version-pinned ShellCheck, Bats, and Gitleaks into ignored `.tools/`
(Linux x86_64 or aarch64; requires curl, tar, xz, and sha256sum).

```sh
make dev-tools
make hooks
make lint test
make secrets
```

`make hooks` opts this checkout into the committed pre-commit hook. It scans the
Git index with Gitleaks and redacts findings, including staged secrets that have
already been removed from the working tree. Missing Gitleaks fails closed. CI
also scans tracked and non-ignored working-tree files, without reading ignored
local credential directories or tooling. Secret scanning is best-effort, not a credential
security boundary.

## Environment configuration

[envs.yaml](envs.yaml) contains one synthetic test environment, checked against
[envs.schema.json](envs.schema.json). The all-zero host-key fingerprint is an
intentional placeholder, not a trusted key. Replace it with an independently
verified pin before any connection. The target is a Kubernetes port-forward
resource; SSH terminates at the pod in the selected Phase 1 setup.

Credential entries are relative filenames under an external secrets directory
(for example `/etc/ops-agent/`), never credential values. Absolute paths, traversal,
duplicate YAML keys, and unrecognized fields are rejected. The schema validates
shape only. With no launcher, the external runtime/operator is responsible for
file ownership, permissions, process isolation, and environment-specific credentials.
Do not source untrusted credential files as shell code.

## SSH access

Install native `kubectl`, OpenSSH (`ssh`, `ssh-keyscan`, `ssh-keygen`), and
`sshpass` on the runtime host. The helper does not install or change identities.
Before starting the agent, externally provision only the chosen environment's
read-only Nomad/database credentials and restricted Kubernetes configuration.
Supply `OPS_ENV`, `OPS_SSH_USER`, `OPS_SSH_PASSWORD`, and `KUBECONFIG` to that
process; never supply the write-capable API token. `OPS_ENVS_FILE` optionally
selects another validated configuration file. None of these variables grants
authorization by itself.

```sh
bash scripts/env-ssh.sh 'journalctl -u demo.service -n 50'
bash scripts/env-ssh.sh 'systemctl status demo.service'
```

The helper opens a loopback-only random-port tunnel, compares the scanned SSH
key to the configured fingerprint, and uses strict host-key checking with an
ephemeral known-hosts file. Passwords go to `sshpass` via its environment, not
command arguments. Other inherited credentials are not forwarded to native
subprocesses. SSH configuration files, agent forwarding, and local commands are
disabled. The wrapper does not replace the target account's read-only permissions.

Only explicitly supported diagnostic options are accepted: `journalctl`,
`systemctl status`, `ps`, `df`, `free`, `ss`, `uptime`, read-only `dmesg`, and
limited `ls`/`cat` paths under `/var/log` plus selected OS/proc files. Shell
metacharacters, environment-dumping options, write flags, traversal, and unknown
options are rejected before opening a tunnel. Filtering runs locally.

`OPS_SSH_TIMEOUT_SECONDS` defaults to 30 (1–120); connection readiness defaults
to 10 seconds via `OPS_CONNECT_TIMEOUT_SECONDS` (1–30). Output defaults to
65,536 bytes via `OPS_OUTPUT_LIMIT_BYTES` (1,024–1,048,576). Exit 124 indicates
command timeout; 125 indicates output truncation. Success, failure, timeout,
and SIGINT/SIGTERM clean up the port-forward and SSH process groups. SIGKILL
and host crashes cannot run cleanup handlers.

Output is buffered to a bounded size and redacted before printing, including
stderr, known session credentials, password/token fields, private keys, and
connection URLs. This is best-effort scrubbing; source-side masking and database
grants remain necessary. File allowlisting cannot prevent a permitted remote
file from being a symlink; target account permissions remain the boundary.

Use native `nomad` and `psql` with externally provisioned read-only credentials.
No wrapper or new launcher is needed for them. Do not run concurrent sessions
for different environments under a shared Unix identity without external
isolation: they could inspect one another's files or processes.

## REST API access: decision pending

The APIs have write-capable tokens. The agent must not receive those tokens;
a wrapper that shares the agent's credentials cannot enforce GET-only access.
Choose one boundary to finish Phase 1:

1. A protected local `api-get.sh` helper, invoked via a narrow sudo rule. Only
   the helper's account can read the token; the agent requests an approved GET
   path. This is not a session launcher.
2. An existing external GET-only gateway holding the token, with its connection
   contract supplied by the owner.

The shared [GET path policy](scripts/api_policy.py) already validates OpenAPI 3
routes, an explicit reviewed read-only route allowlist, and declared query
parameters. It rejects foreign URLs, traversal, percent-encoding, duplicate
query keys, ambiguous paths, and unresolved parameter references. GET alone
does not guarantee an endpoint is read-only, hence the reviewed allowlist.
This module does not yet make HTTP requests or load API credentials.

## Remaining rollout decisions

Slack users and per-user environment limits, concurrency, and the Phase 2 Hermes
Docker versus local backend remain owner decisions. Do not silently switch harnesses.

Production acceptance requires real read-only identities and audit verification;
fake tests alone cannot establish those guarantees. Phase 4 evaluation thresholds
and Phase 6 execution remain separate approval gates.
