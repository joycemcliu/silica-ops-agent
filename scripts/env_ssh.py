import os
from pathlib import Path
import re
import selectors
import shlex
import signal
import subprocess
import sys
import tempfile
import time

from access_common import AccessError, bounded_integer, capture, child_environment, redact, stop_process
from env_config import ConfigError, load_config
from ssh_policy import command_arguments


def environment_config():
    root = Path(__file__).resolve().parent.parent
    try:
        config = load_config(os.environ.get("OPS_ENVS_FILE", root / "envs.yaml"))
        environment = os.environ.get("OPS_ENV", "")
        if environment not in config["environments"]:
            raise AccessError("Select a configured environment with OPS_ENV.")
        return config["environments"][environment]
    except ConfigError:
        raise AccessError("Invalid environment configuration (values suppressed).") from None


def wait_for_port(process, timeout):
    deadline = time.monotonic() + timeout
    buffered = bytearray()
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        while time.monotonic() < deadline:
            if not selector.select(0.1):
                continue
            chunk = os.read(process.stdout.fileno(), 4096)
            if not chunk:
                break
            buffered.extend(chunk)
            match = re.search(rb"Forwarding from 127\.0\.0\.1:([0-9]+) -> [0-9]+\r?\n", buffered)
            if match and 1 <= int(match[1]) <= 65535:
                return int(match[1])
            if len(buffered) > 16384:
                break
    raise AccessError("Port-forward did not become ready.")


def pinned_host_key(port, fingerprint, timeout, processes):
    if fingerprint == "SHA256:" + "A" * 43:
        raise AccessError("Replace the placeholder SSH host-key fingerprint before connecting.")
    process = subprocess.Popen(
        ["ssh-keyscan", "-T", str(timeout), "-p", str(port), "127.0.0.1"],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        env=child_environment(), start_new_session=True,
    )
    processes.append(process)
    output, status = capture(process, timeout, 32768)
    if status:
        raise AccessError("Could not obtain the pinned SSH host key.")
    for line in output.splitlines():
        if not line or line.startswith(b"#") or len(line) > 8192:
            continue
        result = subprocess.run(
            ["ssh-keygen", "-l", "-E", "sha256", "-f", "-"],
            input=line + b"\n", stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=timeout, env=child_environment(), check=False,
        )
        fields = result.stdout.decode("ascii", errors="replace").split()
        if result.returncode == 0 and len(fields) >= 2 and fields[1] == fingerprint:
            return line + b"\n"
    raise AccessError("SSH host key does not match the configured fingerprint.")


def interrupted(_signal_number, _frame):
    raise AccessError("SSH operation interrupted.")


def main():
    processes = []
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        if len(sys.argv) != 2:
            raise AccessError('Usage: env-ssh.sh "<read-only command>"')
        arguments = command_arguments(sys.argv[1])
        config = environment_config()
        username = os.environ.get("OPS_SSH_USER", "")
        password = os.environ.get("OPS_SSH_PASSWORD", "")
        if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", username) or not password or len(password) > 4096 or "\0" in password:
            raise AccessError("Provide the selected environment's SSH account and password.")
        timeout = bounded_integer("OPS_SSH_TIMEOUT_SECONDS", 30, 1, 120)
        connect_timeout = bounded_integer("OPS_CONNECT_TIMEOUT_SECONDS", 10, 1, 30)
        output_limit = bounded_integer("OPS_OUTPUT_LIMIT_BYTES", 65536, 1024, 1048576)
        ssh_config = config["ssh"]
        forward = subprocess.Popen(
            ["kubectl", "--context", config["kube_context"], "--namespace", config["namespace"],
             "port-forward", "--address=127.0.0.1", ssh_config["target"], f':{ssh_config["port"]}'],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=child_environment(kubernetes=True), start_new_session=True,
        )
        processes.append(forward)
        port = wait_for_port(forward, connect_timeout)
        key = pinned_host_key(port, ssh_config["host_key_fingerprint"], connect_timeout, processes)
        with tempfile.TemporaryDirectory(prefix="ops-ssh-") as temporary_directory:
            known_hosts = Path(temporary_directory) / "known_hosts"
            known_hosts.write_bytes(key)
            known_hosts.chmod(0o600)
            ssh_environment = child_environment()
            ssh_environment["SSHPASS"] = password
            process = subprocess.Popen(
                ["sshpass", "-e", "ssh", "-F", "/dev/null", "-a", "-n", "-T", "-p", str(port),
                 "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={known_hosts}",
                 "-o", "GlobalKnownHostsFile=/dev/null", "-o", "PreferredAuthentications=password",
                 "-o", "PubkeyAuthentication=no", "-o", "KbdInteractiveAuthentication=no",
                 "-o", "NumberOfPasswordPrompts=1", "-o", f"ConnectTimeout={connect_timeout}",
                 "-o", "ConnectionAttempts=1", "-o", "ClearAllForwardings=yes",
                 "-o", "PermitLocalCommand=no", "-o", "LogLevel=ERROR",
                 f"{username}@127.0.0.1", shlex.join(arguments)],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                env=ssh_environment, start_new_session=True,
            )
            processes.append(process)
            secrets = [os.environ.get(name, "") for name in ("OPS_SSH_PASSWORD", "NOMAD_TOKEN", "PGPASSWORD", "OPS_API_TOKEN")]
            lookahead = max(len(secret.encode()) for secret in secrets)
            output, status = capture(process, timeout, output_limit + lookahead)
            cleaned = redact(output, secrets).encode("utf-8")
            sys.stdout.buffer.write(cleaned[:output_limit])
            if status == 124:
                print("\nSSH command timed out.", file=sys.stderr)
            elif status == 125 or len(cleaned) > output_limit:
                print("\nSSH output limit reached.", file=sys.stderr)
                status = 125
            return status if status >= 0 else 128 - status
    except AccessError as error:
        print(str(error), file=sys.stderr)
        return 1
    except (OSError, subprocess.SubprocessError):
        print("SSH operation failed (details suppressed).", file=sys.stderr)
        return 1
    finally:
        for process in reversed(processes):
            stop_process(process)


if __name__ == "__main__":
    sys.exit(main())
