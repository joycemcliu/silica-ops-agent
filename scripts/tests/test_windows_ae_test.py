"""Local-only argument/transport checks; never connect to Windows."""

import argparse
import base64
from contextlib import redirect_stderr
import importlib.util
import io
import json
from pathlib import Path
import re
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "windows_ae_test", Path(__file__).resolve().parents[1] / "windows-ae-test.py"
)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class RunnerTests(unittest.TestCase):
    def arguments(self, *extra):
        return [
            "--host", "10.1.0.50", "--worker-pid", "123", "--worker-exe", r"C:\renderer\worker.exe",
            "--aerender", r"C:\Adobe\aerender.exe", "--project", r"C:\render input\project.aepx",
            "--comp", "Scene 'one'; $(invalid)", "--working-directory", r"C:\renderer",
            "--output-root", r"C:\diagnostics", "--ffprobe", r"C:\tools\ffprobe.exe",
            "--ffmpeg", r"C:\tools\ffmpeg.exe", "--expected-frames", "100", *extra,
        ]

    def test_default_is_preflight_and_values_are_data_without_credentials(self):
        args = runner.parser().parse_args(self.arguments("--credentials", "/secret/not-to-send"))
        self.assertFalse(args.execute)
        command = runner.build_command(args)
        match = re.search(r"-RequestBase64 '([^']+)'$", command)
        request = json.loads(base64.b64decode(match.group(1)))
        self.assertEqual(request["comp"], "Scene 'one'; $(invalid)")
        self.assertEqual(request["project"], r"C:\render input\project.aepx")
        for field in ("host", "credentials", "https", "port"):
            self.assertNotIn(field, request)
        self.assertNotIn("/secret/not-to-send", command)
        source = base64.b64decode(request["runner_source"]).decode()
        self.assertEqual(source, (runner.SCRIPTS / "windows-ae-test.ps1").read_text())

    def test_invalid_requests_fail_before_loading_credentials(self):
        cases = (
            ("--port", "65536"), ("--timeout-seconds", "0"), ("--worker-pid", "0"),
            ("--project", r"C:\project.aep"), ("--project", "relative.aepx"),
            ("--output-root", r"\\server\share"), ("--output-name", r"..\existing.mp4"),
            ("--output-name", "*.png"), ("--memory", "5", "80"),
            ("--comp", "\n"), ("--aerender", 'C:\\bad"path\\aerender.exe'),
        )
        with patch.object(runner.winrm, "load_credentials") as credentials, redirect_stderr(io.StringIO()):
            for extra in cases:
                with self.subTest(extra=extra), self.assertRaises(SystemExit) as error:
                    runner.main(self.arguments(*extra))
                self.assertEqual(error.exception.code, 2)
            credentials.assert_not_called()

    def test_supported_paths(self):
        for value in (r"C:\a folder\file.exe", r"\\server\share\file.mov"):
            self.assertEqual(runner.windows_path(value), value)
        for value in ("/tmp/file", "C:relative", "\\relative", "C:\\line\nbreak"):
            with self.assertRaises(argparse.ArgumentTypeError):
                runner.windows_path(value)

    def test_credentials_errors_do_not_expose_details(self):
        with patch.object(runner.winrm, "load_credentials", side_effect=ValueError("secret-value")), redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(runner.main(self.arguments()), 2)
        self.assertNotIn("secret-value", errors.getvalue())

    def test_uses_existing_transport_and_propagates_failure(self):
        with patch.object(runner.winrm, "load_credentials", return_value=("account", "password")), patch.object(runner.winrm, "run_session", return_value=1) as session:
            self.assertEqual(runner.main(self.arguments("--execute", "--https", "--port", "5986")), 1)
        args = session.call_args.args[0]
        self.assertEqual(args.host, "10.1.0.50")
        self.assertTrue(args.https)
        self.assertEqual(args.port, 5986)
        self.assertIn("-RequestBase64", args.command)


if __name__ == "__main__":
    unittest.main()
