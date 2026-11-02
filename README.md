# ops-agent

A shared, read-only operations assistant with portable repository knowledge.
The [implementation plan](IMPLEMENTATION_PLAN.md) defines the phased rollout;
[AGENTS.md](AGENTS.md) is the canonical policy for every harness.

## Status

Phase 0 bootstrap only. No session launcher, production access, Slack gateway,
harness integration, or solver execution is enabled. Later phases stop for the
plan's acceptance checks and owner decisions.

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
resource, not yet a decision about whether SSH terminates at the pod or beyond it.

Credential entries are relative filenames under an external secrets directory
(for example `/etc/ops-agent/`), never credential values. Absolute paths, traversal,
duplicate YAML keys, and unrecognized fields are rejected. The schema validates
shape only: Phase 1 must additionally enforce file ownership, permissions,
symlink containment, process isolation, and environment-specific credentials.
Do not source untrusted credential files as shell code.

## Decisions before access implementation

The next phase requires the owner's deployment choices:

1. API scopes: native `curl` with read-only tokens, or a GET-only OpenAPI-checked
   path when existing tokens can write. A wrapper is not sufficient if the agent
   can still access a write-capable token directly.
2. Secret isolation: privileged launcher dropping to the agent Unix user,
   narrow sudo policy, or short-lived Vault credentials later.
3. SSH identity: dedicated read-only account preferred; choose keys/certificates
   or passwords, and confirm whether SSH terminates on a pod or a host beyond it.
4. Slack users and environment access: shared visibility or per-user limits;
   expected concurrency determines whether session containers are needed.
5. Phase 2 backend: Hermes Docker or explicitly accepted local execution under
   the dedicated Unix user. Do not silently switch harnesses.

Production acceptance requires real read-only identities and audit verification;
fake tests alone cannot establish those guarantees. Phase 4 evaluation thresholds
and Phase 6 execution remain separate approval gates.
