import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from slack_debug.__main__ import main


class CliTests(unittest.TestCase):
    def test_env_file_overrides_inherited_values_without_interpolation(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / "service.env"
            env_file.write_text("SLACK_BOT_TOKEN=xoxb-literal${HOME}\n")

            def check_loaded(root, profile=None):
                self.assertEqual(os.environ["SLACK_BOT_TOKEN"], "xoxb-literal${HOME}")
                self.assertTrue((root / "slack-debug-agent/main.py").is_file())
                self.assertIsNone(profile)

            with (
                patch.dict(os.environ, {"SLACK_BOT_TOKEN": "old", "PYTHON_DOTENV_DISABLED": "0"}),
                patch("sys.argv", ["main.py", "--env-file", str(env_file), "--check"]),
                patch("slack_debug.__main__.Config.load", side_effect=check_loaded),
                patch("slack_debug.__main__.asyncio.run") as run,
                patch("sys.stdout", new_callable=io.StringIO) as output,
            ):
                main()
                run.assert_not_called()
                self.assertIn("Local configuration valid", output.getvalue())
                self.assertNotIn("xoxb-", output.getvalue())

    def test_missing_env_file_stops_before_config_or_slack(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.env"
            with (
                patch("sys.argv", ["main.py", "--env-file", str(missing), "--check"]),
                patch("slack_debug.__main__.Config.load") as load,
                patch("sys.stderr", new_callable=io.StringIO) as output,
                self.assertRaises(SystemExit) as error,
            ):
                main()
            self.assertEqual(error.exception.code, 1)
            self.assertIn("Environment file not found", output.getvalue())
            load.assert_not_called()

    def test_named_profile_is_passed_to_configuration(self):
        with (
            patch("sys.argv", ["main.py", "--profile", "diagnose", "--check"]),
            patch("slack_debug.__main__.Config.load") as load,
            patch("sys.stdout", new_callable=io.StringIO),
        ):
            main()
            self.assertEqual(load.call_args.kwargs, {"profile": "diagnose"})


if __name__ == "__main__":
    unittest.main()
