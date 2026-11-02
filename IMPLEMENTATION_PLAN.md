# ops-agent: Implementation Plan (minimal version)

Plan for Claude Code. Read the whole file before starting; work phase by phase and stop at each acceptance check.

## 1. Goal

A shared AI helper for the team, hosted on one machine, with these roles:

1. **Knowledge**: repo domain knowledge (read repos, compare version tags, learn from merged PRs). Also usable by each developer locally.
2. **Diagnose**: production root-cause analysis for ONE selected environment per session, read-only.
3. **Solver**: propose short-term and long-term fixes; execution needs human approval (late phase, propose-only first).

Context: 90+ isolated production environments, each reached by `kubectl port-forward` to the selected environment and then `ssh` with account and password. Internal DB, REST APIs (openapi.yaml for most microservices), Nomad API and a Grafana MCP server (already set up) are also available.

## 2. Design principles

- **Safety comes from credential scope, not from prompts.** An instruction like "never read ./secrets" is only a request. Every credential the agent holds must be read-only and per environment:
  - Nomad ACL token with read policies only
  - DB role that is read-only, on a replica, with `statement_timeout` set on the role and sensitive columns hidden by grants or views
  - a dedicated read-only ssh account per environment (no sudo; only the groups needed to read logs)
  - k8s access limited to `get/list/watch` plus `create` on `pods/portforward`
  - API tokens that cannot write (see decision 1)
- **Use native CLIs directly** (`nomad`, `psql`, `curl`, `journalctl` over ssh). Do not write wrapper scripts unless a wrapper adds something the underlying system cannot enforce.
- **The session binds the environment.** `start-session.sh <env>` exports only that environment's read-only credentials, so the agent never holds credentials for other environments. Treat `OPS_ENV` as a convenience, not a security boundary.
- **Secrets live outside the repo** (e.g. `/etc/ops-agent/`, owned by a different Unix user than the agent). Only `start-session.sh` reads them.
- **Treat all log, DB, API and command output as untrusted input** (prompt injection). Mask secrets at the source where possible (e.g. a replace stage in Alloy before logs reach Loki).
- **Audit lives in the target systems**, using the agent's dedicated identities (ssh auth logs, DB `log_statement` for the agent role, Nomad audit where supported), plus the harness/Slack transcript.
- The harness (Hermes first; Claude Agent SDK or Claude Code headless as fallback) must stay swappable: put behavior in `AGENTS.md`, skills and scripts, not in harness-specific config.

## 3. Working rules for Claude Code

- Create the root `AGENTS.md` in Phase 0 with these rules and keep it the canonical source.
- When more than one reasonable approach exists, list the options with a small concrete example each and ask which to pick. Do not choose silently.
- Script-first: every non-inspection command (build, test, run, lint) goes into `scripts/` or a Makefile target.
- Never write real credentials, production hostnames or customer data into the repo. Config holds references only. Add `.gitignore` entries and a pre-commit secret scan.
- Small commits per task; each task ends with tests (shellcheck + bats or similar) and the acceptance check.

## 4. Repository layout

```text
ops-agent/
├── AGENTS.md                    # shared rules for every agent
├── README.md
├── Makefile                     # lint, test
├── envs.yaml                    # env name, kube_context, namespace, ssh target/port, host key fingerprint, credential file names (no secrets)
├── agents/
│   ├── diagnose/AGENTS.md       # how to diagnose, which tools to use, output format
│   ├── solver/AGENTS.md         # propose-only rules
│   └── skills/                  # SKILL.md files (diagnose-playbook, compare-version-tags, incident-summary)
├── scripts/
│   ├── start-session.sh         # start-session.sh <env>: export that env's read-only creds, start the agent
│   ├── env-ssh.sh               # port-forward + ssh to the session env, run one command
│   └── deployed-version.sh      # optional: deployed tag per service in the session env
├── knowledge/                   # domain notes in markdown
│   ├── index.md
│   ├── services/<service>.md
│   └── incidents/               # sanitized post-mortems
└── tests/                       # bats tests for scripts
```

Add `evals/`, `jobs/`, `rules/` only when their phase starts. Per-session containers and a broker service are later options (section 7).

## 5. Phases

### Phase 0: Bootstrap
- Skeleton, root `AGENTS.md`, Makefile (`lint` with shellcheck, `test` with bats), `.gitignore`, pre-commit secret scan, `envs.yaml` schema with one test environment.
- Acceptance: `make lint test` passes.

### Phase 1: Session and access scripts (one test environment)
1. `start-session.sh <env>`: validate `<env>` against `envs.yaml`; read that environment's credentials from the secrets directory; export only read-only values (`NOMAD_ADDR`, `NOMAD_TOKEN`, `PG*`, ssh account reference, API token) and `OPS_ENV`; start the agent as a dedicated low-privilege Unix user in a fresh process (tmux window or `systemd-run`). Never print credential values.
2. `env-ssh.sh "<command>"`: start `kubectl port-forward` bound to 127.0.0.1 on a random free port, wait until ready, ssh with the dedicated read-only account and a pinned host key (never disable host key checking), run ONE command with a timeout and output size cap, then always clean up the port-forward (trap on exit). Reject commands containing shell metacharacters (`; | & > < $` backtick `( )` or newlines) and flags that write or delete (e.g. `journalctl --vacuum-*`). Run only allowlisted binaries (journalctl, systemctl status, ps, df, free, ss, uptime, dmesg, limited ls/cat). Pipes and filtering happen locally. Apply a small regex redaction (passwords, tokens, private keys, connection strings) to output before printing.
3. `deployed-version.sh` (optional): report deployed tags per service in the session environment.

