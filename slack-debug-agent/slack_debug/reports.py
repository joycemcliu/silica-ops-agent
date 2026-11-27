"""Render a bounded findings message without changing approval payloads."""

import json
import re
from itertools import groupby

from .permalinks import link_file_references

REPORT_LIMIT = 12000
BLOCK_LIMIT = 2800
CODE = re.compile(r"(```[\s\S]*?```|`[^`\n]*`)")
FENCE = re.compile(r"^```[^\n]*\n(.*?)^```[ \t]*\r?(?:\n|$)", re.MULTILINE | re.DOTALL)
PIPE_ROW = r"^[ \t]*\|[^\n]*\|[ \t]*\r?(?:\n|$)"
TABLE = rf"(?P<table>{PIPE_ROW}^[ \t]*\|(?:[ \t]*:?-+:?[ \t]*\|)+[ \t]*\r?(?:\n|$)(?:{PIPE_ROW})*)"
REPORT_BLOCK = re.compile(rf"{FENCE.pattern}|{TABLE}", FENCE.flags)
HEADING = re.compile(r"^#{1,6}[ \t]+(\S[^\n]*)", re.MULTILINE)
LIST_ITEM = re.compile(r"^[ \t]*(?:([-+*•])|(\d+[.)]))[ \t]+(?=\S)")
URL = r"https?://(?:[^\s<>()\[\]`|]|\([^\s<>()]+\))+"
INLINE = re.compile(
    r"(?P<code>`[^`\n]+`)|(?P<link>\[(?P<label>[^\[\]\n]+)\]\((?P<target>" + URL + r")\))"
    r"|(?P<url>" + URL + r")|(?P<bold>\*\*\S(?:[^*\n]*?\S)?\*\*)"
    r"|(?P<italic>\*[^*\s](?:[^*\n]*?[^*\s])?\*|(?<!\w)_[^_\s](?:[^_\n]*?[^_\s])?_(?!\w))"
    r"|(?P<underline><u>[^\n]+?</u>)"
)


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


async def format_report(text, *, diagnosis=True, source_roots=()):
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
        if not index % 2:
            # Decode prose line separators only, never shell/code escapes or Unicode.
            parts[index] = re.sub(r"(?<!\\)\\r\\n|(?<!\\)\\n", "\n", part)
    text = "".join(parts).strip()
    if source_roots:
        text = await link_file_references(text, source_roots)
    if len(text) > REPORT_LIMIT:
        # Keep reference links even when the model ignores the concise-report rule.
        urls = dict.fromkeys(re.findall(URL, text))
        references = []
        remaining = 1500
        for url in reversed(list(urls)[-5:]):
            if len(url) < remaining:
                references.append(url)
                remaining -= len(url) + 1
        suffix = "\n\n_Response shortened for Slack. Ask a follow-up for omitted details._"
        if diagnosis:
            suffix = (
                "\n\n_Report shortened for Slack. Ask a follow-up for omitted details; "
                "see the diagnosis PR for documented findings._"
            )
        if references:
            suffix += "\n" + "\n".join(reversed(references))
        budget = REPORT_LIMIT - len(suffix) - 4
        excerpt = next(split_text(text, budget)).rstrip()
        for fence in FENCE.finditer(text):
            if fence.start(1) <= len(excerpt) < fence.end():
                excerpt = excerpt[:fence.end(1)].rstrip("\r\n") + "\n```"
                break
        text = excerpt + suffix
    return text


def text_element(text, **style):
    element = {"type": "text", "text": text}
    if style:
        element["style"] = style
    return element


def inline_elements(text, **style):
    """Render the reply's inline syntax; everything else stays literal."""
    position = 0
    for match in INLINE.finditer(text):
        if match.start() > position:
            yield text_element(text[position:match.start()], **style)
        position = match.end()
        token, kind = match.group(), match.lastgroup
        if kind == "link":
            yield {"type": "link", "url": match["target"], "text": match["label"]}
        elif kind == "url":
            url = token.rstrip(".,;:!?")
            yield {"type": "link", "url": url}
            if url != token:
                yield text_element(token[len(url):], **style)
        else:
            start, end = {"bold": (2, -2), "underline": (3, -4)}.get(kind, (1, -1))
            yield text_element(token[start:end], **{**style, kind: True})
    if position < len(text):
        yield text_element(text[position:], **style)


def prose_elements(text):
    def list_style(line):
        match = LIST_ITEM.match(line)
        return ("bullet" if match[1] else "ordered") if match else None

    for style, lines in groupby(text.splitlines(keepends=True), key=list_style):
        if style:
            yield {"type": "rich_text_list", "style": style, "elements": [
                {"type": "rich_text_section", "elements": list(inline_elements(
                    LIST_ITEM.sub("", line, count=1).rstrip("\r\n")
                ))} for line in lines
            ]}
        else:
            prose = "".join(lines)
            if prose.strip():
                elements = []
                position = 0
                for heading in HEADING.finditer(prose):
                    elements.extend(inline_elements(prose[position:heading.start()]))
                    elements.extend(inline_elements(heading[1], bold=True))
                    position = heading.end()
                elements.extend(inline_elements(prose[position:]))
                yield {"type": "rich_text_section", "elements": elements}


def table_block(text, remaining):
    rows = [
        [cell.strip().replace(r"\|", "|") for cell in re.split(r"(?<!\\)\|", line.strip()[1:-1])]
        for line in text.rstrip("\n").split("\n")
    ]
    header, separators, *body = rows
    data = [header, *body]
    if (len(data) > 100 or len(header) > 20
            or any(len(row) != len(separators) for row in data)):
        return None
    size = sum(len(cell) for row in data for cell in row)
    if not 0 < size <= remaining:
        return None

    return {
        "type": "table",
        "column_settings": [
            {"align": "center" if separator.startswith(":") else "right"}
            if separator.endswith(":") else {"align": "left"}
            for separator in separators
        ],
        "rows": [[
            {"type": "rich_text", "elements": [{
                "type": "rich_text_section", "elements": list(inline_elements(cell)),
            }]} if cell else {"type": "raw_text", "text": ""}
            for cell in row
        ] for row in data],
    }, size


def report_blocks(text, *, limit=50):
    blocks = []
    elements = []
    position = 0
    remaining = 10000
    for match in REPORT_BLOCK.finditer(text):
        table = None
        if match["table"]:
            # Leave room for prose before and after this table in Slack's 50-block payload.
            if len(blocks) >= limit - 2 or (table := table_block(match["table"], remaining)) is None:
                continue
        elements.extend(prose_elements(text[position:match.start()]))
        if table:
            block, size = table
            remaining -= size
            if elements:
                blocks.append({"type": "rich_text", "elements": elements})
                elements = []
            blocks.append(block)
        elif match[1]:
            elements.append({"type": "rich_text_preformatted", "elements": [text_element(match[1])]})
        position = match.end()
    elements.extend(prose_elements(text[position:]))
    if elements:
        blocks.append({"type": "rich_text", "elements": elements})
    return blocks
