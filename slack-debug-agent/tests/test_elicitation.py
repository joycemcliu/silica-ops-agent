import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from test_agent import Slack, config, event, until

from slack_debug.app import Manager, Session
from slack_debug.codex import Codex

METHOD = "mcpServer/elicitation/request"


class ElicitationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = Slack()
        self.manager = Manager(config(), self.bot, Slack())
        self.session = Session(self.manager, "D123", "thread", "", "")
        self.manager.sessions[("D123", "thread")] = self.session
        self.params = {
            "serverName": "grafana", "threadId": "codex-thread", "mode": "form",
            "message": "Choose a store",
            "requestedSchema": {"type": "object", "properties": {
                "store": {"type": "string", "enum": ["uswindow", "other"]},
                "confirmed": {"type": "boolean"},
            }, "required": ["store", "confirmed"], "additionalProperties": False},
        }
        self.tasks = []

    async def asyncTearDown(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        await self.session.activity.close()

    async def start_request(self, **changes):
        task = asyncio.create_task(self.session.request(METHOD, {**self.params, **changes}))
        self.tasks.append(task)
        await until(lambda: self.session.question is not None or task.done())
        return task

    async def reply(self, text, **changes):
        await self.manager.message(event(text, thread_ts="thread", **changes), str((text, changes)))

    async def test_form_requires_authorized_schema_valid_reply(self):
        task = await self.start_request()
        question = self.session.question
        await self.reply('{"store":"uswindow","confirmed":true}', user="U999")
        self.assertFalse(question.done())
        await self.reply('{"store":"uswindow","confirmed":"true"}')
        await until(lambda: self.session.question is not question)
        self.assertFalse(task.done())
        await self.reply('{"store":"uswindow","confirmed":true}')
        self.assertEqual(await task, {"action": "accept", "content": {
            "store": "uswindow", "confirmed": True,
        }})
        self.assertIsNone(self.session.question)
        self.assertTrue(self.session.inputs.empty())

    async def test_decline_cancel_and_empty_forms_for_protocol_aliases(self):
        for mode in ("form", "openai/form", "openaiForm"):
            for reply, expected in (("decline", {"action": "decline"}),
                                    ("cancel", {"action": "cancel"}),
                                    ("{}", {"action": "accept", "content": {}})):
                task = await self.start_request(mode=mode, requestedSchema={
                    "type": "object", "properties": {},
                })
                # Give repeated replies unique event identities.
                await self.manager.message(event(reply, thread_ts="thread"), f"{mode}:{reply}")
                self.assertEqual(await task, expected)

    async def test_url_requires_explicit_accept_and_never_fetches(self):
        task = await self.start_request(mode="url", url="https://auth.example.test/connect",
                                        elicitationId="elicitation-1")
        self.assertIn("https://auth.example.test/connect", self.bot.posts[-1]["text"])
        await self.reply("accept")
        self.assertEqual(await task, {"action": "accept"})

    async def test_invalid_modes_urls_and_secret_forms_decline_without_crash(self):
        for changes in (
            {"mode": "new-mode"}, {"mode": "url", "url": "file:///etc/passwd"},
            {"mode": "url", "url": "https://name:password@example.test"},
            {"requestedSchema": {"type": "object", "properties": {
                "password": {"type": "string"}}}},
            {"requestedSchema": {"type": "object", "$ref": "https://example.test/schema"}},
            {"requestedSchema": {"type": "object", "properties": None}},
        ):
            task = await self.start_request(**changes)
            self.assertEqual(await task, {"action": "decline"})
            self.assertIsNone(self.session.question)

    async def test_timeout_returns_cancel(self):
        with patch("slack_debug.elicitation.APPROVAL_SECONDS", 0.01):
            task = await self.start_request()
            self.assertEqual(await task, {"action": "cancel"})
        self.assertIsNone(self.session.question)
        self.assertIn("expired", self.bot.posts[-1]["text"])

    async def test_codex_answer_returns_result_without_session_failure(self):
        client = Codex(config(), self.session.request)
        client.send = AsyncMock()
        task = asyncio.create_task(client._answer({
            "id": "elicitation-request-1", "method": METHOD, "params": self.params,
        }))
        self.tasks.append(task)
        await until(lambda: self.session.question is not None)
        await self.reply("decline")
        await task
        client.send.assert_awaited_once_with({"id": "elicitation-request-1", "result": {
            "action": "decline",
        }})
        self.assertTrue(client.events.empty())
