"""Render a bounded findings message without changing approval payloads."""

import html
import json
import re

REPORT_LIMIT = 12000
BLOCK_LIMIT = 2800
CODE = re.compile(r"(```[\s\S]*?```|`[^`\n]*`)")


def split_text(text, limit=BLOCK_LIMIT):
    """Prefer paragraphs, lines, sentences, then words; preserve every character."""
    while len(text) > limit:
        window = text[:limit]
        end = 0
        for separator in ("\n\n", "\n", ". ", " "):
            position = window.rfind(separator)
            if position >= limit // 2:
                end = position + len(separator)
                break
        end = end or limit  # A single oversized token still needs a hard split.
        yield text[:end]
        text = text[end:]
    if text:
        yield text


def format_report(text):
    # Some responses arrive as a JSON string embedded in the protocol's text field.
    if text.strip().startswith('"'):
        try:
            decoded = json.loads(text)
        except ValueError:
            pass
        else:
            if isinstance(decoded, str):
                text = decoded
    parts = CODE.split(text)
    for index, part in enumerate(parts):
        if index % 2:
            parts[index] = html.escape(part, quote=False)
            continue
        # Decode prose line separators only, never shell/code escapes or Unicode.
        part = re.sub(r"(?<!\\)\\r\\n|(?<!\\)\\n", "\n", part)
        part = html.escape(part, quote=False)
        part = re.sub(r"(?m)^#{1,6}\s+(.+)$", r"*\1*", part)
        part = re.sub(r"\*\*(.+?)\*\*", r"*\1*", part)
        part = re.sub(r"\[([^\]\n]+)\]\((https?://[^\s)]+)\)", r"<\2|\1>", part)
        parts[index] = part
    text = "".join(parts).strip()
    if len(text) > REPORT_LIMIT:
        # Keep reference links even when the model ignores the concise-report rule.
        urls = list(dict.fromkeys(re.findall(r"https?://[^\s<>|)]+", text)))
        references = "\n".join(urls[-5:])[-1500:]
        suffix = (
            "\n\n_Report shortened for Slack. Ask a follow-up for omitted details; "
            "see the diagnosis PR for documented findings._"
        )
        if references:
            suffix += "\n" + references
        budget = REPORT_LIMIT - len(suffix) - 4
        excerpt = next(split_text(text, budget)).rstrip()
        if excerpt.count("```") % 2:
            excerpt += "\n```"
        text = excerpt + suffix
    return text


def report_blocks(text):
    """Keep code fences balanced when a long report spans section blocks."""
    blocks = []
    fence = False
    for chunk in split_text(text, BLOCK_LIMIT - 8):
        rendered = ("```\n" if fence else "") + chunk
        if chunk.count("```") % 2:
            fence = not fence
        if fence:
            rendered += "\n```"
        blocks.append({"type": "section", "text": {
            "type": "mrkdwn", "text": rendered, "verbatim": True,
        }})
    return blocks
