#!/usr/bin/env python3
"""PowerShell over WinRM using ~/.local/secrets/silica-prod-windows-password."""

import argparse
import ipaddress
import json
import os
from pathlib import Path
import stat
import sys


def load_credentials(filename):
    """Validate location and permissions before reading any secret content."""
    root = (Path.home() / ".local/secrets").resolve()
    path = Path(filename).expanduser().resolve()
    if not path.is_relative_to(root):
        raise ValueError("Credentials must be inside ${HOME}/.local/secrets/.")
    # Inspect the opened file as well as its resolved location.
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, encoding="utf-8") as stream:
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode):
            raise ValueError("Credentials must be a regular file.")
        if metadata.st_uid != os.getuid() or metadata.st_mode & 0o077:
            raise ValueError("Credentials must belong to this user and have owner-only permissions (chmod 600).")
        try:
            data = json.load(stream)
        except (ValueError, UnicodeError):
            raise ValueError("Credentials must be valid UTF-8 JSON.") from None
    if not isinstance(data, dict) or any(
        not isinstance(data.get(key), str)
        for key in ("username", "password")
    ):
        raise ValueError("Credentials require username and password strings (empty strings are allowed).")
    return data["username"], data["password"]


def invoke(pool, command, powershell_class):
    ps = powershell_class(pool)
    # One runspace and global script scope retain variables and location.
    ps.add_script(command, use_local_scope=False)
    ps.add_cmdlet("Out-String").add_parameter("Width", 160)
    for output in ps.invoke():
        print(output, end="")
    for error in ps.streams.error:
        print(f"ERROR: {error}", file=sys.stderr)
    return 1 if ps.had_errors else 0


def run_session(args, username, password, wsman_class, pool_class, powershell_class):
    with wsman_class(
        args.host, username=username, password=password,
        ssl=args.https, port=args.port or (5986 if args.https else 5985),
        auth="ntlm", encryption="always", cert_validation=True, no_proxy=True,
    ) as connection:
        with pool_class(connection, min_runspaces=1, max_runspaces=1) as pool:
            if args.command is not None:
                return invoke(pool, args.command, powershell_class)
            print("Connected. Enter one-line PowerShell commands; type exit to disconnect.")
            while True:
                try:
                    command = input("PS remote> ")
                except EOFError:
                    print()
                    break
                if command.strip().lower() == "exit":
                    break
                if command.strip():
                    invoke(pool, command, powershell_class)
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, type=ipaddress.IPv4Address, help="Windows LAN IPv4 address")
    parser.add_argument(
        "--credentials",
        default=os.environ.get("WINRM_CREDENTIALS_FILE") or str(
            Path.home() / ".local/secrets/silica-prod-windows-password"
        ),
        help="JSON credentials file (default: ~/.local/secrets/silica-prod-windows-password; WINRM_CREDENTIALS_FILE overrides it)",
    )
    parser.add_argument("-c", "--command", help="Run one PowerShell script, then close; otherwise open a persistent prompt")
    parser.add_argument("--https", action="store_true", help="Use HTTPS with certificate verification")
    parser.add_argument("--port", type=int, help="Override port (default: 5985, or 5986 with --https)")
    args = parser.parse_args()
    args.host = str(args.host)
    if args.port is not None and not 1 <= args.port <= 65535:
        parser.error("--port must be between 1 and 65535.")
    if args.command is None and not sys.stdin.isatty():
        parser.error("Interactive mode requires a terminal; use --command for agent/noninteractive checks.")
    try:
        username, password = load_credentials(args.credentials)
    except ValueError as exc:
        parser.exit(2, f"ERROR: {exc}\n")
    except OSError:
        parser.exit(2, "ERROR: Cannot open credentials file; check its path and permissions.\n")
    try:
        from pypsrp.powershell import PowerShell, RunspacePool
        from pypsrp.wsman import WSMan
    except ImportError:
        parser.exit(2, "ERROR: WinRM dependencies unavailable. Run scripts/setup-windows-winrm.sh and use its venv Python.\n")
    try:
        return run_session(args, username, password, WSMan, RunspacePool, PowerShell)
    except KeyboardInterrupt:
        print("\nSession interrupted and closed.", file=sys.stderr)
        return 130
    except Exception as exc:
        # Transport exceptions may contain authentication/request details. Do not
        # emit their text or traceback; remote PowerShell errors print above.
        print(f"ERROR: WinRM session failed ({type(exc).__name__}). Check tunnel, Windows listener/firewall, credentials, and remoting permissions; see docs/windows-winrm.md.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
