"""Run explicitly against the local Postman simulation, never against Slack."""

import asyncio
import os
import unittest

import aiohttp
from slack_sdk.web.async_client import AsyncWebClient
from test_agent import URL, FakeCodex, config, event, until

from slack_debug.app import Manager, Session, read_issue


@unittest.skipUnless(
    os.environ.get("SLACK_DEBUG_SIM_URL"), "Local Postman simulation not requested"
)
class SlackWireTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.base = os.environ["SLACK_DEBUG_SIM_URL"].rstrip("/")
        if not self.base.startswith("http://127.0.0.1:"):
            raise ValueError("Wire tests require a loopback mock URL")
        self.http = aiohttp.ClientSession()
        async with self.http.post(self.base + "/reset") as response:
            self.assertEqual(response.status, 200)
        kwargs = {
            "base_url": self.base + "/api/",
            "session": self.http,
            "timeout": 2,
            "retry_handlers": [],
        }
        self.bot = AsyncWebClient(token="xoxb-wire-test", **kwargs)
        self.user = AsyncWebClient(token="xoxp-wire-test", **kwargs)
        FakeCodex.instances.clear()
        self.manager = Manager(config(), self.bot, self.user, FakeCodex)

    async def asyncTearDown(self):
        await self.manager.close()
        await self.http.close()

    async def records(self):
        async with self.http.get(self.base + "/records") as response:
            return (await response.json())["posts"]

    async def test_reply_root_and_dm_report_over_real_http(self):
        root, messages = await read_issue(
            self.user, config(), URL.replace("000001", "000002"), "1794800000.000002"
        )
        self.assertEqual(root, "1794800000.000001")
        self.assertEqual(messages[-1]["text"], "reply evidence")
        await self.manager.message(event(), "wire-start")
        await until(lambda: FakeCodex.instances and len(FakeCodex.instances[0].texts) == 1)
        async with asyncio.timeout(2):
            while len(await self.records()) < 2:
                await asyncio.sleep(0.01)
        posts = await self.records()
        self.assertTrue(
            all(p["channel"] == "D123" and p["thread_ts"] == event()["ts"] for p in posts)
        )
        self.assertIn("finished debugging", posts[-1]["text"])

    async def test_api_error_and_http_503_are_reported_without_a_session(self):
        failures = (("000003", "thread_not_found"), ("000004", "service_unavailable"))
        for count, (suffix, reason) in enumerate(failures, start=1):
            await self.manager.message(
                event("help debugging on " + URL.replace("000001", suffix), ts=suffix), suffix
            )
            async with asyncio.timeout(2):
                while len(posts := await self.records()) < count:
                    await asyncio.sleep(0.01)
            self.assertIn(reason, posts[-1]["text"])
            self.assertNotIn("wire-test", posts[-1]["text"])
        self.assertFalse(FakeCodex.instances)

    async def test_approval_buttons_and_decision_over_real_http(self):
        session = Session(self.manager, "D123", event()["ts"], URL, "")
        task = asyncio.create_task(
            self.manager.approve(session, {"command": "pwd", "cwd": "/tmp", "reason": "inspect"})
        )
        await until(
            lambda: (
                bool(self.manager.approvals)
                and next(iter(self.manager.approvals.values())).message_ts
            )
        )
        key, approval = next(iter(self.manager.approvals.items()))
        await self.manager.action(
            {
                "user": {"id": "U123"},
                "channel": {"id": "D123"},
                "message": {"ts": approval.message_ts},
                "actions": [{"action_id": "debug_approve", "value": key}],
            }
        )
        self.assertEqual(await task, "accept")
        posts = await self.records()
        self.assertEqual(posts[-1]["blocks"][-1]["elements"][0]["action_id"], "debug_approve")
        self.assertIn("$ pwd\nin /tmp", posts[-1]["text"])


if __name__ == "__main__":
    unittest.main()
