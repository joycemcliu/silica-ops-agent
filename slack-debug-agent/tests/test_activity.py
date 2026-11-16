import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from slack_sdk.errors import SlackApiError
from test_agent import URL, FakeCodex, Slack, config, event, until

from slack_debug.app import Manager, Session


class ActivityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = Slack()
        self.manager = Manager(config(), self.bot, Slack(), FakeCodex)
        self.session = Session(self.manager, "D123", "thread", URL, "")
        self.activity = self.session.activity
        self.activity.INTERVAL = 0.03

    async def asyncTearDown(self):
        await self.activity.close()
        await self.manager.close()

    async def feed(self, **item):
        await self.activity.feed("item/completed", {"item": item})

    async def test_rendering_excludes_outputs_and_final_answers(self):
        render = self.activity.line_for
        self.assertEqual(render({
            "type": "commandExecution", "command": "cat x; rg y; ls docs",
            "commandActions": [{"type": "read", "name": "x"},
                               {"type": "search", "query": "y"},
                               {"type": "listFiles", "path": "docs"}],
        }), "Explored: Read x, Search y, List docs")
        self.assertEqual(render({
            "type": "commandExecution", "command": "/bin/zsh -lc 'exit 7'",
            "aggregatedOutput": "secret output", "exitCode": 7,
            "commandActions": [{"type": "read", "name": "x"}, {"type": "unknown"}],
        }), "Ran exit 7  (exit 7)")
        self.assertEqual(render({"type": "fileChange", "changes": [
            {"path": "a.py", "diff": "secret diff"}]}), "Edited a.py")
        self.assertEqual(render({"type": "mcpToolCall", "server": "s", "tool": "t",
                                 "result": "secret result"}), "Tool s.t")
        self.assertEqual(render({"type": "agentMessage", "phase": "commentary",
                                 "text": "checking"}), "• checking")
        for item in ({"type": "reasoning", "text": "hidden"},
                     {"type": "agentMessage", "phase": "final_answer", "text": "done"},
                     {"type": "agentMessage", "text": "legacy final"}):
            self.assertIsNone(render(item))

    async def test_throttle_delivers_trailing_lines_and_bounds_memory(self):
        await self.feed(type="commandExecution", command="first")
        await until(lambda: len(self.bot.posts) == 1)
        for i in range(50):
            await self.feed(type="commandExecution", command=f"{i}:" + "x" * 300)
        self.assertFalse(self.bot.updates)
        self.assertLessEqual(len(self.activity.text), 2800)
        await until(lambda: len(self.bot.updates) == 1)
        self.assertIn("49:", self.bot.updates[0]["text"])
        self.assertEqual(self.bot.updates[0]["ts"], "1")
        self.assertEqual(self.bot.updates[0]["blocks"][0]["text"]["type"], "plain_text")

    async def test_rotate_flushes_then_posts_a_fresh_message(self):
        await self.feed(type="commandExecution", command="before")
        await self.activity.rotate()
        await self.manager.post(self.session, "approval or answer")
        await self.feed(type="commandExecution", command="after")
        await self.activity.rotate()
        self.assertEqual([p["text"] for p in self.bot.posts],
                         ["Ran before", "approval or answer", "Ran after"])

    async def test_disabled_and_dm_guard(self):
        self.activity.mode = "off"
        await self.feed(type="commandExecution", command="hidden")
        await self.activity.rotate()
        self.assertFalse(self.bot.posts)
        self.assertIsNone(self.activity.task)
        self.session.channel = "C123"
        with self.assertRaisesRegex(ValueError, "private DMs"):
            await self.manager.update(self.session, "1", "hidden")
        self.assertFalse(self.bot.updates)

    async def test_slack_failures_do_not_escape_or_spin(self):
        for error in (SlackApiError("limited", {"error": "ratelimited"}), OSError("offline")):
            with patch.object(self.manager, "post", AsyncMock(side_effect=error)) as post:
                await self.feed(type="commandExecution", command="pwd")
                await self.activity.rotate()
                self.assertEqual(post.await_count, 1)
                self.assertFalse(self.activity.dirty)

    async def test_protocol_callback_does_not_wait_for_slack(self):
        entered, release = asyncio.Event(), asyncio.Event()

        async def slow_post(*args, **kwargs):
            entered.set()
            await release.wait()
            return {"ts": "1"}

        with patch.object(self.manager, "post", slow_post):
            await self.feed(type="commandExecution", command="first")
            await entered.wait()
            await asyncio.wait_for(self.feed(type="commandExecution", command="second"), 0.1)
            release.set()
            await self.activity.rotate()
        self.assertFalse(self.activity.dirty)

    async def test_activity_lines_are_separate_sections_on_post_and_update(self):
        await self.feed(type="commandExecution", command="cat config.env AGENTS.md")
        await self.feed(type="commandExecution", command="cat docs/diagnose_toolkit.md")
        await until(lambda: len(self.bot.posts) == 1)
        initial = self.bot.posts[0]
        self.assertEqual([b["text"]["text"] for b in initial["blocks"]], [
            "Ran cat config.env AGENTS.md", "Ran cat docs/diagnose_toolkit.md",
        ])
        await self.feed(type="commandExecution", command="git status --short --branch")
        await until(lambda: len(self.bot.updates) == 1)
        update = self.bot.updates[0]
        self.assertEqual(update["blocks"][:2], initial["blocks"])
        self.assertEqual(update["blocks"][2]["text"]["text"],
                         "Ran git status --short --branch")
        self.assertEqual(update["ts"], "1")
        self.assertIn("\nRan ", update["text"])

    async def test_many_short_lines_keep_activity_block_count_bounded(self):
        await self.manager.post(self.session, "\n".join(f"Ran {i}" for i in range(100)),
                                activity=True)
        blocks = self.bot.posts[-1]["blocks"]
        self.assertEqual(len(blocks), 20)
        self.assertEqual(blocks[0]["text"]["text"], "Earlier activity omitted…")
        self.assertEqual(blocks[-1]["text"]["text"], "Ran 99")

    async def test_session_rotates_before_approval_and_final_answer(self):
        class Reporting(FakeCodex):
            async def turn(inner, text):
                await inner.on_notification("item/completed", {"item": {
                    "type": "commandExecution", "command": "before approval"}})
                await inner.handler("item/commandExecution/requestApproval", {
                    "command": "pwd", "cwd": "/tmp"})
                await inner.on_notification("item/completed", {"item": {
                    "type": "commandExecution", "command": "after approval"}})
                return "final answer"

        async def approve(session, params):
            await self.manager.post(session, "approval")
            return "decline"

        self.manager.codex_factory = Reporting
        with patch.object(self.manager, "approve", approve):
            await self.manager.message(event(), "activity-session")
            await until(lambda: self.bot.posts and self.bot.posts[-1]["text"] == "final answer")
        self.assertEqual([p["text"] for p in self.bot.posts][1:],
                         ["Ran before approval", "approval", "Ran after approval", "final answer"])
