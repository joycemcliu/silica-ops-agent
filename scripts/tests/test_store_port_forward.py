"""Test forwarding with fake tools; TCP checks use loopback only."""

import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time
import unittest


SCRIPTS = Path(__file__).resolve().parents[1]
BASH = "/bin/bash"  # Exercise the system Bash (3.2 on macOS).


class StorePortForwardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "calls.jsonl"
        tool = self.bin / "fake-tool"
        tool.write_text(f"#!{SCRIPTS.parent / '.venv/bin/python'}\n" + """
import json, os, pathlib, re, select, socket, sys, time
name = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
root = pathlib.Path(os.environ['TEST_ROOT'])
with open(root / 'calls.jsonl', 'a') as log:
    log.write(json.dumps([name, args]) + '\\n')
if name == 'kubectl':
    if 'port-forward' in args:
        listeners = []
        if os.environ.get('LOCAL_TCP'):
            for arg in args:
                if ':' in arg and arg.split(':')[0].isdigit():
                    listener = socket.socket()
                    listener.bind(('127.0.0.1', int(arg.split(':')[0])))
                    listener.listen()
                    listeners.append(listener)
            stdin = os.fstat(0)
            null = os.stat('/dev/null')
            (root / ('session-' + str(os.getpid()))).write_text(json.dumps({
                'sid': os.getsid(0), 'stdin_null': (stdin.st_dev, stdin.st_ino) == (null.st_dev, null.st_ino)
            }))
        for arg in args:
            if ':' in arg and arg.split(':')[0].isdigit():
                (root / ('port-' + arg.split(':')[0])).write_text(str(os.getpid()))
        if listeners:
            while True:
                ready, _, _ = select.select(listeners, [], [], 1)
                for listener in ready:
                    connection, _ = listener.accept()
                    with connection:
                        connection.sendall(b'test-forward\\n')
        time.sleep(30)
    elif 'statefulset' in args:
        print('26')
    elif 'pods' in args:
        print('pod/teststore-socat-nomad-1-test')
elif name == 'nc':
    sys.exit(0 if os.environ.get('REUSE_COMMAND') or (root / ('port-' + args[-1])).exists() else 1)
elif name == 'pgrep':
    if os.environ.get('REUSE_COMMAND') and re.search(args[-1], os.environ['REUSE_COMMAND']):
        print('4242')
        sys.exit(0)
    sys.exit(1)
elif name == 'ps' and os.environ.get('REUSE_COMMAND'):
    print(os.environ['REUSE_COMMAND'])
elif name in ('ssh', 'sshuttle'):
    sys.exit(int(os.environ.get('CLIENT_STATUS', '0')))
""")
        tool.chmod(0o755)
        for name in ("kubectl", "nc", "ps", "pgrep", "ssh", "sshuttle"):
            (self.bin / name).symlink_to(tool)
        self.env = {
            "PATH": f"{self.bin}:/usr/bin:/bin", "HOME": str(self.root),
            "TMPDIR": str(self.root), "XDG_RUNTIME_DIR": str(self.root),
            "SKIP_GKE_CONTEXT": "1", "PROD_SSH_PASSWORD_FILE": "",
            "TEST_ROOT": str(self.root),
        }
        self.addCleanup(self.stop_forwards)

    def stop_forwards(self):
        for marker in self.root.glob("port-*"):
            try:
                os.kill(int(marker.read_text()), signal.SIGTERM)
            except ProcessLookupError:
                pass
            marker.unlink()

    def test_final_forwards_bind_ipv4_and_preserve_client_status(self):
        for script in ("store-port-forward.sh", "store-port-forward-ssh.sh", "store-sshuttle.sh"):
            statuses = (0,) if script == "store-port-forward.sh" else (0, 7)
            for status in statuses:
                with self.subTest(script=script, status=status):
                    self.log.unlink(missing_ok=True)
                    result = subprocess.run(
                        [BASH, str(SCRIPTS / script), "--store", "teststore", "--node", "1"],
                        env={**self.env, "CLIENT_STATUS": str(status)}, cwd=self.root,
                        capture_output=True, text=True, timeout=10,
                    )
                    self.assertEqual(result.returncode, status, result.stderr)
                    self.assertNotIn("unbound variable", result.stderr)
                    calls = [args for name, args in map(json.loads, self.log.read_text().splitlines())
                             if name == "kubectl" and "port-forward" in args]
                    self.assertEqual(len(calls), 2 if script == "store-port-forward.sh" else 1)
                    for args in calls:
                        self.assertEqual(args[args.index("--address") + 1], "127.0.0.1")
                    if script != "store-port-forward.sh":
                        for marker in self.root.glob("port-*"):
                            with self.assertRaises(ProcessLookupError):
                                os.kill(int(marker.read_text()), 0)
                    self.stop_forwards()

    def test_ssh_helpers_reuse_ipv4_forwards(self):
        command = ("kubectl --context gke_infra-automate-production_us-west1_default-us-west1 "
                   "-n stores-socat port-forward pod/teststore-socat-shared-1 "
                   "--address 127.0.0.1 15026:22")
        for script in ("store-port-forward-ssh.sh", "store-sshuttle.sh"):
            with self.subTest(script=script):
                self.log.unlink(missing_ok=True)
                result = subprocess.run(
                    [BASH, str(SCRIPTS / script), "--store", "teststore", "--node", "1"],
                    env={**self.env, "REUSE_COMMAND": command}, cwd=self.root,
                    capture_output=True, text=True, timeout=5,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                calls = list(map(json.loads, self.log.read_text().splitlines()))
                self.assertFalse(any(name == "kubectl" and "port-forward" in args
                                     for name, args in calls))

    def test_store_forwards_survive_launcher_exit_and_group_cleanup(self):
        # Reserve four distinct ports until all have been selected.
        reservations = [socket.socket() for _ in range(4)]
        try:
            for reservation in reservations:
                reservation.bind(("127.0.0.1", 0))
            ports = [reservation.getsockname()[1] for reservation in reservations]
        finally:
            for reservation in reservations:
                reservation.close()
        overrides = dict(zip(("NOMAD_LOCAL_PORT", "CONSUL_LOCAL_PORT", "HTTPS_LOCAL_PORT",
                              "POSTGRES_LOCAL_PORT"), map(str, ports)))
        launcher = subprocess.Popen(
            [BASH, str(SCRIPTS / "store-port-forward.sh"), "--store", "teststore", "--node", "1"],
            env={**self.env, **overrides, "LOCAL_TCP": "1"}, cwd=self.root,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, start_new_session=True,
        )
        try:
            stdout, stderr = launcher.communicate("launcher input\n", timeout=10)
        finally:
            # Simulate the agent/terminal cleaning up the launching process group.
            try:
                os.killpg(launcher.pid, signal.SIGHUP)
            except ProcessLookupError:
                pass
            if launcher.poll() is None:
                launcher.kill()
                launcher.wait()
        self.assertEqual(launcher.returncode, 0, stdout + stderr)
        pids = {int(marker.read_text()) for marker in self.root.glob("port-*")}
        self.assertEqual(len(pids), 2)
        for pid in pids:
            state = json.loads((self.root / f"session-{pid}").read_text())
            self.assertEqual(state["sid"], pid)
            self.assertNotEqual(state["sid"], launcher.pid)
            self.assertTrue(state["stdin_null"])
        # Use every forwarded endpoint from a separate, short-lived command.
        client = subprocess.run([
            str(SCRIPTS.parent / ".venv/bin/python"), "-c",
            "import socket, sys\nfor port in sys.argv[1:]:\n"
            " with socket.create_connection(('127.0.0.1', int(port)), timeout=2) as connection:\n"
            "  assert connection.recv(100) == b'test-forward\\n'\n",
            *map(str, ports),
        ], capture_output=True, text=True, timeout=10)
        self.assertEqual(client.returncode, 0, client.stderr)
        stopped = subprocess.run(["/bin/kill", "-TERM", *map(str, pids)], capture_output=True, timeout=5)
        self.assertEqual(stopped.returncode, 0, stopped.stderr)
        for port in ports:
            deadline = time.monotonic() + 3
            while True:
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                        pass
                except OSError:
                    break
                self.assertLess(time.monotonic(), deadline, "Forward did not stop")
                time.sleep(0.01)

    def test_exit_cleanup_handles_empty_and_populated_probe_arrays(self):
        for script in ("store-port-forward.sh", "store-port-forward-ssh.sh"):
            source = (SCRIPTS / script).read_text()
            if script == "store-port-forward.sh":
                cleanup = source[source.index('PROBE_DIR=""'):source.index('# Measure the remote SSH greeting')]
            else:
                cleanup = source[source.index('CREATED_PORT_FORWARD_PID=""'):source.index('require_command() {')]
            for populated in (False, True):
                for action, status in (("exit 0", 0), ("exit 7", 7),
                                       ("kill -INT $$", 130), ("kill -TERM $$", 143),
                                       ("kill -HUP $$", 129)):
                    with self.subTest(script=script, populated=populated, action=action):
                        body = "set -Eeuo pipefail\n" + cleanup
                        body += '\nsleep 30 >/dev/null 2>&1 &\necho $! > "$TEST_ROOT/unowned"\n'
                        if populated:
                            # Wait for child startup before signalling it; killing a
                            # freshly forked Bash child can race its signal reset.
                            body += f"'{SCRIPTS.parent / '.venv/bin/python'}' -c "
                            body += "'import os, time; print(os.getpid(), flush=True); time.sleep(30)' "
                            body += '> "$TEST_ROOT/owned" 2>/dev/null &\nPROBE_PIDS=("$!")\n'
                            body += 'while [[ ! -s "$TEST_ROOT/owned" ]]; do sleep 0.01; done\n'
                        body += action + "\n"
                        try:
                            result = subprocess.run([BASH, "-c", body], env=self.env,
                                                    capture_output=True, text=True, timeout=5)
                            self.assertEqual(result.returncode, status, result.stderr)
                            self.assertNotIn("unbound variable", result.stderr)
                            os.kill(int((self.root / "unowned").read_text()), 0)
                            if populated:
                                with self.assertRaises(ProcessLookupError):
                                    os.kill(int((self.root / "owned").read_text()), 0)
                        finally:
                            for name in ("owned", "unowned"):
                                marker = self.root / name
                                if marker.exists():
                                    try:
                                        os.kill(int(marker.read_text()), signal.SIGTERM)
                                    except ProcessLookupError:
                                        pass
                                    marker.unlink()


if __name__ == "__main__":
    unittest.main()
