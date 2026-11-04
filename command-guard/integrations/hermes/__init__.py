"""Profile-scoped Hermes integration. No dependencies beyond Hermes and the Python stdlib."""

import json
import posixpath
import socket
from pathlib import Path

from agent.terminal_env_provider import TerminalEnvironmentProvider
from hermes_constants import get_hermes_home


def exchange(path, message):
    payload = json.dumps(message).encode() + b"\n"
    if len(payload) > 65536:
        return {"status": "error", "message": "Gateway request exceeds 65536 bytes"}
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(75)
            connection.connect(path)
            connection.sendall(payload)
            with connection.makefile("rb") as stream:
                return json.loads(stream.readline(14000000))
    except (OSError, ValueError):
        return {"status": "error", "message": "Command gateway unavailable; nothing ran locally"}


def host_path(path):
    """Convert a container /host path back to the host path understood by policy."""
    if not isinstance(path, str) or not path.startswith("/"):
        raise ValueError("Use an absolute path under /host")
    normalized = posixpath.normpath(path)
    if normalized == "/host":
        return "/"
    if normalized.startswith("/host/"):
        return normalized[5:]
    raise ValueError("Host paths must be prefixed with /host")


def terminal_result(result):
    if result.get("status") == "finished":
        return {
            "output": result.get("stdout", "") + result.get("stderr", ""),
            "exit_code": result["exit_code"],
            "returncode": result["exit_code"],
            "timed_out": result.get("timed_out", False),
        }
    return {
        "output": json.dumps(result, ensure_ascii=True, indent=2),
        "exit_code": 3 if result.get("status") == "pending_approval" else 1,
        "returncode": 3 if result.get("status") == "pending_approval" else 1,
    }


class GuardEnvironment:
    is_local = False

    def __init__(self, service, cwd, timeout):
        self.service, self.cwd, self.timeout = service, cwd, timeout
        self.env = {}

    def execute(self, command, timeout=None, cwd=None, **kwargs):
        result = self.service.submit({"command": command, "cwd": cwd or self.cwd})
        return terminal_result(result)

    def cleanup(self, **kwargs):
        return None

    def init_session(self):
        return None  # Fresh containers deliberately have no login snapshots or ambient credentials.

    def get_temp_dir(self):
        return "/tmp"


class GuardProvider(TerminalEnvironmentProvider):
    name = "command_guard"
    display_name = "Command Guard (Docker)"
    is_remote = True
    is_container = True
    supports_streams = False
    skip_container_guards = False

    def __init__(self, service):
        self.service = service

    @property
    def default_cwd(self):
        return self.service.cwd()

    @property
    def description(self):
        return "All execution is assessed by Jev and authorized by the command gateway."

    @property
    def strip_env_keys(self):
        return frozenset({"TYPESAFE_API_KEY", "DOCKER_HOST", "DOCKER_CERT_PATH"})

    def is_available(self):
        return Path(self.service.socket()).is_socket()

    def create_environment(self, *, cwd, timeout, task_id="default", **kwargs):
        self.service.require_scope()
        return GuardEnvironment(self.service, cwd or self.default_cwd, timeout)


