import json
import unittest

from test_agent import Slack, config

from slack_debug.app import Manager, Session
from slack_debug.reports import REPORT_LIMIT, format_report, report_blocks, split_text


class ReportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = Slack()
        self.manager = Manager(config(), self.bot, Slack())
        self.session = Session(self.manager, "D123", "thread", "", "")

    def test_escaped_newlines_json_and_code(self):
        self.assertEqual(format_report(r"Symptom: broken\nEvidence: timeout"),
                         "Symptom: broken\nEvidence: timeout")
        self.assertEqual(format_report(json.dumps("Symptom: café\nEvidence: timeout")),
                         "Symptom: café\nEvidence: timeout")
        code = r"`printf '\n'`" + "\n```sh\nprintf '\\n'\n```"
        self.assertEqual(format_report(code), code)

    def test_slack_formatting_and_mentions(self):
        rendered = format_report(
            "## Findings\n**Cause:** timeout\n[PR](https://example.test/pull/1)\n"
            "<!channel> <@U123> & <script>\n`**literal**`"
        )
        self.assertEqual(rendered,
                         "*Findings*\n*Cause:* timeout\n<https://example.test/pull/1|PR>\n"
                         "&lt;!channel&gt; &lt;@U123&gt; &amp; &lt;script&gt;\n`**literal**`")

    def test_split_preserves_text_and_sentence_boundaries(self):
        text = "A complete sentence. " * 500
        chunks = list(split_text(text))
        self.assertEqual("".join(chunks), text)
        self.assertTrue(all(len(chunk) <= 2800 for chunk in chunks))
        self.assertTrue(all(chunk.endswith(". ") for chunk in chunks[:-1]))

    async def test_report_uses_one_message_and_multiple_blocks(self):
        text = "Evidence: a complete sentence.\n" * 200
        await self.manager.report(self.session, text)
        self.assertEqual(len(self.bot.posts), 1)
        post = self.bot.posts[0]
        self.assertEqual(post["thread_ts"], "thread")
        self.assertGreater(len(post["blocks"]), 1)
        self.assertTrue(all(len(block["text"]["text"]) <= 3000 for block in post["blocks"]))
        self.assertEqual("".join(b["text"]["text"] for b in post["blocks"]), text.strip())
        self.assertTrue(all(b["text"]["verbatim"] for b in post["blocks"]))

    async def test_sixty_message_report_is_bounded_and_keeps_pr(self):
        text = "Evidence: a complete finding.\n" * 6000 + "PR: https://example.test/pull/42"
        await self.manager.report(self.session, text)
        self.assertEqual(len(self.bot.posts), 1)
        post = self.bot.posts[0]
        self.assertLessEqual(len(post["text"]), REPORT_LIMIT)
        self.assertIn("Report shortened for Slack", post["text"])
        self.assertIn("https://example.test/pull/42", post["text"])
        self.assertLess(len(post["blocks"]), 10)

    def test_code_fences_remain_balanced_across_blocks(self):
        blocks = report_blocks("```\n" + "some output\n" * 500 + "```\nDone.")
        self.assertGreater(len(blocks), 1)
        self.assertTrue(all(b["text"]["text"].count("```") % 2 == 0 for b in blocks))

    def test_shortening_closes_code_before_notice(self):
        text = format_report("```\n" + "long code line\n" * 2000 + "```")
        self.assertLessEqual(len(text), REPORT_LIMIT)
        before_notice = text.split("_Report shortened")[0]
        self.assertEqual(before_notice.count("```") % 2, 0)

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
