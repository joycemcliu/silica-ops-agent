# Command guard

Project-local command assessment, user approval, and Docker execution for the
Hermes `diagnose` profile. Run the controller from the repository root:

```bash
./command-guard.sh status
./command-guard.sh restart
./command-guard.sh approve REQUEST_ID
```

No installation under host `/opt`, `/etc`, or `/usr/local` is required. The human
operator needs Docker access; commands executed by the AI receive no Docker socket.

## First setup

```bash
./command-guard.sh setup
./command-guard.sh start
```

Setup builds the gateway and command-runtime images with pinned base images. The
gateway image installs Python dependencies with uv and `uv.lock`. A short-lived
setup container creates private project data and numeric UID/GID settings; it
does not create host users, groups, services, or global commands.

```text
command-guard.sh                 # Human-facing controller
command-guard/                   # Source, Compose file, tests, Hermes adapter
.command-guard/                  # Ignored by Git
  config/
    policy.yaml                 # File exclusions and approval rules
    service.env                 # TYPESAFE_API_KEY
    compose.env                 # Image IDs and numeric container identities
  state/                        # Private audit and execution metadata
  sockets/                      # Submission and approval sockets
  legacy-backup/                # Only when importing an older deployment
```

Edit `.command-guard/config/service.env` and set `TYPESAFE_API_KEY=your-key`, then
run `./command-guard.sh restart`. Without a key, commands require user approval
and classification confidence is reported as unavailable. Never commit this file;
the whole `.command-guard` directory is ignored by Git, and key files have mode 0600.

To configure a new Hermes profile:

```bash
uv sync --project command-guard --locked --group dev
uv run --project command-guard python command-guard/deploy/linux/apply_hermes.py \
  /path/to/hermes/profiles/diagnose --cwd /host/path/to/operations
hermes -p diagnose guard-check --reload
```

The profile's plugin symlink points into `command-guard/integrations/hermes` in
this checkout. Config/SOUL backups are stored inside that profile. Start a new
conversation after changing tool schemas. If the checkout moves, rerun setup and
relocate the profile so its absolute socket/plugin paths follow the new location.

## Daily use

```bash
./command-guard.sh status
./command-guard.sh logs --tail 50
./command-guard.sh list
./command-guard.sh inspect REQUEST_ID
./command-guard.sh approve REQUEST_ID
./command-guard.sh decline REQUEST_ID
./command-guard.sh restart
./command-guard.sh stop
./command-guard.sh start
```

Approval displays the exact request and requires typing `approve REQUEST_ID` in
the operator terminal. Restart recreates the gateway, reloads the key file, and
invalidates pending approvals. Stop/start and crashes also discard in-memory grants.

## How Hermes uses it

Only the selected profile's terminal handler is overridden:

```text
Hermes terminal → submission socket → policy + Jev → approval if needed
                                                     → fresh Docker command container
```

The AI does not have to remember to run the client script. Its normal terminal
tool is the gateway client. Native file-editing, direct code execution, delegation,
and other execution routes without guarded adapters are denied by a profile-scoped
pre-tool hook. Explicit `allowed_mcp_servers` exceptions are separate from shell
execution. Skills viewing, clarification, memory, and todo remain available.

Host files appear under `/host` inside command containers. Container `/etc` and
`/usr` are from the runtime image. Use a workdir per call; each execution has a
fresh container with no persistent exports, background processes, or temporary files.

Read example, as terminal tool arguments:

```json
{"command":"cat /host/usr/lib/os-release","workdir":"/host"}
```

Writes, networking, sensitive-read exceptions, and resume use `guard_command`:

```json
{
  "action": "submit",
  "command": "printf 'hello\\n' > guard-test.txt",
  "cwd": "/host/srv/operations",
  "write_paths": ["/host/srv/operations"],
  "network": false
}
```

The AI presents the returned command, capability scope, effects, confidence, and
request ID. After the human approves through `./command-guard.sh approve ID`, it calls:

```json
{"action":"resume","id":"REQUEST_ID"}
```

