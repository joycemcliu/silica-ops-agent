import asyncio
import unittest
from unittest.mock import AsyncMock, patch

from slack_sdk.errors import SlackApiError
from test_agent import Slack, config, until

from slack_debug.app import Manager, Session, approval_blocks, approval_text, display_command
from slack_debug.codex import ApprovalPaused, Codex


class ApprovalDisplayTests(unittest.IsolatedAsyncioTestCase):
    def test_multiline_script_and_literal_markup_stay_inside_code_block(self):
        command = "python - <<'PY'\nimport json\nprint('``` <!channel> & <x>')\nPY"
        root = config().root
        blocks = approval_blocks("12345678abcdef", {
            "command": command, "cwd": str(root), "reason": "Read-only request",
        }, root)
        self.assertEqual(blocks[1], {"type": "rich_text", "elements": [{
            "type": "rich_text_preformatted", "elements": [{
                "type": "text", "text": "$ " + command,
            }],
        }]})
        self.assertEqual(blocks[2]["text"]["text"], f"in {root}")
        self.assertEqual(blocks[3]["text"]["text"], "why: Read-only request")
        self.assertIn(f"\nin {root}\n", approval_text("key", {
            "command": command, "cwd": ".", "reason": "Read-only request",
        }, root))

    async def test_oversized_code_is_complete_and_buttons_follow_all_details(self):
        bot = Slack()
        manager = Manager(config(), bot, Slack())
        session = Session(manager, "D123", "thread", "", "")
        command = "python - <<'PY'\n" + "print('line')\n" * 4000 + "PY"
        with patch("slack_debug.app.APPROVAL_SECONDS", 0.02), self.assertRaises(ApprovalPaused):
            await manager.approve(session, {
                "command": command, "cwd": "/tmp", "reason": "Inspect",
            })
        self.assertGreater(len(bot.posts), 1)
        rendered = "".join(b["elements"][0]["elements"][0]["text"]
                           for p in bot.posts for b in p["blocks"] if b["type"] == "rich_text")
        self.assertEqual(rendered, "$ " + command)
        self.assertTrue(all(len(p["text"]) <= 3900 for p in bot.posts))
        self.assertLessEqual(len(bot.updates[-1]["text"]), 4000)
        self.assertFalse(any(b["type"] == "actions" for p in bot.posts[:-1] for b in p["blocks"]))
        self.assertEqual(bot.posts[-1]["blocks"][-1]["type"], "actions")
        manager.store.close()

    async def test_slack_rejection_keeps_the_error_code_and_closes_the_approval(self):
        class RejectingSlack(Slack):
            async def chat_postMessage(self, **kwargs):
                raise SlackApiError("private response body", {"error": "invalid_blocks"})

        manager = Manager(config(), RejectingSlack(), Slack())
        self.addCleanup(manager.store.close)
        session = Session(manager, "D123", "thread", "", "")
        codex = Codex(manager.config, session.request)
        with patch.object(codex, "send", return_value=None) as send, self.assertLogs():
            await codex._answer({
                "id": "approval",
                "method": "item/commandExecution/requestApproval",
                "params": {"command": "git status", "cwd": "/tmp"},
            })
        self.assertIn("error", send.call_args.args[0])
        self.assertEqual(codex.events.get_nowait(), {
            "method": "client/failure",
            "params": {"reason": "Could not send approval to Slack (Slack API: invalid_blocks)"},
        })
        self.assertFalse(manager.approvals)

    def test_unwrap_only_plain_shell_invocations(self):
        self.assertEqual(display_command("/bin/zsh -lc 'git status'"), "git status")
        for command in ("env FOO=bar bash -c 'pwd'", "bash -c 'pwd' && echo done",
                        "bash -c 'pwd' extra", "echo 'unterminated"):
            self.assertEqual(display_command(command), command)
        self.assertEqual(display_command("bash -c 'pwd\necho done'"), "pwd\necho done")

    def test_compact_details_and_unknown_permissions_are_preserved(self):
        root = config().root
        params = {
            "kind": "command", "command": "/bin/zsh -lc 'git status'",
            "cwd": str(root / "docs"), "reason": "Check checkout",
            "threadId": "internal", "turnId": "internal", "itemId": "internal",
            "startedAtMs": 123, "environmentId": "local", "commandActions": [],
            "proposedExecpolicyAmendment": ["git"], "availableDecisions": ["accept"],
        }
        self.assertEqual(approval_text("12345678abcdef", params, root),
                         "Approve? [12345678] (session pauses after 10 min without a response)\n"
                         f"$ git status\nin {root / 'docs'}\nwhy: Check checkout")
        params["cwd"] = "docs"
        self.assertIn(f"\nin {root / 'docs'}\n", approval_text("key", params, root))
        params["networkPermissions"] = {"host": "example.test"}
        self.assertIn('"networkPermissions":{"host":"example.test"}',
                      approval_text("key", params, root))
        params["cwd"] = "/outside/root"
        self.assertIn("in /outside/root", approval_text("key", params, root))
        self.assertIn('"fileChanges"', approval_text("key", {
            "fileChanges": {"changes": [{"path": "a", "diff": "complete diff"}]},
        }, root))

    async def test_buttons_share_message_full_id_and_details_survive_cleanup(self):
        bot = Slack()
        manager = Manager(config(), bot, Slack())
        session = Session(manager, "D123", "thread", "", "")
        task = asyncio.create_task(manager.approve(session, {
            "command": "/bin/zsh -lc 'git status'", "cwd": "/tmp", "reason": "inspect",
        }))
        try:
            await until(lambda: bot.posts and next(iter(manager.approvals.values())).message_ts)
            self.assertEqual(len(bot.posts), 1)
            key, approval = next(iter(manager.approvals.items()))
            post = bot.posts[0]
            self.assertIn("$ git status\nin /tmp\nwhy: inspect", post["text"])
            self.assertEqual(post["blocks"][0]["text"]["type"], "plain_text")
            self.assertEqual(post["blocks"][1]["elements"][0]["type"], "rich_text_preformatted")
            self.assertEqual(post["blocks"][2]["text"]["text"], "in /tmp")
            self.assertEqual(post["blocks"][3]["text"]["text"], "why: inspect")
            self.assertEqual(post["blocks"][-1]["type"], "actions")
            self.assertTrue(all(b["value"] == key for b in post["blocks"][-1]["elements"]))
            self.assertEqual(
                [b["text"]["text"] for b in post["blocks"][-1]["elements"]],
                ["✅ Approve", "❌ Deny", "💬 Others"],
            )
            self.assertEqual(len(key), 32)
            await manager.action({
                "user": {"id": "U123"}, "channel": {"id": "D123"},
                "message": {"ts": approval.message_ts},
                "actions": [{"action_id": "debug_approve", "value": key}],
            })
            self.assertEqual(await task, "accept")
            update = bot.updates[-1]
            self.assertIn("$ git status", update["text"])
            self.assertIn("Approved for this request only.", update["text"])
            self.assertEqual(update["blocks"][:-1], post["blocks"][:-1])
            self.assertFalse(any(b["type"] == "actions" for b in update["blocks"]))
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def test_other_opens_text_input_and_declines_with_follow_up(self):
        bot = Slack()
        bot.views_open = AsyncMock()
        manager = Manager(config(), bot, Slack())
        self.addCleanup(manager.store.close)
        session = Session(manager, "D123", "thread", "", "")
        task = asyncio.create_task(session.request("item/commandExecution/requestApproval", {
            "command": "pwd", "cwd": str(config().root), "reason": "Inspect",
        }))
        try:
            await until(lambda: bot.posts and next(iter(manager.approvals.values())).message_ts)
            key, approval = next(iter(manager.approvals.items()))
            body = {
                "user": {"id": "U123"}, "channel": {"id": "D123"},
                "message": {"ts": approval.message_ts}, "trigger_id": "trigger",
                "actions": [{"action_id": "debug_other", "value": key}],
            }
            await manager.action({**body, "message": {"ts": "different-message"}})
            bot.views_open.assert_not_awaited()
            await manager.action(body)
            bot.views_open.assert_awaited_once()
            modal = bot.views_open.call_args.kwargs["view"]
            self.assertEqual(modal["private_metadata"], key)
            self.assertFalse(approval.future.done())

            entry = {"value": "  "}
            submission = {"user": body["user"], "view": {
                **modal, "state": {"values": {"feedback": {"instructions": entry}}},
            }}
            self.assertEqual(manager.approval_feedback(submission), "Enter instructions for the agent.")
            entry["value"] = "Leave the tunnels open."
            self.assertIsNotNone(manager.approval_feedback({**submission, "user": {"id": "U999"}}))
            self.assertFalse(approval.future.done())
            self.assertTrue(session.inputs.empty())

            self.assertIsNone(manager.approval_feedback(submission))
            self.assertEqual(await task, {"decision": "decline"})
            self.assertIn("Leave the tunnels open.", session.inputs.get_nowait())
            self.assertIn("queued as a follow-up", bot.updates[-1]["text"])
            self.assertIsNotNone(manager.approval_feedback(submission))
            self.assertTrue(session.inputs.empty())
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def test_non_dm_approval_is_rejected(self):
        bot = Slack()
        manager = Manager(config(), bot, Slack())
        with self.assertRaisesRegex(ValueError, "private DMs"):
            await manager.approve(Session(manager, "C123", "thread", "", ""), {})
        self.assertFalse(bot.posts)
        self.assertFalse(manager.approvals)
