# ops-agent

A shared team assistant with an environment-scoped, read-only broker. The broker
holds production credentials; disposable agents receive only a scoped session
token. See [the plan](IMPLEMENTATION_PLAN.md) and [contributor rules](AGENTS.md).

## Development

Install Go 1.27 and Make, or install the local development tools with
`bash scripts/setup-tools.sh`. Run:

```sh
make build
make test
make lint
make check-config
```

If Make is unavailable, use `bash scripts/project.sh build` (and `test`, `lint`,
`fmt`, `deps`, `check-config`). On Debian/Ubuntu the setup script also unpacks Make
into `.tools/make/`; invoke it as `.tools/make/usr/bin/make test`. Tool downloads
and caches stay in ignored `.tools/`.

Configuration and tests use synthetic environments only. Never put production
credentials or customer data in this repository.

## Progress and required decisions

Implemented:

- Phase 0: minimal skeleton, canonical contributor rules, Go module, script-first
  build/test/lint targets and CI.
- Phase 1, tasks 1–4: strict environment registry, bounded environment/file
  secret stores, redacted structured audit writer and configurable redaction.
- Phase 1, part of task 5: session claim lifecycle, gateway identity matching,
  and default-deny authorization by user, group, role, environment and tool.
- A `broker check-config` command, which validates all example configuration
  without loading credentials or contacting production.

Pending required decisions:

- Session signing key model: HMAC-SHA256 with a shared trusted key, or Ed25519
  with a private minting key and a public verification key.
- Dedicated read-only SSH account, existing secret store, SSH topology and
  maximum concurrent sessions.
- `kubectl` subprocess versus client-go tunneling, and the Go MCP SDK.

There is **no broker server, token signer, production connection or agent runtime
yet**. `session.Verifier` is an interface only; consumers must not treat raw JSON
claims as authentication. The next step is to finish signed tokens, then build
tunneling, SSH execution, MCP tools and `prodctl`, in the plan's order.

The first milestone also requires a test environment, a Slack app, Loki
ingestion and a supplied historical incident. Those acceptance checks have not
been run. Phases 2–5 have not started; Phase 6 requires explicit approval.

Git was initialized in the previously empty metadata directory. Changes remain
uncommitted because this environment has no configured Git author identity.

## Broker configuration

- [Environment registry](environments/envs.yaml): strict YAML with unique names,
  Kubernetes context/namespace, SSH target, credential reference and ACL group.
  An unknown field, missing field, duplicate name or unsafe target fails loading.
- [Access policy](environments/access.yaml): trusted users map to groups and roles;
  groups grant tools within the matching registry ACL. No caller-supplied group
  membership or wildcard grants. Expired claims and unknown tools fail closed.
- [Redaction rules](environments/redaction.yaml): adds regular expressions to the
  mandatory password, token, private-key, connection-string and PII rules. The
  baseline cannot be disabled by an empty rule list.

Secret references use `env:VARIABLE_NAME` or `file:relative/path`. The file store
is rooted in an explicitly supplied secret directory and prevents traversal and
symlink escapes. Files must be regular, private to their owner and at most 64 KiB.
File bytes, including trailing newlines, are returned exactly as stored. The
`secrets.WithRedaction` wrapper registers every retrieved value for literal
redaction before use. References for Vault remain a future `secrets.Store`
implementation. No secret values belong in configuration files.

The audit writer accepts a provided output stream (stdout in the future broker),
emits one JSON line per event, redacts nested arguments and errors, and reports
write failures. Transport wiring must audit every attempted tool call exactly
once and refuse to release results when audit persistence fails. That integration
is pending; writer tests alone do not prove the tool-call invariant.

Redaction catches known registered credentials and configured patterns. It does
not neutralize instructions embedded in evidence or identify every possible
unlabelled unknown secret; the eventual agent prompts must treat all returned
evidence as untrusted. Do not send output through a path that skips redaction.
