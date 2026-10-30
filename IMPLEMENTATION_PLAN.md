# ops-agent: Implementation Plan

Working name: `ops-agent`. Plan for Claude Code. Read the whole file before starting; work phase by phase.

## 1. Goal

A shared AI helper for the team, hosted on one machine, with three roles:

1. **Knowledge**: repo domain knowledge (read repos, compare version tags, learn from merged PRs).
2. **Diagnose**: production root-cause analysis for ONE selected environment per session, read-only.
3. **Solver**: propose short-term and long-term fixes; execution needs human approval (later phase, propose-only first).

Context: 90+ isolated production environments, each reached by `kubectl port-forward` to the selected environment and then `ssh` with account and password. Internal DB, REST APIs (openapi.yaml available for most microservices) and a Grafana MCP server (already set up) are also available.

## 2. Core design (do not change without asking)

```
Slack -> agent (throwaway container, NO secrets) -> broker -> production (read-only)
                                                       ^
                                       checks user, env, role; redacts output; audits
```

- The **broker** is the only component that holds credentials and touches production. Agents only call the broker (MCP tools + `prodctl` CLI).
- One **session** = one user + one environment + one role + TTL. The environment comes from the session token. Tools take NO `env` parameter, so the model cannot pick another environment.
- Read-only is enforced at the lowest layer possible (dedicated Linux account without sudo, read-only DB role on a replica, GET-only API, k8s `get/list/watch` plus `create` on `pods/portforward`), and again in broker validation.
- Treat all log, DB and command output as **untrusted input** (prompt injection). Redact before returning it.
- The **executor** (later) is a separate binary with separate credentials. The diagnose path never gets write credentials.
- The harness (Hermes first, Claude Agent SDK as fallback) must be swappable. Safety lives in the broker, not in the harness.

## 3. Working rules for Claude Code

- Create `AGENTS.md` in Phase 0 with these rules and keep it the canonical source.
- When more than one reasonable approach exists, list the options with a small concrete example for each and ask which to pick. Do not choose silently.
- Script-first: every non-inspection command (build, test, run, lint) goes into a script under `scripts/` or a Makefile target.
- Never write real credentials, hostnames of production or customer data into the repo. Config holds references only (e.g. a secret path).
- Small commits per task; each task ends with tests passing and the acceptance check below.

## 4. Repository layout (start minimal)

```text
ops-agent/
├── AGENTS.md
├── README.md
├── Makefile
├── scripts/
├── broker/            # Go service holding credentials
│   ├── go.mod
│   ├── cmd/broker/    # MCP server
│   ├── cmd/prodctl/   # CLI, same operations
│   └── internal/{session,authz,envregistry,secrets,tunnel,sshexec,dbquery,apiproxy,versions,redact,audit,mcp}/
├── agents/            # harness config, prompts, skills
│   ├── common/skills/
│   ├── diagnose/
│   ├── solver/
│   └── harness/hermes/
├── knowledge/         # domain notes (markdown)
└── environments/envs.yaml   # references only
```

Add `evals/`, `policy/`, `sandbox/`, `executor/`, `runbooks/`, `jobs/` only when their phase starts.

## 5. Phases

### Phase 0: Bootstrap
- Tasks: repo skeleton, `AGENTS.md`, Makefile targets (`build`, `test`, `lint`), Go module, CI running `go vet` and `go test`.
- Acceptance: `make test` passes on an empty broker.

### Phase 1: Broker MVP (one test environment)
Build in this order, each with unit tests:

