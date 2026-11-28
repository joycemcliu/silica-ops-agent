"""Test MCP config rendering from the shared registry."""

import importlib.util
import io
from contextlib import redirect_stdout
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import tomllib
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("render_mcp_config", SCRIPTS / "render-mcp-config.py")
render = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render)


def servers(env):
    registry = tomllib.loads((SCRIPTS.parent / "config" / "mcp-servers.toml").read_text())
    return {n: render.resolve(s, env) for n, s in registry["servers"].items()}


class RenderTests(unittest.TestCase):
    def test_codex_output_is_valid_toml_with_all_servers(self):
        resolved = servers({"SLACK_HISTORY_CHANNELS": "C1", "RCA_GOOGLE_CREDENTIALS_FILE": "credentials/rca.json"})
        parsed = tomllib.loads(render.render_codex(resolved))["mcp_servers"]
        self.assertEqual(
            set(parsed), {"grafana_mcp_ops_dev", "grafana_mcp_ops_prod", "slack_history", "google_drive_rca"}
        )
        self.assertEqual(parsed["slack_history"]["env"]["SLACK_HISTORY_CHANNELS"], "C1")
        self.assertEqual(parsed["grafana_mcp_ops_dev"]["http_headers"]["Host"], "localhost:60007")
        self.assertEqual(parsed["slack_history"]["default_tools_approval_mode"], "auto")
        self.assertNotIn("tools", parsed["slack_history"])
        self.assertEqual(parsed["google_drive_rca"]["default_tools_approval_mode"], "prompt")
        self.assertEqual(parsed["google_drive_rca"]["env"]["RCA_GOOGLE_CREDENTIALS_FILE"], "credentials/rca.json")
        for name, folder in (("slack_history", "slack-history-mcp"), ("google_drive_rca", "google-drive-mcp")):
            script = SCRIPTS.parent / "mcp-servers" / folder / f"{folder}.py"
            self.assertEqual(parsed[name]["args"], [str(script)])
            self.assertTrue(script.is_file())

    def test_unset_env_placeholder_is_omitted(self):
        slack = servers({})["slack_history"]
        self.assertNotIn("SLACK_HISTORY_CHANNELS", slack["env"])
        self.assertIn("SLACK_HISTORY_TOKEN_FILE", slack["env"])

    def test_renderer_loads_separate_mcp_env_files(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            directory = root / "mcp-servers" / "env"
            directory.mkdir(parents=True)
            (directory / ".env.gdrive").write_text(
                "RCA_GOOGLE_CREDENTIALS_FILE='credentials/rca key.json'\nUNUSED=not-rendered\n"
            )
            (directory / ".env.slack").write_text("SLACK_HISTORY_CHANNELS=C1,C2\n")
            (directory / ".env.slack.example").write_text("SLACK_HISTORY_CHANNELS=C3\n")
            output = io.StringIO()
            registry = SCRIPTS.parent / "config" / "mcp-servers.toml"
            with mock.patch.object(render, "REPO", root), mock.patch.dict(os.environ, {}, clear=True), redirect_stdout(output):
                render.main(["codex", "--registry", str(registry)])
            raw = output.getvalue()
            parsed = tomllib.loads(raw)["mcp_servers"]
            self.assertEqual(parsed["slack_history"]["env"]["SLACK_HISTORY_CHANNELS"], "C1,C2")
            self.assertEqual(parsed["google_drive_rca"]["env"]["RCA_GOOGLE_CREDENTIALS_FILE"], "credentials/rca key.json")
            self.assertNotIn("not-rendered", raw)
            with mock.patch.dict(os.environ, {"SLACK_HISTORY_CHANNELS": "C4"}, clear=True):
                self.assertEqual(render.mcp_environment(directory)["SLACK_HISTORY_CHANNELS"], "C4")

    def test_bearer_token_file_renders_codex_helper_and_hermes_env_header(self):
        server = {"type": "http", "url": "http://h:1/mcp", "bearer_token_file": "{home}/tok", "bearer_token_env": "TOK"}
        resolved = {"s": render.resolve(server, {})}
        codex = tomllib.loads(render.render_codex(resolved))["mcp_servers"]["s"]
        self.assertTrue(codex["http_headers_helper"].endswith(f"mcp-bearer-header.sh {Path.home()}/tok"))
        self.assertNotIn("bearer_token_env_var", codex)
        self.assertIn("Bearer ${TOK}", render.render_hermes(resolved))

    def test_remote_rca_uses_bearer_auth_and_prompts_for_approval(self):
        registry = tomllib.loads((SCRIPTS.parent / "config/mcp-servers.remote.toml").read_text())
        resolved = {name: render.resolve(server, {}) for name, server in registry["servers"].items()}
        codex = tomllib.loads(render.render_codex(resolved))["mcp_servers"]
        self.assertEqual(codex["slack_history"]["default_tools_approval_mode"], "auto")
        self.assertNotIn("tools", codex["slack_history"])
        rca = codex["google_drive_rca"]
        self.assertEqual(rca["url"], "http://127.0.0.1:60011/mcp")
        self.assertEqual(rca["default_tools_approval_mode"], "prompt")
        self.assertTrue(rca["http_headers_helper"].endswith(
            f"mcp-bearer-header.sh {Path.home()}/.local/secrets/google-drive-rca-mcp-http-token"
        ))
        self.assertIn("Bearer ${GOOGLE_DRIVE_RCA_MCP_TOKEN}", render.render_hermes(resolved))

    def test_hermes_output_names_match_codex(self):
        text = render.render_hermes(servers({"SLACK_HISTORY_CHANNELS": "C1"}))
        for name in ("grafana_mcp_ops_dev", "grafana_mcp_ops_prod", "slack_history", "google_drive_rca"):
            self.assertIn(f"  {name}:", text)


if __name__ == "__main__":
    unittest.main()
