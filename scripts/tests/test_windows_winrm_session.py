"""Local checks only: never connect to Windows or open a tunnel."""

from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch


spec = importlib.util.spec_from_file_location(
    "windows_winrm_session", Path(__file__).resolve().parents[1] / "windows-winrm-session.py"
)
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)


class CredentialsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.root = self.home / ".local/secrets"
        self.root.mkdir(parents=True)
        self.path = self.root / "windows.json"
        self.path.write_text(json.dumps({"username": r"PC\user", "password": "test-secret"}))
        self.path.chmod(0o600)
        self.home_patch = patch.object(client.Path, "home", return_value=self.home)
        self.home_patch.start()
        self.addCleanup(self.home_patch.stop)

    def test_load_private_file(self):
        self.assertEqual(client.load_credentials(self.path), (r"PC\user", "test-secret"))

    def test_allow_empty_credentials(self):
        for username, password in (("", "test-secret"), (r"PC\user", ""), ("", "")):
            with self.subTest(username=username, empty_password=not password):
                self.path.write_text(json.dumps({"username": username, "password": password}))
                self.assertEqual(client.load_credentials(self.path), (username, password))

    def test_reject_group_or_other_permissions(self):
        for mode in (0o640, 0o604):
            self.path.chmod(mode)
            with self.assertRaisesRegex(ValueError, "owner-only"):
                client.load_credentials(self.path)

    def test_reject_different_owner(self):
        with patch.object(client.os, "getuid", return_value=self.path.stat().st_uid + 1):
            with self.assertRaisesRegex(ValueError, "belong to this user"):
                client.load_credentials(self.path)

    def test_reject_outside_path_and_symlink_escape(self):
        outside = self.home / "outside.json"
        outside.write_text(self.path.read_text())
        outside.chmod(0o600)
        link = self.root / "link.json"
        link.symlink_to(outside)
        for candidate in (outside, link):
            with self.assertRaisesRegex(ValueError, "inside"):
                client.load_credentials(candidate)

    def test_malformed_and_missing_credentials_do_not_expose_content(self):
        for content in (
            '{"password":"test-secret"', '{}', '[]',
            '{"username":123,"password":"test-secret"}',
            '{"username":"","password":null}',
            '{"username":null,"password":""}',
            '{"username":""}', '{"password":""}',
        ):
            self.path.write_text(content)
            with self.assertRaises(ValueError) as caught:
                client.load_credentials(self.path)
            self.assertNotIn("test-secret", str(caught.exception))


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.wsman = MagicMock()
        self.pool = MagicMock()
        self.powershell = MagicMock()
        ps = self.powershell.return_value
        ps.invoke.return_value = ["Windows output\n"]
        ps.streams.error = []
        ps.had_errors = False
        self.args = SimpleNamespace(host="10.26.1.50", https=False, port=None, command="hostname")

    def run_session(self):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return client.run_session(self.args, "user", "test-secret", self.wsman, self.pool, self.powershell)

    def test_single_command_encrypted_direct_transport_and_cleanup(self):
        self.assertEqual(self.run_session(), 0)
        self.wsman.assert_called_once_with(
            "10.26.1.50", username="user", password="test-secret", ssl=False,
            port=5985, auth="ntlm", encryption="always", cert_validation=True, no_proxy=True,
        )
        self.powershell.return_value.add_script.assert_called_once_with("hostname", use_local_scope=False)
        self.pool.return_value.__exit__.assert_called_once()
        self.wsman.return_value.__exit__.assert_called_once()

    def test_interactive_commands_share_one_runspace(self):
        self.args.command = None
        with patch("builtins.input", side_effect=['$x = 42', '$x', 'exit']):
            self.assertEqual(self.run_session(), 0)
        self.pool.assert_called_once()
        self.assertEqual(self.powershell.call_count, 2)
        for call in self.powershell.call_args_list:
            self.assertEqual(call.args, (self.pool.return_value.__enter__.return_value,))
        self.assertEqual(self.powershell.return_value.add_script.call_args_list[1].kwargs, {"use_local_scope": False})

    def test_powershell_error_fails_single_command(self):
        self.powershell.return_value.had_errors = True
        self.powershell.return_value.streams.error = ["Access denied"]
        self.assertEqual(self.run_session(), 1)

    def test_https_default_and_explicit_port(self):
        self.args.https = True
        self.run_session()
        self.assertEqual(self.wsman.call_args.kwargs["port"], 5986)
        self.args.port = 12345
        self.run_session()
        self.assertEqual(self.wsman.call_args.kwargs["port"], 12345)


if __name__ == "__main__":
    unittest.main()