1. **`envregistry`**: load `environments/envs.yaml`. Fields: `name`, `kube_context`, `namespace`, `ssh_target` (host or service), `credential_ref`, `acl_group`. Validate on load; reject unknown fields.
2. **`secrets`**: interface `Get(ref) -> string`. First implementation reads from a file or environment variable; keep the interface ready for Vault. Never log values.
3. **`audit`**: structured JSON events (who, session, env, tool, arguments, result size, duration, error) to stdout. Redact before writing.
4. **`redact`**: scrub passwords, tokens, private keys, bearer headers, connection strings, and email/phone patterns. Rules in a config file. Apply to all tool output.
5. **`session`** and **`authz`**: signed session token carrying user, env, role, expiry. `authz` maps user/group to allowed envs and tools. Reject expired or mismatched tokens.
6. **`tunnel`**: start `kubectl port-forward` on demand for the session's env, bind 127.0.0.1 on a random free port, idle TTL, max concurrency, clean teardown on exit or crash. (Decision to confirm with me: shell out to `kubectl` vs `client-go`; default is `kubectl` for v1.)
7. **`sshexec`**: connect through the tunnel using the agent's dedicated read-only account. Execute only commands that pass the allowlist validator:
   - parse into argv; reject any shell metacharacters (`; | & > < $ ` ( )` and newlines),
   - allowlist binary AND permitted flags (e.g. `journalctl`, `systemctl status|is-active`, `ps`, `df`, `free`, `ss`, `uptime`, `dmesg`, `ls`, `cat` within allowed paths),
   - reject flags that write or delete (e.g. `journalctl --vacuum-*`),
   - output size and time limits.
   Pipes and filtering happen locally in the agent sandbox, not on the host.
8. **`mcp`** + **`cmd/broker`**: MCP server exposing:
   - `get_logs(host, unit, since, until, lines)`
   - `run_readonly(host, argv[])`
   - `list_hosts()`
   - `whoami()` (session env, role, expiry)
9. **`cmd/prodctl`**: CLI mirroring the same operations (`prodctl logs ...`, `prodctl run ...`), using the session token from an environment variable.

Acceptance: against one test environment (or a local fake: containerized sshd + a stub `kubectl`), a session can fetch journal logs and run an allowlisted command; non-allowlisted commands, cross-environment attempts and expired tokens are rejected; audit shows every call; a secret seeded in output is redacted.

### Phase 2: More read-only data sources
- **`dbquery`**: tool `query_db(database, sql)`. Single statement only, `SELECT` only (parse, don't regex), statement timeout, row limit, column masking from config. Must also connect with a read-only DB role on a replica.
- **`apiproxy`**: tool `call_api(service, path, query)`. GET only; validate path and parameters against the service's `openapi.yaml`; response size limit.
- **`versions`**: tools `get_deployed_version(service)` and `diff_tags(repo, from, to)` (uses mirrored git repos).
- **Grafana**: keep the existing MCP server as is for now; later put an env-scoped proxy in front.
- Acceptance: each tool has tests for rejection cases (writes, multi-statement SQL, non-GET, unknown path).

### Phase 3: Agent layer (spike with Hermes)
- Run Hermes with the **Docker terminal backend** (never `local`) and a Slack gateway with a strict user allowlist.
- Session launcher script: on request (`/diagnose <env>`), mint a session token, start one throwaway container (git, ripgrep, jq, python, `prodctl`; no secrets; network only to the broker), destroy it at the end.
- `agents/diagnose/`: system prompt, read-only toolset, skills (`diagnose-playbook`, `compare-version-tags`, `write-incident-summary`).
- Restrict or disable the self-learning loop for the diagnose role; skills change only through PRs.
- Acceptance: from Slack, a user starts a session on the test environment, the agent answers using broker tools, and the audit log shows the full trail.
- Decision gate: if Hermes cannot give per-session isolation and per-user identity, write an ADR and switch to the Agent SDK with a thin Slack adapter. Ask me before switching.

### Phase 4: Knowledge
- `knowledge/` layout: `index.md`, `glossary.md`, `services/<service>.md`, `incidents/`.
- Job triggered on PR merge: summarize the PR into a proposed knowledge update and open a PR to `knowledge/` (never write directly).
- The same package (skills + knowledge) is distributable to developers for local use.

### Phase 5: Evals
- `evals/cases/<incident>/` with `evidence/`, `question.md`, `expected-root-cause.md`; a runner that replays the case against the agent and scores it.
- Seed with 10 past incidents. Use results to judge prompts and harness choice.

### Phase 6: Solver and executor (outline only, do not build until I approve)
- Solver stays propose-only: produces short-term and long-term options with a dry-run plan.
- Executor: separate binary and credentials; runs only approved, typed actions or runbook scripts pinned by hash, with dry-run first, Slack approval verification and full audit.

## 6. Security invariants (add as tests)

1. No tool accepts an environment parameter; the session decides.
2. A token for env A can never produce a call to env B.
3. No secret value appears in logs, tool output or prompts.
4. Every tool call produces exactly one audit event.
5. Any command not on the allowlist is rejected, not executed.
6. Agent containers have no credentials and no route to production except through the broker.

## 7. Open questions (ask me; do not assume)

- Can we create a dedicated read-only agent account on each environment, or must the shared one be reused?
- Where do secrets live today (Vault or other)?
- Is the ssh target a host reached through a bastion pod, or a pod itself?
- Expected number of concurrent incident sessions?
- Which Go MCP SDK to use (decide with options and examples).

## 8. Definition of done for the first milestone

Phases 0 to 3 complete on one test environment, with invariants tested, audit visible in Loki, and one replayed past incident diagnosed correctly from Slack.
