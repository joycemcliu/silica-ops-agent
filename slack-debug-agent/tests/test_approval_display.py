import asyncio
import unittest
from unittest.mock import patch

from test_agent import Slack, config, until

from slack_debug.app import Manager, Session, approval_blocks, approval_text, display_command


class ApprovalDisplayTests(unittest.IsolatedAsyncioTestCase):
    def test_multiline_script_and_literal_markup_stay_inside_code_block(self):
        command = "python - <<'PY'\nimport json\nprint('``` <!channel> & <x>')\nPY"
        blocks = approval_blocks("12345678abcdef", {
            "command": command, "cwd": str(config().root), "reason": "Read-only request",
        }, config().root)
        self.assertEqual(blocks[1], {"type": "rich_text", "elements": [{
            "type": "rich_text_preformatted", "elements": [{
                "type": "text", "text": "$ " + command,
            }],
        }]})
        self.assertEqual(blocks[2]["text"]["text"], "in .\nwhy: Read-only request")

    async def test_oversized_code_is_complete_and_buttons_follow_all_details(self):
        bot = Slack()
        manager = Manager(config(), bot, Slack())
        session = Session(manager, "D123", "thread", "", "")
        command = "python - <<'PY'\n" + "print('line')\n" * 4000 + "PY"
        with patch("slack_debug.app.APPROVAL_SECONDS", 0.02):
            self.assertEqual(await manager.approve(session, {
                "command": command, "cwd": "/tmp", "reason": "Inspect",
            }), "decline")
        self.assertGreater(len(bot.posts), 1)
        rendered = "".join(b["elements"][0]["elements"][0]["text"]
                           for p in bot.posts for b in p["blocks"] if b["type"] == "rich_text")
        self.assertEqual(rendered, "$ " + command)
        self.assertTrue(all(len(p["blocks"]) <= 11 and len(p["text"]) < 30000 for p in bot.posts))
        self.assertFalse(any(b["type"] == "actions" for p in bot.posts[:-1] for b in p["blocks"]))
        self.assertEqual(bot.posts[-1]["blocks"][-1]["type"], "actions")
        manager.store.close()

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
                         "Approve? [12345678] (denies in 10 min)\n"
                         "$ git status\nin docs\nwhy: Check checkout")
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
            self.assertEqual(post["blocks"][-1]["type"], "actions")
            self.assertTrue(all(b["value"] == key for b in post["blocks"][-1]["elements"]))
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
            self.assertEqual(update["blocks"][1], post["blocks"][1])
            self.assertFalse(any(b["type"] == "actions" for b in update["blocks"]))
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
