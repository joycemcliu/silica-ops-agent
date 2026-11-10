"""Use temporary Git remotes and fake forwarding tools; never touch real checkouts or Kubernetes."""

import json
import os
from pathlib import Path
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest


SCRIPTS = Path(__file__).resolve().parents[1]


class StartupFixture(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name).resolve()
        self.root = self.base / "ops agent"
        (self.root / "scripts").mkdir(parents=True)
        (self.root / ".venv/bin").mkdir(parents=True)
        (self.root / ".venv/bin/python").symlink_to(sys.executable)
        self.bin = self.base / "bin"
        self.bin.mkdir()
        self.env = {**os.environ, "PATH": f"{self.bin}:{os.environ['PATH']}"}
        # Exercise real OS locks even on macOS, which lacks the flock CLI.
        self.write_tool("flock", f"#!{sys.executable}\n" + """
import fcntl, sys
flags = fcntl.LOCK_UN if '-u' in sys.argv else fcntl.LOCK_EX
if '-n' in sys.argv:
    flags |= fcntl.LOCK_NB
try:
    fcntl.flock(int(sys.argv[-1]), flags)
except BlockingIOError:
    sys.exit(1)
""")

    def write_tool(self, name, content):
        path = self.bin / name
        path.write_text(content)
        path.chmod(0o755)
        return path

    def run_shell(self, script, *args, input=None, **overrides):
        return subprocess.run(
            ["bash", str(script), *args], cwd=self.base,
            env={**self.env, **overrides}, input=input, capture_output=True, text=True, timeout=15,
        )