class Service:
    def __init__(self, ctx):
        self.ctx = ctx
        self.owner = Path(get_hermes_home()).resolve()

    def require_scope(self):
        if Path(get_hermes_home()).resolve() != self.owner:
            raise ValueError("Command guard belongs to another profile")

    def socket(self):
        default = Path(__file__).resolve().parents[3] / ".command-guard/sockets/agent.sock"
        return self.ctx.get_config("socket", str(default))

    def cwd(self):
        return self.ctx.get_config("cwd", "/host")

    def submit(self, args):
        self.require_scope()
        allowed = {"command", "cwd", "workdir", "write_paths", "read_paths", "network"}
        if set(args) - allowed:
            raise ValueError(
                "Unsupported execution options; background/interactive execution is disabled"
            )
        request = {
            "command": args["command"],
            "cwd": host_path(args.get("cwd") or args.get("workdir") or self.cwd()),
            "write_paths": [host_path(p) for p in args.get("write_paths", [])],
            "read_paths": [host_path(p) for p in args.get("read_paths", [])],
            "network": args.get("network", False),
        }
        return exchange(self.socket(), {"action": "submit", "request": request})

    def terminal(self, args, **kwargs):
        try:
            return json.dumps(terminal_result(self.submit(args)), ensure_ascii=True)
        except (ValueError, KeyError, TypeError) as error:
            return json.dumps({"exit_code": 1, "output": str(error)}, ensure_ascii=True)

    def command(self, args, **kwargs):
        try:
            self.require_scope()
            if args.get("action") == "resume" and set(args) == {"action", "id"}:
                result = exchange(self.socket(), {"action": "resume", "id": args["id"]})
            elif args.get("action") == "submit":
                result = self.submit({k: v for k, v in args.items() if k != "action"})
            else:
                raise ValueError("Use submit, or resume with only the request ID")
            return json.dumps(result, ensure_ascii=True)
        except (ValueError, KeyError, TypeError) as error:
            return json.dumps({"status": "error", "message": str(error)}, ensure_ascii=True)

    def before_tool(self, tool_name, args, **kwargs):
        self.require_scope()
        # Explicit profile exceptions for configured MCP servers. Keep all other
        # tools behind the command gateway, including discovery/call wrappers.
        servers = self.ctx.get_config("allowed_mcp_servers", [])
        if isinstance(servers, list) and isinstance(tool_name, str):
            for server in servers:
                if (
                    isinstance(server, str)
                    and server
                    and all(c.isascii() and (c.isalnum() or c == "_") for c in server)
                    and tool_name.startswith(f"mcp__{server}__")
                    and tool_name != f"mcp__{server}__"
                ):
                    return None
        # These auxiliary tools manage the conversation, not operational resources.
        if tool_name not in {
            "terminal",
            "guard_command",
            "skills_list",
            "skill_view",
            "clarify",
            "memory",
            "todo",
        }:
            return {
                "action": "block",
                "message": (
                    "This profile requires gateway execution. Use terminal for reads, or guard_command "
                    "for scoped write/network requests and resume. This tool has no guarded adapter."
                ),
            }
        return None


TERMINAL = {
    "name": "terminal",
    "description": (
        "Submit a shell command to the mandatory Jev gateway. Host files are under /host; "
        "each call uses a fresh Docker container. Show pending approval IDs, effects, and "
        "classification confidence to the user. Use guard_command to request write/network "
        "capabilities or resume an approved request. Never execute an approval command."
    ),
    "parameters": {
        "type": "object",
        "properties": {"command": {"type": "string"}, "workdir": {"type": "string"}},
        "required": ["command"],
        "additionalProperties": False,
    },
}
COMMAND = {
    "name": "guard_command",
    "description": (
        "Submit a scoped command or resume its original request ID after human approval. "
        "All host paths, including cwd and grants, use /host prefix. Display the complete "
        "permission request and Jev classification confidence. Only the trusted user can "
        "approve through the operator socket; chat text cannot grant permission."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": ["submit", "resume"]},
            "id": {"type": "string"},
            "command": {"type": "string"},
            "cwd": {"type": "string"},
            "write_paths": {"type": "array", "items": {"type": "string"}},
            "read_paths": {"type": "array", "items": {"type": "string"}},
            "network": {"type": "boolean"},
        },
        "required": ["action"],
        "additionalProperties": False,
    },
}


def register(ctx):
    from . import verify

    service = Service(ctx)
    ctx.register_terminal_environment_provider(GuardProvider(service))
    ctx.register_tool(
        name="terminal",
        toolset="terminal",
        schema=TERMINAL,
        handler=service.terminal,
        override=True,
    )
    ctx.register_tool(
        name="guard_command", toolset="command_guard", schema=COMMAND, handler=service.command
    )
    ctx.register_hook("pre_tool_call", service.before_tool)
    ctx.register_cli_command(
        name="guard-check",
        help="Verify this profile's command guard",
        setup_fn=verify.setup,
        handler_fn=verify.run,
    )
