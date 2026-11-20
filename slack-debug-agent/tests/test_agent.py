import asyncio
import dataclasses
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from slack_debug.__main__ import protect_listener
from slack_debug.app import Manager, Session, read_issue
from slack_debug.codex import ApprovalPaused, Codex
from slack_debug.config import Config, parse_permalink

ROOT = Path(__file__).resolve().parents[2]
URL = "https://example.slack.com/archives/C123/p1794800000000001"


def config(root=ROOT):
    return Config(
        root,
        root.parent / "silica",
        root.parent / "silica-environments",
        root.parent / "slack-codex-test",
        "codex",
        "U123",
        "C123",
        "example.slack.com",
        "xoxb-test",
        "xoxp-test",
        "xapp-test",
        session_db=":memory:",
    )


def event(text="help debugging on " + URL, **kwargs):
    return {
        "user": "U123",
        "channel_type": "im",
        "channel": "D123",
        "ts": "1794800001.000001",
        "text": text,
        **kwargs,
    }


class Slack:
    def __init__(self, pages=None):
        self.posts, self.updates, self.reads = [], [], []
        self.pages = pages or [
            {"ok": True, "messages": [{"ts": "1794800000.000001", "text": "broken"}]}
        ]

    async def chat_postMessage(self, **kwargs):
        self.posts.append(kwargs)
        return {"ok": True, "ts": str(len(self.posts))}

    async def chat_update(self, **kwargs):
        self.updates.append(kwargs)
        return {"ok": True}

    async def conversations_replies(self, **kwargs):
        self.reads.append(kwargs)
        return self.pages.pop(0)


class FakeCodex:
    instances = []

    def __init__(self, config, handler, on_notification=None):
        self.config, self.handler = config, handler
        self.on_notification = on_notification
        self.closed, self.texts, self.items = False, [], {}
        self.session_id = "actual-thread-id"
        self.thread_id = self.session_id
        self.instances.append(self)

    async def start(self, instructions, resume_thread=None):
        self.instructions = instructions
        self.resumed_thread = resume_thread
        return self.session_id

    async def turn(self, text):
        self.texts.append(text)
        return "finished debugging\nPR: https://example.test/pr/1"

    async def close(self):
        self.closed = True


async def until(predicate):
    async with asyncio.timeout(2):
        while not predicate():
            await asyncio.sleep(0.001)