class SessionStartTests(StartupFixture):
    def setUp(self):
        super().setUp()
        self.script = self.root / "scripts/diagnose-agent-session-start.sh"
        shutil.copy2(SCRIPTS / "diagnose-agent-session-start.sh", self.script)
        self.env["HOME"] = str(self.base)
        self.env.pop("PROD_SSH_PASSWORD_FILE", None)
        self.env.pop("WINRM_CREDENTIALS_FILE", None)
        self.password_file = self.base / ".local/secrets/silica-prod-master-node-password"
        self.password_file.parent.mkdir(parents=True)
        self.password_file.write_text("fixture-password\n")
        self.password_file.chmod(0o600)
        self.windows_password_file = self.password_file.with_name("silica-prod-windows-password")
        self.windows_password_file.write_text(json.dumps({
            "username": r"PC\fixture-user", "password": "fixture-windows-password",
        }))
        self.windows_password_file.chmod(0o600)
        self.forward_log = self.base / "forwards.log"
        self.env["FORWARD_LOG"] = str(self.forward_log)
        (self.root / "scripts/grafana-mcp-forward.sh").write_text("""#!/usr/bin/env bash
echo "$1" >> "$FORWARD_LOG"
if [[ "$1" == status ]]; then exit "${FORWARD_STATUS:-0}"; fi
exit "${FORWARD_START_STATUS:-0}"
""")
        self.write_tool("curl", f"#!{sys.executable}\n" + """
import json, os, sys
args = sys.argv[1:]
port = args[-1].split(':')[-1].split('/')[0]
assert 'Host: localhost:' + port in args
assert 'Accept: application/json, text/event-stream' in args
request = json.loads(args[args.index('--data') + 1])
assert request['method'] == 'initialize'
mode = os.environ.get('MCP_DEV_MODE' if port == '60007' else 'MCP_PROD_MODE', 'ok')
if mode in ('refused', 'timeout', 'http403'):
    print({'refused': 'curl: (7) Connection refused',
           'timeout': 'curl: (28) Operation timed out',
           'http403': 'curl: (22) The requested URL returned error: 403'}[mode], file=sys.stderr)
    sys.exit(7)
if mode == 'invalid':
    print('not an MCP response')
    sys.exit(0)
response = {'jsonrpc': '2.0', 'id': 1, 'result': {
    'protocolVersion': '2025-06-18', 'capabilities': {'tools': {}}}}
if mode == 'error':
    response = {'jsonrpc': '2.0', 'id': 1, 'error': {'code': -32603, 'message': 'Grafana unavailable'}}
if mode == 'no_tools':
    response['result']['capabilities'] = {}
body = json.dumps(response)
print('event: message\\ndata: ' + body + '\\n' if mode == 'sse' else body)
""")
        self.env.update(GIT_AUTHOR_NAME="Test", GIT_COMMITTER_NAME="Test",
                        GIT_AUTHOR_EMAIL="test@example.com", GIT_COMMITTER_EMAIL="test@example.com",
                        GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
                        GIT_TERMINAL_PROMPT="0")
        self.repos = []
        self.remotes = []
        for name in ("silica", "silica environments"):
            remote = self.base / f"{name}.git"
            repo = self.base / name
            self.git(self.base, "init", "--bare", "--initial-branch=master", str(remote))
            self.git(self.base, "clone", str(remote), str(repo))
            (repo / "tracked").write_text("original\n")
            self.git(repo, "add", "tracked")
            self.git(repo, "commit", "-m", "initial")
            self.git(repo, "push", "-u", "origin", "master")
            self.git(repo, "checkout", "-b", "working")
            (repo / "tracked").write_text("local changes to discard\n")
            self.repos.append(repo)
            self.remotes.append(remote)
        self.config = self.root / "config.env"
        self.config.write_text("SILICA_REPO=../silica\nSILICA_ENV_REPO='../silica environments'\n")

    def git(self, cwd, *args):
        result = subprocess.run(["git", "-C", str(cwd), *args], env=self.env,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def test_updates_both_repositories_and_prunes_before_starting_forwards(self):
        for index, (repo, remote) in enumerate(zip(self.repos, self.remotes)):
            seed = self.base / f"seed-{index}"
            self.git(self.base, "clone", str(remote), str(seed))
            self.git(seed, "push", "origin", "master:stale")
            self.git(repo, "fetch")
            self.git(seed, "push", "origin", "--delete", "stale")
            (seed / "tracked").write_text("remote update\n")
            self.git(seed, "commit", "-am", "remote update")
            self.git(seed, "push")
        result = self.run_shell(self.script)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Session startup complete.", result.stdout)
        for repo in self.repos:
            self.assertEqual(self.git(repo, "branch", "--show-current"), "master")
            self.assertEqual((repo / "tracked").read_text(), "remote update\n")
            self.assertEqual(self.git(repo, "status", "--porcelain"), "")
            self.assertNotIn("origin/stale", self.git(repo, "branch", "-r"))
        self.assertEqual(self.forward_log.read_text().splitlines(), ["start", "status"])

    def test_bad_configuration_stops_before_checkout_or_forwarding(self):
        cases = [None, "SILICA_REPO=../silica\n", "SILICA_REPO=../silica\nSILICA_ENV_REPO=''\n",
                 "SILICA_REPO=../silica\nSILICA_ENV_REPO=../missing\n",
                 "SILICA_REPO=../silica\nSILICA_ENV_REPO=../silica/subdir\n"]
        (self.repos[0] / "subdir").mkdir()
        for config in cases:
            with self.subTest(config=config):
                self.config.unlink(missing_ok=True)
                if config is not None:
                    self.config.write_text(config)
                result = self.run_shell(self.script, SILICA_ENV_REPO=str(self.repos[1]))
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("config", result.stderr)
                self.assertFalse(self.forward_log.exists())
                for repo in self.repos:
                    self.assertEqual(self.git(repo, "branch", "--show-current"), "working")
                    self.assertEqual((repo / "tracked").read_text(), "local changes to discard\n")

    def test_fetch_failure_stops_before_forced_checkout(self):
        self.git(self.repos[0], "remote", "set-url", "origin", str(self.base / "missing.git"))
        result = self.run_shell(self.script)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.forward_log.exists())
        for repo in self.repos:
            self.assertEqual(self.git(repo, "branch", "--show-current"), "working")
            self.assertEqual((repo / "tracked").read_text(), "local changes to discard\n")

    def test_unreachable_forward_fails_startup(self):
        result = self.run_shell(self.script, FORWARD_STATUS="7")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Cannot use Grafana MCP servers: forwarding connectivity check failed", result.stdout)
        self.assertNotIn("Session startup complete.", result.stdout)

    def test_forward_start_failure_informs_agent(self):
        result = self.run_shell(self.script, FORWARD_START_STATUS="9")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("forwarding startup failed", result.stdout)
        self.assertEqual(self.forward_log.read_text().splitlines(), ["start"])

    def test_password_failure_is_delivered_as_hook_context(self):
        self.password_file.unlink()
        for event in ("SessionStart", "SubagentStart"):
            with self.subTest(event=event):
                result = self.run_shell(self.script, input=json.dumps({"hook_event_name": event}))
                self.assertEqual(result.returncode, 0, result.stderr)
                output = json.loads(result.stdout)
                context = output["hookSpecificOutput"]
                self.assertEqual(context["hookEventName"], event)
                self.assertIn("Inform the user", context["additionalContext"])
                self.assertIn("configure the indicated file", context["additionalContext"])
                self.assertIn(str(self.password_file), context["additionalContext"])
                self.assertNotIn("fixture-password", result.stdout + result.stderr)
                self.assertFalse(self.forward_log.exists())

    def test_mcp_checks_both_servers_and_reports_failure_reasons(self):
        cases = {"refused": "Connection refused", "timeout": "Operation timed out",
                 "http403": "403", "invalid": "invalid MCP initialize response",
                 "error": "Grafana unavailable", "no_tools": "missing tools capability"}
        for mode, reason in cases.items():
            with self.subTest(mode=mode):
                result = self.run_shell(self.script, MCP_DEV_MODE=mode, MCP_PROD_MODE="refused")
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("sandbox_dev_grafana", result.stdout)
                self.assertIn(reason, result.stdout)
                self.assertIn("sandbox_prod_grafana", result.stdout)
                self.assertIn("Connection refused", result.stdout)
                self.assertIn("Inform the user", result.stdout)
                self.assertNotIn("Session startup complete.", result.stdout)

    def test_mcp_failure_is_delivered_as_hook_context_without_progress_output(self):
        result = self.run_shell(self.script, input='{"hook_event_name":"SessionStart"}',
                                MCP_PROD_MODE="timeout")
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertIn("sandbox_prod_grafana", output["hookSpecificOutput"]["additionalContext"])
        self.assertIn("Operation timed out", output["systemMessage"])
        self.assertIn("Updating", result.stderr)

    def test_mcp_accepts_sse_and_hook_success_warns_about_runtime_connections(self):
        result = self.run_shell(self.script, input='{"hook_event_name":"SessionStart"}',
                                MCP_DEV_MODE="sse")
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Session startup complete.", context)
        self.assertIn("does not verify the agent runtime connections", context)
        self.assertIn("MCP handshake succeeded", result.stderr)

    def test_invalid_password_file_stops_before_git_updates_or_forwarding(self):
        missing = self.base / "missing-password"
        empty = self.base / "empty-password"
        empty.write_text("")
        blank = self.base / "blank-password"
        blank.write_text("\nfixture-password\n")
        exposed = self.base / "exposed-password"
        exposed.write_text("fixture-password\n")
        for path in (empty, blank):
            path.chmod(0o600)
        exposed.chmod(0o640)
        paths = ["", str(missing), str(empty), str(blank), str(exposed), str(self.base)]
        if os.geteuid() != 0:
            unreadable = self.base / "unreadable-password"
            unreadable.write_text("fixture-password\n")
            unreadable.chmod(0o000)
            paths.append(str(unreadable))
        for password_path in paths:
            with self.subTest(path=password_path):
                result = self.run_shell(self.script, PROD_SSH_PASSWORD_FILE=password_path)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("password", result.stderr.lower())
                self.assertNotIn("fixture-password", result.stdout + result.stderr)
                self.assertFalse(self.forward_log.exists())
                for repo in self.repos:
                    self.assertEqual(self.git(repo, "branch", "--show-current"), "working")
                    self.assertEqual((repo / "tracked").read_text(), "local changes to discard\n")

    def test_password_override_accepts_repo_relative_path_without_trailing_newline(self):
        custom = self.root / "custom password"
        custom.write_text("fixture-password")
        custom.chmod(0o400)
        self.password_file.unlink()
        result = self.run_shell(self.script, PROD_SSH_PASSWORD_FILE=custom.name)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("fixture-password", result.stdout + result.stderr)

    def test_missing_default_password_file_does_not_fall_back_to_interactive_auth(self):
        self.password_file.unlink()
        result = self.run_shell(self.script)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must exist and be readable", result.stderr)
        self.assertFalse(self.forward_log.exists())
        self.assertEqual(self.git(self.repos[0], "branch", "--show-current"), "working")

    def test_missing_windows_password_file_stops_before_git_updates_or_forwarding(self):
        self.windows_password_file.unlink()
        result = self.run_shell(self.script)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Windows password file", result.stderr)
        self.assertFalse(self.forward_log.exists())
        for repo in self.repos:
            self.assertEqual(self.git(repo, "branch", "--show-current"), "working")
            self.assertEqual((repo / "tracked").read_text(), "local changes to discard\n")

    def test_invalid_windows_credentials_fail_without_exposing_contents(self):
        valid = json.dumps({"username": "fixture-user", "password": "fixture-windows-password"})
        cases = [(content, 0o600) for content in (
            "", '{"password":"fixture-windows-password"', '{}', '[]',
            '{"username":123,"password":"fixture-windows-password"}',
            '{"username":"fixture-user","password":null}',
        )] + [(valid, 0o640)]
        for content, mode in cases:
            with self.subTest(content=content, mode=mode):
                self.windows_password_file.write_text(content)
                self.windows_password_file.chmod(mode)
                result = self.run_shell(self.script)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("Windows password file", result.stderr)
                self.assertNotIn("fixture-windows-password", result.stdout + result.stderr)
                self.assertFalse(self.forward_log.exists())
                for repo in self.repos:
                    self.assertEqual(self.git(repo, "branch", "--show-current"), "working")

    def test_windows_credentials_override_allows_empty_strings_like_winrm_client(self):
        custom = self.windows_password_file.with_name("custom windows.json")
        custom.write_text(json.dumps({"username": "", "password": ""}))
        custom.chmod(0o600)
        self.windows_password_file.unlink()
        result = self.run_shell(self.script, WINRM_CREDENTIALS_FILE=str(custom))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Session startup complete.", result.stdout)

    def test_concurrent_sessions_serialize_git_and_release_the_lock(self):
        real_git = shutil.which("git")
        self.env["UPDATE_GUARD"] = str(self.base / "updating")
        self.write_tool("git", "#!/usr/bin/env bash\n" + f"REAL_GIT={shlex.quote(real_git)}\n" + """
if [[ "${3:-}" == fetch ]]; then
  mkdir "$UPDATE_GUARD" || exit 70
  trap 'rmdir "$UPDATE_GUARD"' EXIT
  sleep 0.15
fi
"$REAL_GIT" "$@"
""")
        processes = [subprocess.Popen(["bash", str(self.script)], cwd=self.base, env=self.env,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                     for _ in range(2)]
        try:
            for process in processes:
                out, err = process.communicate(timeout=15)
                self.assertEqual(process.returncode, 0, out + err)
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                process.wait()
        self.assertEqual(self.forward_log.read_text().splitlines(), ["start", "status"] * 2)


class GrafanaStartTests(StartupFixture):
    def test_macos_busy_ports_stop_before_starting_any_forward(self):
        script = self.root / "scripts/grafana-mcp-forward.sh"
        shutil.copy2(SCRIPTS / "grafana-mcp-forward.sh", script)
        self.write_tool("uname", "#!/bin/sh\necho Darwin\n")
        self.write_tool("lsof", "#!/bin/sh\nprintf 'p123\\nn*:60007\\nn127.0.0.1:60008\\n'\n")
        calls = self.base / "kubectl-calls"
        self.env["KUBECTL_BIN"] = str(self.write_tool(
            "kubectl", f"#!/bin/sh\ntouch {shlex.quote(str(calls))}\n"))
        result = self.run_shell(script, "run")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("already listening", result.stderr)
        self.assertFalse(calls.exists())
        self.assertFalse((self.root / ".tools/grafana-mcp-forward/pid").exists())

    def test_concurrent_starts_launch_one_supervisor_without_inheriting_start_lock(self):
        script = self.root / "scripts/grafana-mcp-forward.sh"
        shutil.copy2(SCRIPTS / "grafana-mcp-forward.sh", script)
        state = self.root / ".tools/grafana-mcp-forward"
        launches = self.base / "launches"
        self.env.update(TEST_STATE=str(state), LAUNCHES=str(launches))
        # Model the detached supervisor with a delayed PID publication, exposing
        # the race between the initial alive check and actual process startup.
        self.write_tool("setsid", f"#!{sys.executable}\n" + """
import os, pathlib, signal, time
state = pathlib.Path(os.environ['TEST_STATE'])
with open(os.environ['LAUNCHES'], 'a') as log:
    log.write(str(os.getpid()) + '\\n')
def stop(*_):
    (state / 'pid').unlink(missing_ok=True)
    (state / 'ready').unlink(missing_ok=True)
    raise SystemExit(0)
signal.signal(signal.SIGTERM, stop)
time.sleep(0.3)
(state / 'pid').write_text(str(os.getpid()))
(state / 'ready').touch()
while True:
    time.sleep(0.1)
""")
        python = self.root / ".venv/bin/python"
        python.unlink()
        shutil.copy2(self.bin / "setsid", python)
        for name in ("kubectl", "ss", "lsof", "tail", "curl"):
            self.write_tool(name, "#!/bin/sh\nexit 0\n")
        processes = []
        try:
            processes = [subprocess.Popen(["bash", str(script), "start"], cwd=self.base,
                                          env=self.env, stdout=subprocess.PIPE,
                                          stderr=subprocess.PIPE, text=True) for _ in range(2)]
            for process in processes:
                out, err = process.communicate(timeout=10)
                self.assertEqual(process.returncode, 0, out + err)
            self.assertEqual(len(launches.read_text().splitlines()), 1)
            result = self.run_shell(script, "status")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("grafana_mcp_ops_dev: reachable", result.stdout)
            self.assertIn("grafana_mcp_ops_prod: reachable", result.stdout)
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                process.wait()
            if launches.exists():
                for pid in launches.read_text().splitlines():
                    try:
                        os.kill(int(pid), 15)
                    except ProcessLookupError:
                        pass
                deadline = time.monotonic() + 3
                while (state / "pid").exists() and time.monotonic() < deadline:
                    time.sleep(0.05)

    def test_supervisor_starts_reuses_and_stops_both_forwards_on_each_platform(self):
        script = self.root / "scripts/grafana-mcp-forward.sh"
        reservations = [socket.socket(), socket.socket()]
        try:
            for sock in reservations:
                sock.bind(("127.0.0.1", 0))
            ports = [sock.getsockname()[1] for sock in reservations]
        finally:
            for sock in reservations:
                sock.close()
        script.write_text((SCRIPTS / "grafana-mcp-forward.sh").read_text()
                          .replace("DEV_PORT=60007", f"DEV_PORT={ports[0]}")
                          .replace("PROD_PORT=60008", f"PROD_PORT={ports[1]}"))
        self.env["KUBECTL_LOG"] = str(self.base / "kubectl.log")
        self.env["KUBECTL_BIN"] = str(self.write_tool("kubectl", f"#!{sys.executable}\n" + """
import http.server, json, os, sys
with open(os.environ['KUBECTL_LOG'], 'a') as log:
    log.write(json.dumps(sys.argv[1:]) + '\\n')
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(404)
        self.send_header('Content-Length', '0')
        self.end_headers()
    def log_message(self, *_):
        pass
http.server.HTTPServer(('127.0.0.1', int(sys.argv[-1].split(':')[0])), Handler).serve_forever()
"""))
        # Use the actual flock implementation when it is installed.
        installed_flock = shutil.which("flock")
        if installed_flock:
            (self.bin / "flock").unlink()
            (self.bin / "flock").symlink_to(installed_flock)
        # Linux-only tools are stand-ins when exercising that branch on macOS.
        if not shutil.which("setsid"):
            self.write_tool("setsid", '#!/bin/sh\nexec "$@"\n')
        if not shutil.which("ss"):
            self.write_tool("ss", "#!/bin/sh\nexit 0\n")
        if not shutil.which("lsof"):
            self.write_tool("lsof", "#!/bin/sh\nexit 1\n")
        for platform in ("Darwin", "Linux"):
            with self.subTest(platform=platform):
                self.write_tool("uname", f"#!/bin/sh\necho {platform}\n")
                try:
                    result = self.run_shell(script, "start")
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertIn("Both tunnels are reachable", result.stdout)
                    if platform == "Darwin":
                        supervisor = int((self.root / ".tools/grafana-mcp-forward/pid").read_text())
                        self.assertEqual(os.getpgid(supervisor), supervisor)
                    before = Path(self.env["KUBECTL_LOG"]).read_text()
                    result = self.run_shell(script, "start")
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("Already running", result.stdout)
                    self.assertEqual(Path(self.env["KUBECTL_LOG"]).read_text(), before)
                    result = self.run_shell(script, "status")
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("grafana_mcp_ops_dev: reachable", result.stdout)
                    self.assertIn("grafana_mcp_ops_prod: reachable", result.stdout)
                finally:
                    result = self.run_shell(script, "stop")
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertFalse((self.root / ".tools/grafana-mcp-forward/pid").exists())
                for port in ports:
                    with socket.socket() as sock:
                        self.assertNotEqual(sock.connect_ex(("127.0.0.1", port)), 0)


if __name__ == "__main__":
    unittest.main()
