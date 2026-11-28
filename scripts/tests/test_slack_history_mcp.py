"""Test the Slack history MCP helpers with a fake client; never contacts Slack."""

import asyncio
import importlib.util
import os
from pathlib import Path
import unittest
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[2] / "mcp-servers/slack-history-mcp/slack-history-mcp.py"
spec = importlib.util.spec_from_file_location("slack_history_mcp", SCRIPT)
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


class FakeClient:
    def __init__(self):
        self.calls = []

    async def conversations_replies(self, channel, ts, limit, cursor):
        self.calls.append(ts)
        reply = {"ts": "1700000002.000000", "thread_ts": "1700000001.000000", "text": "r", "bot_id": "x"}
        if ts == "1700000001.000000":
            return {"messages": [{"ts": ts, "text": "root"}, reply]}
        return {"messages": [reply]}


class SlackHistoryTests(unittest.TestCase):
    def test_permalink_parsing(self):
        url = "https://w.slack.com/archives/C123ABC/p1700000002000000?thread_ts=1700000001.000000&cid=C123ABC"
        self.assertEqual(
            server.parse_permalink(url), ("C123ABC", "1700000002.000000", "1700000001.000000")
        )
        with self.assertRaises(ValueError):
            server.parse_permalink("https://example.com/")

    def test_get_thread_trims_fields(self):
        fake = FakeClient()
        url = "https://w.slack.com/archives/C123ABC/p1700000002000000?thread_ts=1700000001.000000"
        with mock.patch.object(server, "client", return_value=fake):
            result = asyncio.run(server.get_thread(url))
        self.assertEqual([m["text"] for m in result["messages"]], ["root", "r"])
        self.assertNotIn("bot_id", result["messages"][1])

    def test_channel_allowlist(self):
        with mock.patch.dict(os.environ, {"SLACK_HISTORY_CHANNELS": "C111"}):
            server.check_channel("C111")
            with self.assertRaises(ValueError):
                server.check_channel("C222")


if __name__ == "__main__":
    unittest.main()
