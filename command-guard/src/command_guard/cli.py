"""Agent client, trusted operator console, and service entrypoint."""

import argparse
import grp
import json
import os
import signal
import socket
import sys
import threading
from dataclasses import replace
from pathlib import Path

from .approval.requests import render
from .assessment.jev import Jev
from .audit import Audit
from .execution.runner import Runner
from .gateway import Gateway
from .policy import Policy
from .server import MAX_MESSAGE, Server


def exchange(path, message):
    raw = json.dumps(message).encode() + b"\n"
    if len(raw) > MAX_MESSAGE:
        raise ValueError("Request exceeds protocol size limit")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(75)
        connection.connect(path)
        connection.sendall(raw)
        with connection.makefile("rb") as stream:
            response = stream.readline(14000000)
        return json.loads(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", default=str(Path.cwd() / ".command-guard/sockets/agent.sock"))
    sub = parser.add_subparsers(dest="action", required=True)
    submit = sub.add_parser("submit")
    submit.add_argument("--command", required=True)
    submit.add_argument("--cwd", default=os.getcwd())
    submit.add_argument("--write", action="append", default=[])
    submit.add_argument("--read", action="append", default=[])
    submit.add_argument("--network", action="store_true")
    for action in ("resume", "inspect", "approve", "decline"):
        sub.add_parser(action).add_argument("id")
    sub.add_parser("list")
    service = sub.add_parser("serve")
    service.add_argument("--policy", required=True)
    service.add_argument("--operator-socket", default="/run/command-guard/operator.sock")
    service.add_argument("--agent-group", required=True)
    service.add_argument("--operator-group", required=True)
    service.add_argument("--audit", required=True)
    sub.add_parser("cleanup").add_argument("--policy", required=True)
    args = parser.parse_args()
    if args.action == "cleanup":
        Runner(Policy.load(args.policy)).cleanup()
        return
    if args.action == "serve":
        policy = Policy.load(args.policy)
        policy = replace(
            policy,
            protected_paths=tuple(
                sorted(
                    set(
                        (
                            *policy.protected_paths,
                            str(Path(__file__).resolve().parent),
                            str(Path(sys.prefix).resolve()),
                            str(Path(args.policy).resolve()),
                            str(Path(args.audit).resolve().parent),
                            str(Path(args.socket).resolve().parent),
                            str(Path(args.operator_socket).resolve().parent),
                        )
                    )
                )
            ),
        )
        runner = Runner(policy)
        runner.cleanup()
        gateway = Gateway(policy, Jev(policy), runner, Audit(args.audit))
        agent_gid = (
            int(args.agent_group)
            if args.agent_group.isdecimal()
            else grp.getgrnam(args.agent_group).gr_gid
        )
        operator_gid = (
            int(args.operator_group)
            if args.operator_group.isdecimal()
            else grp.getgrnam(args.operator_group).gr_gid
        )
        if agent_gid == operator_gid:
            parser.error("Agent and operator groups must be different")
        os.umask(0o077)
        with (
            Server(args.socket, gateway, False, agent_gid) as agent,
            Server(args.operator_socket, gateway, True, operator_gid) as operator,
        ):
            stopped = threading.Event()
            signal.signal(signal.SIGTERM, lambda *_: stopped.set())
            signal.signal(signal.SIGINT, lambda *_: stopped.set())
            for server in (agent, operator):
                threading.Thread(target=server.serve_forever, daemon=True).start()
            stopped.wait()
            agent.shutdown()
            operator.shutdown()
            runner.cleanup()
        for path in (args.socket, args.operator_socket):
            os.unlink(path)
        return
    message = {"action": args.action}
    if args.action == "submit":
        message["request"] = {
            "command": args.command,
            "cwd": args.cwd,
            "write_paths": args.write,
            "read_paths": args.read,
            "network": args.network,
        }
    elif args.action in {"resume", "inspect", "approve", "decline"}:
        message["id"] = args.id
    try:
        if args.action == "approve":
            record = exchange(args.socket, {"action": "inspect", "id": args.id})
            print(render(record), flush=True)
            if record.get("status") == "error":
                raise SystemExit(1)
            with open("/dev/tty", "r+", encoding="utf-8") as terminal:
                terminal.write(f"Type 'approve {args.id}' to grant this exact request: ")
                terminal.flush()
                if terminal.readline().strip() != f"approve {args.id}":
                    raise SystemExit("Approval cancelled")
        result = exchange(args.socket, message)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Gateway connection failed: {type(exc).__name__}\n")
    print(render(result))
    if result.get("status") == "error":
        raise SystemExit(1)
    if result.get("status") == "pending_approval":
        raise SystemExit(3)
    if result.get("status") == "finished":
        code = result["exit_code"]
        raise SystemExit(124 if result["timed_out"] else (128 - code if code < 0 else code))


if __name__ == "__main__":
    main()