class ConfigTests(unittest.TestCase):
    def test_linux_listener_disables_dumpability_before_starting_children(self):
        with (
            patch("slack_debug.__main__.sys.platform", "linux"),
            patch("slack_debug.__main__.ctypes.CDLL") as libc,
        ):
            libc.return_value.prctl.return_value = 0
            protect_listener()
            libc.return_value.prctl.assert_called_once_with(4, 0, 0, 0, 0)
            libc.return_value.prctl.return_value = -1
            with self.assertRaises(OSError):
                protect_listener()
        with (
            patch("slack_debug.__main__.sys.platform", "darwin"),
            patch("slack_debug.__main__.resource.setrlimit") as limit,
            patch("slack_debug.__main__.ctypes.CDLL") as libc,
        ):
            protect_listener()
            libc.assert_not_called()
            limit.assert_called_once()
        with (
            patch("slack_debug.__main__.sys.platform", "win32"),
            self.assertRaisesRegex(ValueError, "supports Linux and macOS"),
        ):
            protect_listener()

    def test_permalink_validation(self):
        for text in ("help debugging on " + URL, "help debugging on <" + URL + "|issue>"):
            self.assertEqual(parse_permalink(text, config()), (URL, "1794800000.000001"))
        for url in (
            URL.replace("C123", "C999"),
            URL.replace("example.slack.com", "evil.test"),
            URL.replace("https:", "http:"),
            URL + "#bad",
            "https://example.slack.com@evil.test/",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                parse_permalink("help debugging on " + url, config())

    def test_config_mandatory_and_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "Copy config.example"):
                Config.load(root)
            (root / "config.env").write_text("SILICA_REPO=missing\n")
            with self.assertRaisesRegex(ValueError, "Correct SILICA_REPO"):
                Config.load(root)
            for name in ("silica", "env", "codex-home"):
                (root / name).mkdir()
            (root / "config.env").write_text("SILICA_REPO=silica\nSILICA_ENV_REPO=env\n")
            home = root / "codex-home"
            (home / "config.toml").touch()
            # A sibling dedicated home is required; resolve the root separately.
            toolkit = root / "toolkit"
            toolkit.mkdir()
            (toolkit / "config.env").write_text("SILICA_REPO=../silica\nSILICA_ENV_REPO=../env\n")
            env = {
                "SLACK_DEBUG_USER_ID": "U123",
                "SLACK_DEBUG_CHANNEL_ID": "C123",
                "SLACK_DEBUG_WORKSPACE_HOST": "example.slack.com",
                "SLACK_DEBUG_CODEX_HOME": str(home),
                "SLACK_BOT_TOKEN": "xoxb-test",
                "SLACK_USER_TOKEN": "xoxp-test",
                "SLACK_APP_TOKEN": "xapp-test",
            }
            with (
                patch.dict(os.environ, env),
                patch("shutil.which", return_value="/test/codex"),
            ):
                loaded = Config.load(toolkit)
                self.assertEqual(loaded.codex_bin, "/test/codex")
                self.assertEqual(loaded.activity_mode, "summary")
                with patch.dict(os.environ, {"SLACK_DEBUG_ACTIVITY": "off"}):
                    self.assertEqual(Config.load(toolkit).activity_mode, "off")
                with patch.dict(os.environ, {"SLACK_DEBUG_ACTIVITY": "invalid"}):
                    with self.assertRaisesRegex(ValueError, "SLACK_DEBUG_ACTIVITY"):
                        Config.load(toolkit)
                (toolkit / "config.env").write_text("SILICA_REPO=changed\n")
                self.assertEqual(loaded.silica_repo, (root / "silica").resolve())
                self.assertFalse(any(k.startswith("SLACK_") for k in loaded.child_environment()))
                (toolkit / "config.env").write_text(
                    "SILICA_REPO=../silica\nSILICA_ENV_REPO=../env\n"
                )
                (home / "rules").mkdir()
                (home / "rules/allow.rules").touch()
                with self.assertRaisesRegex(ValueError, "Remove execpolicy"):
                    Config.load(toolkit)
                profile_file = home / "diagnose.config.toml"
                profile_file.write_text('model="profile-model"\n[features]\nhooks=true\n')
                loaded_profile = Config.load(toolkit, profile="diagnose")
                self.assertEqual(loaded_profile.profile_name, "diagnose")
                self.assertEqual(loaded_profile.profile_config["model"], "profile-model")
                profile_file.write_text('model="changed"\n')
                self.assertEqual(loaded_profile.profile_config["model"], "profile-model")
                with self.assertRaisesRegex(ValueError, "profile not found"):
                    Config.load(toolkit, profile="missing")
                with self.assertRaisesRegex(ValueError, "Profile names"):
                    Config.load(toolkit, profile="../invalid")
                # Explicit profile selection permits the existing interactive home.
                with (
                    patch("slack_debug.config.Path.home", return_value=home.parent),
                    patch.dict(os.environ, {"SLACK_DEBUG_CODEX_HOME": str(home.parent / ".codex")}),
                ):
                    (home.parent / ".codex").symlink_to(home, target_is_directory=True)
                    self.assertEqual(
                        Config.load(toolkit, profile="diagnose").codex_home, home.resolve()
                    )


class AgentTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        FakeCodex.instances.clear()
        self.bot, self.user = Slack(), Slack()
        self.manager = Manager(config(), self.bot, self.user, FakeCodex)

    async def asyncTearDown(self):
        await self.manager.close()

    async def test_private_authorized_messages_only_and_invalid_urls(self):
        for change in (
            {"user": "U999"},
            {"channel_type": "channel", "channel": "C123"},
            {"bot_id": "B123"},
            {"subtype": "message_changed"},
        ):
            await self.manager.message(event(**change), str(change))
        self.assertFalse(self.bot.posts)
        await self.manager.message(event("help debugging on " + URL.replace("C123", "C999")), "bad")
        self.assertFalse(self.manager.sessions)
        self.assertFalse(self.user.reads)
        self.assertIn("not allowed", self.bot.posts[-1]["text"])

    async def test_followup_reuses_session_and_duplicate_is_ignored(self):
        await self.manager.message(event(), "first")
        await self.manager.message(event(), "first")
        await until(lambda: len(self.bot.posts) == 2)
        await self.manager.message(
            event("more evidence", thread_ts=event()["ts"], ts="2"), "follow"
        )
        await until(lambda: len(self.bot.posts) == 3)
        self.assertEqual(len(FakeCodex.instances), 1)
        client = FakeCodex.instances[0]
        self.assertEqual(client.texts[-1], "more evidence")
        self.assertIn("actual-thread-id", client.texts[0])
        self.assertTrue(
            all(p["channel"] == "D123" and p["thread_ts"] == event()["ts"] for p in self.bot.posts)
        )
        await self.manager.close()
        self.assertTrue(client.closed)
        await self.manager.message(event("after restart", thread_ts=event()["ts"], ts="3"), "lost")
        await until(lambda: len(FakeCodex.instances) == 2 and len(self.bot.posts) == 5)
        self.assertEqual(FakeCodex.instances[-1].resumed_thread, client.thread_id)
        self.assertIn("after restart", FakeCodex.instances[-1].texts[-1])

    async def test_polite_debug_command_fetches_issue_thread(self):
        await self.manager.message(event(f"please debug <{URL}|{URL}>"), "polite-debug")
        await until(lambda: FakeCodex.instances and FakeCodex.instances[0].texts)
        self.assertEqual(len(self.user.reads), 1)
        self.assertEqual(self.user.reads[0]["channel"], "C123")
        self.assertTrue(self.bot.posts[0]["text"].startswith("working on thread"))
        self.assertIn("Issue thread JSON:", FakeCodex.instances[0].texts[0])

    async def test_concurrent_sessions_keep_followups_separate(self):
        self.user.pages *= 2
        await self.manager.message(event(), "session-one")
        await self.manager.message(event(ts="1794800002.000001"), "session-two")
        await until(lambda: len(self.bot.posts) == 4)
        self.assertEqual(len(FakeCodex.instances), 2)
        await self.manager.message(
            event("first only", thread_ts=event()["ts"], ts="follow"), "follow-first"
        )
        await until(lambda: len(self.bot.posts) == 5)
        self.assertEqual(FakeCodex.instances[0].texts[-1], "first only")
        self.assertEqual(len(FakeCodex.instances[1].texts), 1)

    async def test_reply_permalink_and_pagination(self):
        target = "1794800000.000001"
        root = "1794700000.000001"
        user = Slack(
            [
                {"messages": [{"ts": target, "thread_ts": root}]},
                {
                    "messages": [{"ts": root}],
                    "has_more": True,
                    "response_metadata": {"next_cursor": "next"},
                },
                {"messages": [{"ts": target, "thread_ts": root, "text": "reply"}]},
            ]
        )
        actual, messages = await read_issue(user, config(), URL, target)
        self.assertEqual(actual, root)
        self.assertEqual(messages[-1]["text"], "reply")
        self.assertEqual(user.reads[-1]["cursor"], "next")
        user = Slack([{"messages": [{"ts": root}, {"ts": target, "thread_ts": root}]}])
        await read_issue(user, config(), URL + "?thread_ts=" + root, target)
        self.assertEqual(user.reads[0]["ts"], root)

    async def test_missing_issue_does_not_start_codex(self):
        self.user.pages = [{"messages": []}]
        await self.manager.message(event(), "missing")
        await until(lambda: bool(self.bot.posts))
        self.assertFalse(FakeCodex.instances)
        self.assertFalse(self.manager.sessions)
        self.assertIn("failed:", self.bot.posts[-1]["text"])

    async def test_long_command_and_approval_identity(self):
        session = Session(self.manager, "D123", "thread", URL, "")
        command = "echo '<!channel>'\n" + "x" * 9000
        task = asyncio.create_task(
            self.manager.approve(session, {"command": command, "cwd": "/tmp", "reason": "inspect"})
        )
        await until(
            lambda: (
                bool(self.manager.approvals) and list(self.manager.approvals.values())[0].message_ts
            )
        )
        key, approval = next(iter(self.manager.approvals.items()))
        body = {
            "user": {"id": "U999"},
            "channel": {"id": "D123"},
            "message": {"ts": approval.message_ts},
            "actions": [{"value": key, "action_id": "debug_approve"}],
        }
        await self.manager.action(body)
        self.assertFalse(task.done())
        body["user"]["id"] = "U123"
        body["channel"]["id"] = "D999"
        await self.manager.action(body)
        self.assertFalse(task.done())
        body["channel"]["id"] = "D123"
        await self.manager.action(body)
        self.assertEqual(await task, "accept")
        rendered = "".join(b["elements"][0]["elements"][0]["text"]
                           for p in self.bot.posts for b in p["blocks"]
                           if b["type"] == "rich_text")
        self.assertEqual(rendered, "$ " + command)
        self.assertTrue(all(len(p["text"]) < 30000 for p in self.bot.posts))
        self.assertFalse(self.manager.approvals)
        self.assertFalse(any(b["type"] == "actions" for b in self.bot.updates[-1]["blocks"]))
        await self.manager.action(body)  # A replay cannot approve another command.

    async def test_approval_timeout_expires_the_buttons_and_pauses(self):
        session = Session(self.manager, "D123", "thread", URL, "")
        with patch("slack_debug.app.APPROVAL_SECONDS", 0.01), self.assertRaises(ApprovalPaused):
            await self.manager.approve(session, {"command": "test", "cwd": "/"})
        self.assertFalse(self.manager.approvals)
        self.assertIn("expired without a response", self.bot.updates[-1]["text"])
        self.assertFalse(any(b["type"] == "actions" for b in self.bot.updates[-1]["blocks"]))

    async def test_explicit_denial_and_stale_click(self):
        session = Session(self.manager, "D123", "thread", URL, "")
        task = asyncio.create_task(self.manager.approve(session, {"command": "test", "cwd": "/"}))
        await until(
            lambda: (
                bool(self.manager.approvals)
                and next(iter(self.manager.approvals.values())).message_ts
            )
        )
        key, approval = next(iter(self.manager.approvals.items()))
        body = {
            "user": {"id": "U123"},
            "channel": {"id": "D123"},
            "message": {"ts": approval.message_ts},
            "actions": [{"value": key, "action_id": "debug_deny"}],
        }
        await self.manager.action(body)
        self.assertEqual(await task, "decline")
        self.assertTrue(self.bot.updates[-1]["text"].endswith("\nDenied."))

    async def test_unreviewable_requests_fail_closed_and_questions_continue(self):
        session = Session(self.manager, "D123", "thread", URL, "")
        session.codex = FakeCodex(config(), session.request)
        self.assertEqual(
            await session.request("item/commandExecution/requestApproval", {"command": "test"}),
            {"decision": "decline"},
        )
        self.assertEqual(
            await session.request("item/fileChange/requestApproval", {"itemId": "x"}),
            {"decision": "decline"},
        )
        with self.assertRaisesRegex(RuntimeError, "unsupported"):
            await session.request("new/unknown/approval", {})
        self.manager.sessions[("D123", "thread")] = session
        task = asyncio.create_task(
            session.request(
                "item/tool/requestUserInput",
                {"questions": [{"id": "store", "question": "Which store?"}]},
            )
        )
        await until(lambda: session.question is not None)
        await self.manager.message(event("usbaymkt", thread_ts="thread"), "answer")
        self.assertEqual(await task, {"answers": {"store": {"answers": ["usbaymkt"]}}})

    async def test_timeout_kills_active_session(self):
        class Hanging(FakeCodex):
            async def turn(self, text):
                await asyncio.Event().wait()

        self.manager.codex_factory = Hanging
        with patch("slack_debug.app.SESSION_SECONDS", 0.03):
            await self.manager.message(event(), "timeout")
            await until(
                lambda: (
                    self.bot.posts and self.bot.posts[-1]["text"] == "failed: timed out after 2h"
                )
            )
        self.assertTrue(FakeCodex.instances[0].closed)
        self.assertFalse(self.manager.sessions)

    async def test_operation_timeout_is_not_reported_as_two_hours(self):
        class TimedOut(FakeCodex):
            async def turn(self, text):
                raise TimeoutError

        self.manager.codex_factory = TimedOut
        await self.manager.message(event(), "operation-timeout")
        await until(
            lambda: self.bot.posts and self.bot.posts[-1]["text"] == "failed: operation timed out"
        )
        self.assertTrue(FakeCodex.instances[0].closed)


class ProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_pause_exits_the_turn_without_sending_an_approval_response(self):
        client = Codex(config(), AsyncMock(side_effect=ApprovalPaused))
        client.thread_id = "thread-1"
        with (
            patch.object(client, "call", AsyncMock(return_value={"turn": {"id": "turn-1"}})),
            patch.object(client, "send", AsyncMock()) as send,
        ):
            await client._answer({"id": "approval-1", "method": "item/commandExecution/requestApproval"})
            with self.assertRaises(ApprovalPaused):
                await client.turn("investigate")
            send.assert_not_awaited()

    async def test_real_subprocess_handshake_approval_and_shutdown(self):
        # A wire peer exercises JSON framing and asynchronous bidirectional requests,
        # without using credentials or invoking a model.
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "codex"
            executable.write_text(
                "#!"
                + str(ROOT / ".venv/bin/python")
                + "\n"
                + """
import json, sys
for line in sys.stdin:
    m = json.loads(line)
    method = m.get("method")
    if method == "initialize":
        result = {}
    elif method == "thread/start":
        assert m["params"]["approvalPolicy"] == "on-request"
        cfg = m["params"]["config"]
        assert cfg["model"] == "profile-model"
        assert cfg["sandbox_mode"] == "workspace-write"
        assert cfg["features"]["hooks"] is False
        assert cfg["sandbox_workspace_write"]["network_access"] is False
        assert cfg["sandbox_workspace_write"]["writable_roots"] == []
        result = {"thread": {"id": "thread-1", "sessionId": "session-1"}}
    elif method == "turn/start":
        print(json.dumps({"id": m["id"], "result": {"turn": {"id": "turn-1"}}}), flush=True)
        print(json.dumps({"id": "approval-1", "method": "item/commandExecution/requestApproval", "params": {"command": "pwd", "cwd": "/tmp"}}), flush=True)
        continue
    elif m.get("id") == "approval-1":
        assert m["result"] == {"decision": "decline"}
        print(json.dumps({"method": "item/completed", "params": {"turnId": "turn-1", "item": {"id": "i", "type": "agentMessage", "phase": "final_answer", "text": "denied safely"}}}), flush=True)
        print(json.dumps({"method": "turn/completed", "params": {"turn": {"id": "turn-1", "status": "completed"}}}), flush=True)
        continue
    else:
        continue
    print(json.dumps({"id": m["id"], "result": result}), flush=True)
"""
            )
            executable.chmod(0o700)
            seen = []

            async def deny(method, params):
                seen.append((method, params))
                return {"decision": "decline"}

            notifications = []

            async def notified(method, params):
                notifications.append((method, params))

            client = Codex(
                dataclasses.replace(
                    config(),
                    codex_bin=str(executable),
                    profile_name="diagnose",
                    profile_config={
                        "model": "profile-model",
                        "sandbox_mode": "danger-full-access",
                        "features": {"hooks": True},
                        "sandbox_workspace_write": {
                            "network_access": True,
                            "writable_roots": ["/"],
                        },
                    },
                ),
                deny,
                notified,
            )
            try:
                await client.start("diagnose")
                self.assertEqual(client.session_id, "session-1")
                self.assertEqual(await client.turn("investigate"), "denied safely")
                self.assertEqual(seen[0][1]["command"], "pwd")
                self.assertEqual([method for method, _ in notifications],
                                 ["item/completed", "turn/completed"])
            finally:
                await client.close()
            self.assertIsNotNone(client.process.returncode)


if __name__ == "__main__":
    unittest.main()
