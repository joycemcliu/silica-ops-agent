import base64
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from access_common import AccessError, redact
from ssh_policy import command_arguments


class CommandPolicyTests(unittest.TestCase):
    def test_allowed_diagnostics(self):
        commands = [
            "journalctl -u demo.service -n 50 --since '1 hour ago'",
            "journalctl --output=json --priority=3", "systemctl status demo.service",
            "ps aux", "df -h", "free -m", "ss -tulnp", "uptime", "dmesg --ctime",
            "ls -lh /var/log", "cat /var/log/demo.log /proc/meminfo",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertTrue(command_arguments(command))

    def test_shell_and_write_bypasses_are_rejected(self):
        commands = [
            "sh", "/bin/uptime", "uptime; id", "uptime | cat", "uptime &", "uptime > /tmp/out",
            "cat < /var/log/demo.log", "uptime $HOME", "uptime `id`", "uptime (id)",
            "uptime\nid", "uptime\rid", "uptime\x00", "uptime\t", "$(uptime)",
            "journalctl --vacuum-time=1s", "journalctl --rotate", "journalctl --flush",
            "journalctl --file=/etc/shadow", "journalctl --setup-keys", "journalctl -u",
            "journalctl -u --vacuum-size=1", "systemctl restart demo", "systemctl status --host=other",
            "ps auxe", "ps -o environ", "ss -K", "dmesg -c", "dmesg --clear",
            "cat /etc/shadow", "cat /proc/self/environ", "cat /var/log/../secrets",
            "cat /var/log//demo.log", "ls -R /", "cat /var/log/demo*", "ls", "cat",
        ]
        for command in commands:
            with self.subTest(command=command), self.assertRaises(AccessError):
                command_arguments(command)

    def test_redaction_handles_structured_and_truncated_secrets(self):
        secret_text = (
            'password=hunter-fixture token:abc-fixture {"api_key":"json-fixture"}\n'
            'Authorization: Bearer bearer-fixture\npostgresql://user:pass@db/test\n'
            + "-----BEGIN " + "RSA PRIVATE KEY-----\nkey-fixture\n"
        )
        cleaned = redact(secret_text)
        for sensitive in ["hunter-fixture", "abc-fixture", "json-fixture", "bearer-fixture", "user:pass", "key-fixture"]:
            self.assertNotIn(sensitive, cleaned)
        self.assertIn("[REDACTED", cleaned)


class SSHIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name)
        binaries = self.home / "bin"
        binaries.mkdir()
        fake = binaries / "fake-cli"
        fake.write_bytes((ROOT / "tests/fakes/native_cli.py").read_bytes())
        fake.chmod(0o755)
        for binary in ["kubectl", "sshpass", "ssh-keyscan", "ssh-keygen"]:
            (binaries / binary).symlink_to(fake)
        self.fingerprint = "SHA256:" + base64.b64encode(hashlib.sha256(b"synthetic server").digest()).decode().rstrip("=")
        self.state = {"fingerprint": self.fingerprint}
        self.write_state()
        self.config = self.home / "envs.yaml"
        self.config.write_text((ROOT / "envs.yaml").read_text().replace("SHA256:" + "A" * 43, self.fingerprint))
        self.environment = {
            **os.environ, "PATH": str(binaries) + os.pathsep + os.environ["PATH"],
            "HOME": str(self.home), "OPS_ENV": "test", "OPS_ENVS_FILE": str(self.config),
            "OPS_SSH_USER": "ops_readonly", "OPS_SSH_PASSWORD": "synthetic-session-password",
            "OPS_CONNECT_TIMEOUT_SECONDS": "1", "OPS_SSH_TIMEOUT_SECONDS": "1",
            "OPS_OUTPUT_LIMIT_BYTES": "1024", "OTHER_ENV_TOKEN": "other-environment-fixture",
        }

    def write_state(self):
        (self.home / "fake-state.json").write_text(json.dumps(self.state))

    def invoke(self, command="uptime"):
        self.write_state()
        result = subprocess.run(
            ["bash", str(ROOT / "scripts/env-ssh.sh"), command], env=self.environment,
            capture_output=True, text=True, timeout=10,
        )
        self.assert_forward_stopped()
        return result

    def assert_forward_stopped(self):
        pid_file = self.home / "forward.pid"
        if pid_file.exists():
            with self.assertRaises(ProcessLookupError):
                os.kill(int(pid_file.read_text()), 0)

    def test_allowed_journal_and_native_security_options(self):
        result = self.invoke("journalctl -u demo.service -n 50")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("seeded service failure", result.stdout)
        calls = [json.loads(line) for line in (self.home / "calls.jsonl").read_text().splitlines()]
        forward = next(call for call in calls if call["binary"] == "kubectl")
        self.assertIn("--address=127.0.0.1", forward["args"])
        self.assertIn(":22", forward["args"])
        ssh = next(call for call in calls if call["binary"] == "sshpass")
        self.assertIn("StrictHostKeyChecking=yes", ssh["args"])
        self.assertIn("journalctl --no-pager -u demo.service -n 50", ssh["args"])
        self.assertNotIn(self.environment["OPS_SSH_PASSWORD"], json.dumps(calls))
        for call in calls:
            self.assertNotIn("OTHER_ENV_TOKEN", call["environment_keys"])
            self.assertNotIn("OPS_SSH_PASSWORD", call["environment_keys"])
        self.assertIn("SSHPASS", ssh["environment_keys"])

    def test_rejection_happens_before_port_forward(self):
        result = self.invoke("journalctl --vacuum-size=1")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse((self.home / "forward.pid").exists())

    def test_stdout_stderr_and_actual_password_are_redacted(self):
        self.state.update(stdout="password=stdout-fixture\ntoken=token-fixture\n", stderr="api_key=stderr-fixture\n", echo_password=True)
        result = self.invoke()
        for sensitive in ["stdout-fixture", "token-fixture", "stderr-fixture", self.environment["OPS_SSH_PASSWORD"]]:
            self.assertNotIn(sensitive, result.stdout + result.stderr)
        self.assertIn("[REDACTED]", result.stdout)

    def test_known_secret_crossing_output_boundary_is_redacted(self):
        self.state["stdout"] = "x" * 1010 + self.environment["OPS_SSH_PASSWORD"] + "\n"
        result = self.invoke()
        self.assertNotIn("synthetic-session", result.stdout)
        self.assertLessEqual(len(result.stdout.encode()), 1024)

    def test_invalid_limits_and_missing_credentials_do_not_connect(self):
        for key, value in [("OPS_SSH_TIMEOUT_SECONDS", "0"), ("OPS_OUTPUT_LIMIT_BYTES", "999999999"), ("OPS_SSH_PASSWORD", "")]:
            previous = self.environment[key]
            self.environment[key] = value
            self.assertNotEqual(self.invoke().returncode, 0)
            self.assertFalse((self.home / "forward.pid").exists())
            self.environment[key] = previous

    def test_ssh_failure_always_cleans_up(self):
        self.state["ssh_status"] = 17
        self.assertEqual(self.invoke().returncode, 17)

    def test_ssh_timeout_always_cleans_up(self):
        self.state["ssh_hang"] = True
        self.assertEqual(self.invoke().returncode, 124)

    def test_output_is_bounded_and_tunnel_is_cleaned_up(self):
        self.state["ssh_flood"] = True
        result = self.invoke()
        self.assertEqual(result.returncode, 125)
        self.assertLessEqual(len(result.stdout.encode()), 1024)

    def test_forward_failure_and_readiness_timeout(self):
        for mode in ["forward_fail", "forward_hang"]:
            self.state = {"fingerprint": self.fingerprint, mode: True}
            self.assertNotEqual(self.invoke().returncode, 0)

    def test_untrusted_or_placeholder_host_keys_are_rejected(self):
        self.state["fingerprint"] = "SHA256:" + "B" * 43
        self.assertNotEqual(self.invoke().returncode, 0)
        self.config.write_text((ROOT / "envs.yaml").read_text())
        self.assertNotEqual(self.invoke().returncode, 0)

    def test_unknown_environment_does_not_connect(self):
        self.environment["OPS_ENV"] = "other"
        self.assertNotEqual(self.invoke().returncode, 0)
        self.assertFalse((self.home / "forward.pid").exists())

    def test_termination_signal_cleans_up_forward(self):
        self.state["ssh_hang"] = True
        self.write_state()
        process = subprocess.Popen(
            ["bash", str(ROOT / "scripts/env-ssh.sh"), "uptime"], env=self.environment,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.addCleanup(lambda: process.kill() if process.poll() is None else None)
        deadline = time.monotonic() + 5
        while not (self.home / "forward.pid").exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        self.assertTrue((self.home / "forward.pid").exists())
        process.send_signal(signal.SIGTERM)
        process.communicate(timeout=5)
        self.assertNotEqual(process.returncode, 0)
        self.assert_forward_stopped()


if __name__ == "__main__":
    unittest.main()
