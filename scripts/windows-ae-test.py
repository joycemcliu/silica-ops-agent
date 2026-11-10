#!/usr/bin/env python3
"""Preflight or launch one isolated AE diagnostic through the existing WinRM client.

Not executed end-to-end against Windows/AE during implementation.
"""

import argparse
import base64
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import sys


SCRIPTS = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("windows_winrm_session", SCRIPTS / "windows-winrm-session.py")
winrm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(winrm)


def positive(value):
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return number


def windows_path(value):
    if not re.match(r"^(?:[A-Za-z]:\\|\\\\[^\\]+\\[^\\]+)", value) or any(c in value for c in '\x00\r\n"'):
        raise argparse.ArgumentTypeError("must be an absolute Windows path without quotes or control characters")
    return value


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--host", required=True, type=ipaddress.IPv4Address)
    result.add_argument("--credentials", default=os.environ.get("WINRM_CREDENTIALS_FILE") or str(
        Path.home() / ".local/secrets/silica-prod-windows-password"))
    result.add_argument("--https", action="store_true")
    result.add_argument("--port", type=positive)
    result.add_argument("--worker-pid", required=True, type=positive)
    result.add_argument("--worker-exe", required=True, type=windows_path, help="Expected full path of the live worker executable")
    result.add_argument("--aerender", required=True, type=windows_path)
    result.add_argument("--project", required=True, type=windows_path, help="AEPX with absolute fileReference paths")
    result.add_argument("--comp", required=True)
    result.add_argument("--working-directory", required=True, type=windows_path, help="Worker's configured working directory")
    result.add_argument("--output-root", required=True, type=windows_path, help="Existing local directory for unique run directories")
    result.add_argument("--output-name", default="output.mp4", help="Single output filename; image sequences are unsupported")
    result.add_argument("--ffprobe", required=True, type=windows_path)
    result.add_argument("--ffmpeg", required=True, type=windows_path)
    result.add_argument("--expected-frames", required=True, type=positive)
    result.add_argument("--input-path", action="append", default=[], type=windows_path, help="Additional input file/directory to verify")
    result.add_argument("--dump-directory", type=windows_path, help="AE Sentry reports directory in the worker's profile")
    result.add_argument("--mfr", choices=("ON", "OFF"), default="ON")
    result.add_argument("--mfr-cpu", type=int, choices=range(1, 101), default=60, metavar="1..100")
    result.add_argument("--memory", type=int, nargs=2, default=[50, 80], metavar=("CACHE", "MAX"))
    result.add_argument("--timeout-seconds", type=positive, default=720, help="Total render and validation deadline")
    result.add_argument("--execute", action="store_true", help="Create a temporary interactive task and run AE; default is read-only preflight")
    return result


def build_command(args):
    request = {key: value for key, value in vars(args).items() if key not in {"host", "credentials", "https", "port"}}
    source = (SCRIPTS / "windows-ae-test.ps1").read_text(encoding="utf-8")
    request["runner_source"] = base64.b64encode(source.encode()).decode("ascii")
    encoded = base64.b64encode(json.dumps(request).encode()).decode("ascii")
    # Values travel as JSON data; none are interpolated into executable PowerShell.
    return "& {\n" + source + "\n} -RequestBase64 '" + encoded + "'"


def main(argv=None):
    cli = parser()
    args = cli.parse_args(argv)
    if args.port is not None and args.port > 65535:
        cli.error("--port must be between 1 and 65535")
    if any(value < 10 or value > 100 for value in args.memory):
        cli.error("--memory values must be between 10 and 100")
    if not args.project.lower().endswith(".aepx"):
        cli.error("--project must be an AEPX file with absolute media references")
    if not re.match(r"^[A-Za-z]:\\", args.output_root):
        cli.error("--output-root must be a local drive path")
    if not re.fullmatch(r"[^<>:\"/\\|?*\x00-\x1f]+\.(?:mp4|mov|avi)", args.output_name, re.IGNORECASE):
        cli.error("--output-name must be a single .mp4, .mov, or .avi filename")
    if not args.comp.strip() or any(c in args.comp for c in "\x00\r\n"):
        cli.error("--comp must be a nonempty single-line name")
    try:
        username, password = winrm.load_credentials(args.credentials)
        from pypsrp.powershell import PowerShell, RunspacePool
        from pypsrp.wsman import WSMan
        args.host = str(args.host)
        args.command = build_command(args)
        return winrm.run_session(args, username, password, WSMan, RunspacePool, PowerShell)
    except (OSError, ValueError):
        print("ERROR: Check local credentials permissions/format and runner files.", file=sys.stderr)
        return 2
    except ImportError:
        print("ERROR: WinRM dependency unavailable in the repository-local .venv.", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted. The remote task has its own deadline; inspect its retained run directory.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"ERROR: AE diagnostic connection failed ({type(exc).__name__}); remote evidence may still be running.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
