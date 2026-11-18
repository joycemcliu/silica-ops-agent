import dataclasses
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_agent import URL, Slack, config

from slack_debug.app import Manager, Session
from slack_debug.reports import REPORT_LIMIT, format_report, report_blocks, split_text


class ReportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = Slack()
        self.manager = Manager(config(), self.bot, Slack())
        self.session = Session(self.manager, "D123", "thread", URL, "1794800000.000001")

    async def test_escaped_newlines_json_and_code(self):
        self.assertEqual(await format_report(r"Symptom: broken\nEvidence: timeout"),
                         "Symptom: broken\nEvidence: timeout")
        self.assertEqual(await format_report(json.dumps("Symptom: café\nEvidence: timeout")),
                         "Symptom: café\nEvidence: timeout")
        code = r"`printf '\n'`" + "\n```sh\nprintf '\\n'\n```"
        self.assertEqual(await format_report(code), code)

    async def test_slack_formatting_and_mentions(self):
        await self.manager.report(self.session, (
            "## 🔎 Findings\n- **Cause:** timeout _likely_\n- <u>Check retries</u>\n"
            "[PR](https://example.test/pull/1?a=1&b=2)\n"
            "<!channel> <@U123> & <script>\n`**literal**`"
        ))
        post = self.bot.posts[0]
        heading, bullets, details = post["blocks"][0]["elements"]
        self.assertEqual(heading["elements"][0], {
            "type": "text", "text": "🔎 Findings", "style": {"bold": True},
        })
        self.assertEqual((bullets["type"], bullets["style"]), ("rich_text_list", "bullet"))
        cause, next_step = [item["elements"] for item in bullets["elements"]]
        self.assertEqual(cause, [
            {"type": "text", "text": "Cause:", "style": {"bold": True}},
            {"type": "text", "text": " timeout "},
            {"type": "text", "text": "likely", "style": {"italic": True}},
        ])
        self.assertEqual(next_step, [
            {"type": "text", "text": "Check retries", "style": {"underline": True}},
        ])
        self.assertEqual(details["elements"], [
            {"type": "link", "text": "PR", "url": "https://example.test/pull/1?a=1&b=2"},
            {"type": "text", "text": "\n<!channel> <@U123> & <script>\n"},
            {"type": "text", "text": "**literal**", "style": {"code": True}},
        ])
        self.assertFalse(post["mrkdwn"])
        self.assertIn("&lt;!channel&gt; &lt;@U123&gt;", post["text"])

    def test_split_preserves_text_and_sentence_boundaries(self):
        text = "A complete sentence. " * 500
        chunks = list(split_text(text))
        self.assertEqual("".join(chunks), text)
        self.assertTrue(all(len(chunk) <= 2800 for chunk in chunks))
        self.assertTrue(all(chunk.endswith(". ") for chunk in chunks[:-1]))

    async def test_report_uses_one_message_for_long_prose(self):
        text = "Evidence: a complete sentence.\n" * 200
        await self.manager.report(self.session, text)
        self.assertEqual(len(self.bot.posts), 1)
        post = self.bot.posts[0]
        self.assertEqual(post["thread_ts"], "thread")
        self.assertEqual(post["blocks"], [{"type": "rich_text", "elements": [{
            "type": "rich_text_section", "elements": [{"type": "text", "text": text.strip()}],
        }]}])

    async def test_local_citations_link_to_published_lines_and_leave_code_literal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            def git(*args):
                return subprocess.check_output(["git", "-C", directory, *args], text=True).strip()

            git("init", "--quiet")
            git("remote", "add", "origin", "git@github.com:example/toolkit.git")
            (root / "Published notes.md").write_text("first\nsecond\nthird\n")
            (root / "Edited.md").write_text("old\n")
            git("add", ".")
            git("-c", "user.name=Test", "-c", "user.email=test@example.test", "commit", "-qm", "notes")
            revision = git("rev-parse", "HEAD")
            git("update-ref", "refs/remotes/origin/main", revision)
            (root / "Edited.md").write_text("new\n")
            self.manager.config = dataclasses.replace(self.manager.config, root=root)
            citation = f"[Published]({root}/Published notes.md:2-3)"
            with patch.object(Path, "home", return_value=root):
                await self.manager.report(self.session, (
                    f"{citation}\n[Same file]($HOME/Published%20notes.md:1)\n"
                    f"[Local edit]({root}/Edited.md:1)\n```\n{citation}\n```"
                ))
            post = self.bot.posts[0]
            prose, code = post["blocks"][0]["elements"]
            url = f"https://github.com/example/toolkit/blob/{revision}/Published%20notes.md"
            self.assertEqual([element for element in prose["elements"] if element["type"] == "link"], [
                {"type": "link", "text": "Published", "url": url + "#L2-L3"},
                {"type": "link", "text": "Same file", "url": url + "#L1"},
            ])
            self.assertIn("Local edit (`Edited.md:1`)", post["text"])
            self.assertEqual(code["elements"][0]["text"], citation + "\n")

    async def test_sixty_message_report_is_bounded_and_keeps_pr(self):
        text = "Evidence: a complete finding.\n" * 6000 + "PR: https://example.test/pull/42"
        await self.manager.report(self.session, text)
        self.assertEqual(len(self.bot.posts), 1)
        post = self.bot.posts[0]
        self.assertLessEqual(len(post["text"]), REPORT_LIMIT)
        self.assertIn("Report shortened for Slack", post["text"])
        self.assertIn("https://example.test/pull/42", post["text"])
        self.assertLess(len(post["blocks"]), 10)

    def test_fenced_code_is_preformatted_and_keeps_literal_content(self):
        code = "    **some output** & <@U123>\n" * 300 + "    ```\n"
        blocks = report_blocks(f"```sh\n{code}```\nDone.")
        self.assertEqual(blocks[0]["elements"], [
            {"type": "rich_text_preformatted", "elements": [{"type": "text", "text": code}]},
            {"type": "rich_text_section", "elements": [{"type": "text", "text": "Done."}]},
        ])

    async def test_shortening_closes_code_before_notice(self):
        text = await format_report("```\n" + "long code line\n" * 2000 + "```")
        self.assertLessEqual(len(text), REPORT_LIMIT)
        before_notice = text.split("_Report shortened")[0]
        self.assertEqual(before_notice.count("```") % 2, 0)

    async def test_shortened_chat_reply_uses_a_general_notice(self):
        text = await format_report("An example answer. " * 1000, diagnosis=False)
        self.assertLessEqual(len(text), REPORT_LIMIT)
        self.assertIn("Response shortened for Slack", text)
        self.assertNotIn("diagnosis PR", text)

    async def test_approvals_keep_all_characters_and_literal_escapes(self):
        text = r"printf '\n' " * 800
        await self.manager.post(self.session, text)
        self.assertEqual("".join(p["text"] for p in self.bot.posts), text)
        self.assertTrue(all(p["blocks"][0]["text"]["type"] == "plain_text"
                            for p in self.bot.posts))

    async def test_report_cannot_write_to_channel(self):
        self.session.channel = "C123"
        with self.assertRaisesRegex(ValueError, "private DMs"):
            await self.manager.report(self.session, "hidden")
        self.assertFalse(self.bot.posts)