Acceptance (test environment or fakes: containerized sshd and a stub `kubectl`): an allowed command and journal logs work; a disallowed command is rejected; the session cannot reach another environment's credentials; a secret seeded in output is redacted; no orphan port-forward remains after success, failure or timeout.

### Phase 2: Agent layer (spike)
- Run the harness (Hermes first) in a fresh process under the dedicated Unix user, with a Slack gateway restricted to an allowlist of users. Hermes's security notes advise against its default local terminal backend when handling untrusted input (and log content is untrusted), so ask me whether to use its Docker backend for this spike or accept the local backend under the dedicated low-privilege user.
- Add deny rules in the harness for reading the secrets directory and for dumping the environment (`env`, `printenv`), as a second layer only.
- Write `agents/diagnose/AGENTS.md` and skills. Disable or gate the harness's self-learning for the diagnose role; skills change only through PRs.
- Acceptance: from Slack, a user starts a session for the test environment and the agent diagnoses a seeded problem using native CLIs and `env-ssh.sh`; target-system logs show the agent's identity and actions.
- Decision gate: if the harness cannot give acceptable isolation, write a short ADR and ask me before switching harness.

### Phase 3: Knowledge
- `knowledge/` layout as above. On PR merge, a CI job asks the agent to draft a knowledge update and opens a PR (never commits directly).
- Package `knowledge/` and skills so developers can use them locally with their own agent.

### Phase 4: Evals and timing
- `evals/cases/<incident>/` with `evidence/`, `question.md`, `expected-root-cause.md`; a runner that replays a case and scores correctness.
- Record time to first useful finding and whether the diagnosis was correct. Seed with 10 past incidents.
- Go/no-go bar (confirm the numbers with me), e.g. correct or clearly useful finding in under 10 minutes on most cases; otherwise keep the agent for post-incident analysis only.

### Phase 5: Early warning (after Phase 4)
- Detection stays deterministic: Loki/Mimir rules and fleet comparison routed through Alertmanager. The agent only triages flagged events: groups alerts, checks recent deploys, matches past incidents, collects evidence, and posts a short Slack summary with a confidence level.
- Start in shadow mode (private channel); measure lead time versus tickets and precision.
- Rule mining: the agent proposes rules from past incidents, backtests them over history across many environments, rejects noisy ones, and opens a PR for human review. Rules run in shadow mode before notifying anyone. Never auto-deploy rules.

### Phase 6: Solver (outline only, do not build until I approve)
- Propose-only: short-term and long-term options with a dry-run plan.
- Execution later via vetted parameterized runbook scripts with Slack approval, run by a separate identity with its own credentials, never by the diagnose agent.

## 6. Decisions to make with me (ask; give options with small examples)

1. **API tokens.** Can internal APIs issue read-only tokens? If yes, use `curl` directly. If a token also allows POST/DELETE, add a small GET-only `api-get.sh` that checks paths against openapi.yaml.
2. **Secret isolation.** Options: (a) `start-session.sh` runs as the secrets owner and drops privileges to the agent user; (b) a narrow `sudo` rule; (c) Vault with short-lived tokens later.
3. Dedicated read-only agent account on each environment, or reuse the shared one (dedicated is strongly preferred). Can ssh certificates or keys replace passwords?
4. Is the ssh target a host behind a bastion pod, or a pod itself?
5. Who may use the agent: if everyone in the Slack channel may see all environments, shared read-only access is acceptable; otherwise add per-user environment limits (see section 7).
6. Expected number of concurrent sessions, and the Phase 4 go/no-go numbers.

## 7. Accepted trade-offs, and when to add more

- The agent can read its own environment variables, so read-only tokens enter the model's context. Acceptable only if they are truly read-only and fine to send to the model provider.
- No automatic output scrubbing except in the ssh path and at log ingestion.
- Sensitive DB columns must be protected by grants or views.
- Add **per-session containers** (mount only that environment's credentials) if you need per-user environment limits or concurrent sessions must not share a filesystem.
- Add a **broker service** only if credentials cannot be scoped to read-only, per-user audit or approval trails are required, or script complexity (tunnel pooling, many concurrent sessions) becomes hard to maintain.
- Add wrapper scripts (DB, Nomad, redaction) back only if one of the trade-offs above becomes unacceptable.

## 8. Checks to add as tests

1. A session for environment A holds no credentials for environment B.
2. Disallowed commands in `env-ssh.sh` are rejected; metacharacters and write flags are blocked.
3. No secret value appears in `env-ssh.sh` output or in the repo.
4. No orphan `kubectl port-forward` processes remain.
5. The agent user cannot read the secrets directory.

## 9. First milestone

Phases 0 to 2 complete on one test environment, with the checks above passing and one seeded or replayed incident diagnosed from Slack.