Approval expires after five minutes and can be consumed once. Resume cannot
replace the command or requested access. Approval does not override ordinary host
file ownership: a directory eligible for writes must be writable by the runner UID/GID.
Chat text cannot grant permission. Jev confidence describes a classification,
not the probability that executing a command is safe.

## Isolation

The gateway runs in Docker as a separate non-root numeric UID, with a read-only
image, dropped capabilities, resource limits, and `restart: unless-stopped`. It
publishes no TCP ports. Only this trusted container receives the Docker socket.
It sees host metadata through `/hostfs`, resolving absolute symlinks against that
host view rather than its own image. The private project directory, controller,
and gateway source are excluded from commands.

Command containers have read-only host mounts by default. Sensitive exclusions,
host process/device trees, runtime sockets, and Docker data are not mounted.
Writes and sensitive reads need explicit path grants; IP networking requires
approval. Unix sockets remain prohibited even with networking enabled. The Moby
default seccomp profile is vendored and tightened; the app needs no Bubblewrap or
direct libseccomp integration. Source pin/license are under `execution/profiles/`.

Mounts are split around exclusions, with recursive submounts disabled. Symlinks at
split boundaries are omitted; use canonical host paths. Exclusions do not discover
secret copies or hard-link aliases automatically. Globs expand at startup.

Output is bounded to 1 MiB per stream. Commands have timeouts and CPU/memory/task
limits. Completion and failure remove the command container; broker startup and
graceful shutdown clean up its labeled containers. A state lock prevents duplicate
brokers from replacing live sockets, and startup recovers sockets left by a crash.

Audit records contain hashes, UIDs, decisions, timestamps, and exit metadata, not
raw commands/output. TypeSafe receives command text, cwd, capability scope, and
exclusion names, without file contents or ambient credentials. Avoid embedded
secrets in commands. Approved networking can transfer data or modify remote
systems; remote read-only enforcement requires restricted remote credentials.

This enforces the profile's tool-execution boundary. Profiles sharing an OS account
are not separate trust zones against an administrator, malicious peer profile, or
arbitrary additional trusted host plugin. Docker access itself is privileged.

## Verify and develop

```bash
hermes -p diagnose guard-check
hermes -p diagnose guard-check --probe
hermes -p diagnose guard-check --resume REQUEST_ID
```

Expected: `guarded: true`, `backend_registered: true`, and blocked native bypass
tools. A probe returns output or a pending permission request. The default profile
retains its own backend.

```bash
cd command-guard
uv sync --locked --group dev
docker build -t command-guard-gateway:local -f deploy/docker/Gateway.Dockerfile .
uv run ruff check src tests integrations deploy/linux/*.py ../scripts/command-guard-client.py
uv run ruff format --check src tests integrations deploy/linux/*.py ../scripts/command-guard-client.py
COMMAND_GUARD_REQUIRE_DOCKER=1 uv run pytest -q -ra
uv build
```

Tests exercise real Docker mounts, approval ownership/replay, socket restrictions,
timeouts, secret handling, broker crash recovery, and profile relocation. Required
Docker tests fail if Docker or the built gateway image is missing. Tests make no
live TypeSafe API or model calls.

`scripts/command-guard-client.py` is a standalone submission/resume client and
defaults to this checkout's socket. It uses host paths for cwd/grants, while its
command text runs inside the Docker filesystem. Exit 3 means pending approval;
124 means timeout; other finished results use the command exit code.

## Import an older installation

`./command-guard.sh setup --migrate` copies the old host installation's key,
policy, and audit data into the private project directory, retaining a backup.
Start the local gateway, then relocate an already guarded profile without changing
its other settings or MCP exceptions:

```bash
uv run --project command-guard python command-guard/deploy/linux/apply_hermes.py \
  /path/to/hermes/profiles/diagnose --relocate-only
hermes -p diagnose guard-check --reload
```

Import does not delete the old deployment automatically. After verifying local
execution, retire the old container and configuration. The current `diagnose`
deployment has already been migrated; it uses no host `/opt` or `/etc` installation.
