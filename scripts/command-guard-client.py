#!/usr/bin/env python3
"""Agent-only client. Install separately from protected gateway source and credentials."""

import argparse
import json
import os
import socket
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--socket",
        default=str(Path(__file__).resolve().parents[1] / ".command-guard/sockets/agent.sock"),
    )
    sub = parser.add_subparsers(dest="action", required=True)
    submit = sub.add_parser("submit")
    submit.add_argument("--command", required=True)
    submit.add_argument("--cwd", default=os.getcwd())
    submit.add_argument("--write", action="append", default=[])
    submit.add_argument("--read", action="append", default=[])
    submit.add_argument("--network", action="store_true")
    sub.add_parser("resume").add_argument("id")
    args = parser.parse_args()
    message = {"action": args.action}
    if args.action == "submit":
        message["request"] = {
            "command": args.command,
            "cwd": args.cwd,
            "write_paths": args.write,
            "read_paths": args.read,
            "network": args.network,
        }
    else:
        message["id"] = args.id
    payload = json.dumps(message).encode() + b"\n"
    if len(payload) > 65536:
        parser.error("Request exceeds 65536 bytes")
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(75)
            connection.connect(args.socket)
            connection.sendall(payload)
            with connection.makefile("rb") as stream:
                result = json.loads(stream.readline(14000000))
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Gateway connection failed: {type(exc).__name__}\n")
    print(json.dumps(result, indent=2, ensure_ascii=True))
    status = result.get("status")
    if status == "pending_approval":
        raise SystemExit(3)
    if status == "finished":
        code = result["exit_code"]
        raise SystemExit(124 if result["timed_out"] else (128 - code if code < 0 else code))
    if status == "error":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
