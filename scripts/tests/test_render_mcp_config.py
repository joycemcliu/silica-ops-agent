"""Test MCP config rendering from the shared registry."""

import importlib.util
import os
from pathlib import Path
import tomllib
import unittest
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("render_mcp_config", SCRIPTS / "render-mcp-config.py")
render = importlib.util.module_from_spec(spec)
spec.loader.exec_module(render)


def servers(env):
    registry = tomllib.loads((SCRIPTS.parent / "config" / "mcp-servers.toml").read_text())
    with mock.patch.dict(os.environ, env, clear=False):
        return {n: render.resolve(s) for n, s in registry["servers"].items()}


class RenderTests(unittest.TestCase):
    def test_codex_output_is_valid_toml_with_all_servers(self):
        parsed = tomllib.loads(render.render_codex(servers({"SLACK_HISTORY_CHANNELS": "C1"})))["mcp_servers"]
        self.assertEqual(
            set(parsed), {"grafana_mcp_ops_dev", "grafana_mcp_ops_prod", "slack_history"}
        )
        self.assertEqual(parsed["slack_history"]["env"]["SLACK_HISTORY_CHANNELS"], "C1")
        self.assertEqual(parsed["grafana_mcp_ops_dev"]["http_headers"]["Host"], "localhost:60007")
        self.assertEqual(parsed["slack_history"]["tools"]["get_thread"]["approval_mode"], "approve")

    def test_unset_env_placeholder_is_omitted(self):
        env = dict(os.environ)
        env.pop("SLACK_HISTORY_CHANNELS", None)
        with mock.patch.dict(os.environ, env, clear=True):
            registry = tomllib.loads((SCRIPTS.parent / "config" / "mcp-servers.toml").read_text())
            slack = render.resolve(registry["servers"]["slack_history"])
        self.assertNotIn("SLACK_HISTORY_CHANNELS", slack["env"])
        self.assertIn("SLACK_HISTORY_TOKEN_FILE", slack["env"])

    def test_hermes_output_names_match_codex(self):
        text = render.render_hermes(servers({"SLACK_HISTORY_CHANNELS": "C1"}))
        for name in ("grafana_mcp_ops_dev", "grafana_mcp_ops_prod", "slack_history"):
            self.assertIn(f"  {name}:", text)


if __name__ == "__main__":
    unittest.main()
