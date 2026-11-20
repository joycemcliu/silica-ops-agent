"""Socket Mode orchestration; only the bot client may write, only to private DMs."""

import asyncio
import contextlib
import html
import json
import logging
import re
import secrets
import shlex
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from slack_sdk.errors import SlackApiError

from .codex import ApprovalPaused, Codex
from .config import APPROVAL_SECONDS, SESSION_SECONDS, is_debug_request, parse_permalink
from .elicitation import elicit
from .reports import format_report, report_blocks, split_text
from .state import SessionStore

SHELLS = {"bash", "zsh", "sh", "dash"}
KNOWN = {"kind", "threadId", "turnId", "itemId", "startedAtMs", "environmentId",
         "reason", "command", "cwd", "commandActions",
         "proposedExecpolicyAmendment", "availableDecisions"}


def display_command(command: str) -> str:
    """Return the string the shell will run, minus a plain `shell -c/-lc '...'` wrapper."""
    try:
        parts = shlex.split(command)
    except ValueError:
        return command
    if len(parts) == 3 and Path(parts[0]).name in SHELLS and parts[1] in ("-c", "-lc"):
        return parts[2]          # exactly what the shell executes, so nothing is hidden
    return command


def display_cwd(cwd: str | None, root: Path) -> str:
    return str(root / cwd) if cwd else "?"


def approval_text(key: str, params: dict, root: Path) -> str:
    lines = [f"Approve? [{key[:8]}] (session pauses after 10 min without a response)"]
    if params.get("command"):
        lines.append("$ " + display_command(params["command"]))
        lines.append("in " + display_cwd(params.get("cwd"), root))
    lines.append("why: " + (params.get("reason") or "(not supplied by Codex)"))
    extra = {k: v for k, v in params.items() if k not in KNOWN}
    if extra:   # file changes, network or extra permissions: anything unusual still shows
        lines.append("extra: " + json.dumps(extra, ensure_ascii=False, separators=(",", ":")))
    return "\n".join(lines)


def preformatted(text):
    return {"type": "rich_text_preformatted", "elements": [{"type": "text", "text": text}]}


def approval_blocks(key, params, root):
    header, details = approval_text(key, {**params, "command": None}, root).split("\n", 1)
    blocks = [{"type": "section", "text": {
        "type": "plain_text", "text": header, "emoji": False,
    }}]
    if params.get("command"):
        for chunk in split_text("$ " + display_command(params["command"])):
            # Native preformatted text preserves indentation and literal backticks.
            blocks.append({"type": "rich_text", "elements": [preformatted(chunk)]})
        details = "in " + display_cwd(params.get("cwd"), root) + "\n" + details
    blocks.extend({"type": "section", "text": {
        "type": "plain_text", "text": chunk, "emoji": False,
    }} for chunk in split_text(details))
    return blocks


def approval_block_text(block):
    if block["type"] == "rich_text":
        return block["elements"][0]["elements"][0]["text"]
    return block["text"]["text"]


LOG = logging.getLogger(__name__)


def safe_error(error):
    if isinstance(error, SlackApiError):
        return f"Slack API: {error.response.get('error', 'request failed')}"
    # No exception repr or request headers: SDK/transport errors can include credentials.
    return str(error) if isinstance(error, (ValueError, RuntimeError)) else type(error).__name__


@dataclass(frozen=True)
class ActivityEntry:
    label: str
    command: str = ""
    commentary: bool = False

    @property
    def text(self):
        return f"{self.label}\n{self.command}" if self.command else self.label

    def block(self):
        if self.commentary:
            return {"type": "section", "text": {
                "type": "plain_text", "text": self.label, "emoji": False,
            }}
        elements = [{"type": "rich_text_quote", "elements": [
            {"type": "text", "text": self.label},
        ]}]
        if self.command:
            elements.append({**preformatted(self.command), "border": 1})
        return {"type": "rich_text", "elements": elements}


class Activity:
    """Bounded activity tail; Slack I/O never runs on the Codex protocol reader."""

    MAX = 2800
    MAX_ENTRIES = 20
    OMITTED = ActivityEntry("Earlier activity omitted…")
    INTERVAL = 2.0
    EXPLORE = {"read": "Read", "search": "Search", "listFiles": "List"}

    def __init__(self, session, mode="summary"):
        self.session, self.mode = session, mode
        self.entries, self.ts = [], None
        self.last = float("-inf")
        self.dirty = False
        self.task = None
        self.lock = asyncio.Lock()

    def entry_for(self, item):
        kind = item.get("type")
        if kind == "commandExecution":
            actions = item.get("commandActions") or []
            exit_code = item.get("exitCode")
            status = f" (exit {exit_code})" if exit_code not in (0, None) else ""
            if actions and all(a.get("type") in self.EXPLORE for a in actions):
                summary = "Explored: " + ", ".join(
                    f"{self.EXPLORE[a['type']]} "
                    + (a.get("name") or a.get("query") or a.get("path") or "")
                    for a in actions
                )
                return ActivityEntry(("🔎 " + summary)[:500 - len(status)].rstrip() + status)
            command = display_command(item.get("command", ""))
            if len(command) > 300:
                command = command[:299] + "…"
            return ActivityEntry("💻 Ran" + status, command)
        if kind == "fileChange":
            paths = ", ".join(c.get("path", "?") for c in item.get("changes", []))
            return ActivityEntry(("📝 Edited " + paths)[:500])
        if kind == "mcpToolCall":
            return ActivityEntry(f"🔧 Tool {item.get('server')}.{item.get('tool')}"[:500])
        # A null phase is also treated as a final answer by Codex.turn().
        if kind == "agentMessage" and item.get("phase") == "commentary":
            text = (item.get("text") or "").strip().removeprefix("• ")[:500]
            if text:
                return ActivityEntry(text, commentary=True)
        return None

    async def feed(self, method, params):
        if self.mode == "off" or method != "item/completed":
            return
        entry = self.entry_for(params.get("item", {}))
        if entry:
            self.entries.append(entry)
            while (len(self.entries) > self.MAX_ENTRIES
                   or len("\n".join(entry.text for entry in self.entries)) > self.MAX):
                if self.entries[0] is self.OMITTED:
                    del self.entries[1]
                else:
                    self.entries[0] = self.OMITTED
            self.dirty = True
            if self.task is None or self.task.done():
                self.task = asyncio.create_task(self._publish())

    async def _publish(self):
        while self.dirty:
            await asyncio.sleep(max(0, self.INTERVAL - (asyncio.get_running_loop().time() - self.last)))
            async with self.lock:
                await self._flush()

    async def _flush(self, rotate=False):
        entries, ts, dirty = self.entries.copy(), self.ts, self.dirty
        if rotate:
            self.entries, self.ts = [], None
        if not dirty:
            return
        self.dirty = False
        self.last = asyncio.get_running_loop().time()
        try:
            async with asyncio.timeout(5):
                response = await self.session.manager.publish_activity(self.session, ts, entries)
                if ts is None and not rotate:
                    self.ts = response["ts"]
        except Exception as error:
            # Progress is best effort, including rate limits and transport failures.
            LOG.warning("Activity update failed (%s)", type(error).__name__)

    async def rotate(self):
        async with self.lock:
            await self._flush(rotate=True)

    async def close(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)


async def read_issue(client, config, url, target_ts):
    query = parse_qs(urlsplit(url).query)
    root_ts = query.get("thread_ts", [target_ts])[0]
    if not re.fullmatch(r"\d{10}\.\d{6}", root_ts):
        raise ValueError("invalid thread timestamp in permalink")

    async def replies(ts):
        messages, cursor = [], None
        while True:
            response = await client.conversations_replies(
                channel=config.channel_id,
                ts=ts,
                limit=100,
                cursor=cursor,
            )
            messages.extend(response.get("messages", []))
            cursor = response.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                if response.get("has_more"):
                    raise RuntimeError(
                        "Slack returned an incomplete thread without a pagination cursor"
                    )
                return messages

    messages = await replies(root_ts)
    target = next((m for m in messages if m.get("ts") == target_ts), None)
    if not target:
        raise ValueError(
            "issue message not found in the supplied thread; copy its full Slack permalink"
        )
    actual_root = target.get("thread_ts", target["ts"])
    if actual_root != root_ts:
        messages = await replies(actual_root)
        if not any(m.get("ts") == target_ts for m in messages):
            raise ValueError("issue reply not found in its parent thread")
    # Include text and attachment metadata without fetching arbitrary URLs or files.
    evidence = [
        {k: m[k] for k in ("ts", "user", "text", "attachments", "files") if k in m}
        for m in messages
    ]
    return actual_root, evidence


@dataclass
class Approval:
    session: object
    future: asyncio.Future
    deadline: float
    message_ts: str = ""


class Session:
    def __init__(self, manager, channel, thread, url, target_ts, resume_thread=None):
        self.manager, self.channel, self.thread = manager, channel, thread
        self.url, self.target_ts = url, target_ts
        self.resume_thread = resume_thread
        self.inputs = asyncio.Queue()
        self.question = None
        self.request_lock = asyncio.Lock()
        self.codex = None
        self.task = None
        self.approval_paused = False
        self.activity = Activity(self, manager.config.activity_mode)

    async def request(self, method, params):
        # One DM reply must answer exactly one interactive request.
        async with self.request_lock:
            if self.approval_paused:
                raise ApprovalPaused
            return await self._request(method, params)

    async def _request(self, method, params):
        if method in (
            "item/commandExecution/requestApproval",
            "item/fileChange/requestApproval",
            "item/tool/requestUserInput",
            "mcpServer/elicitation/request",
        ):
            await self.activity.rotate()
        if method == "mcpServer/elicitation/request":
            return await elicit(self, params)
        if method == "item/commandExecution/requestApproval":
            if not params.get("command") or not params.get("cwd"):
                await self.manager.post(
                    self,
                    "Denied approval: Codex did not supply the full command and working directory.",
                )
                return {"decision": "decline"}
            return {"decision": await self.manager.approve(self, params)}
        if method == "item/fileChange/requestApproval":
            item = self.codex.items.get(params["itemId"])
            if not item or not item.get("changes") or params.get("grantRoot"):
                await self.manager.post(
                    self,
                    "Denied file approval: a complete diff is required and session-wide write grants are disabled. Use a command with one-time sandbox approval.",
                )
                return {"decision": "decline"}
            return {"decision": await self.manager.approve(self, {**params, "fileChanges": item})}
        if method == "item/tool/requestUserInput":
            answers = {}
            for question in params["questions"]:
                if question.get("isSecret"):
                    raise RuntimeError(
                        "secret input is not supported in Slack; configure credentials on the host"
                    )
                self.question = asyncio.get_running_loop().create_future()
                options = "\n".join(
                    f"- {o['label']}: {o.get('description', '')}"
                    for o in question.get("options") or []
                )
                try:
                    await self.manager.post(self, f"{question['question']}\n{options}".strip())
                    reply = await self.question
                    answers[question["id"]] = {"answers": [reply]}
                finally:
                    self.question = None
            return {"answers": answers}
        raise RuntimeError(f"unsupported Codex request: {method}")

    def instructions(self):
        config = self.manager.config
        guide = (config.root / "docs/diagnose_agent_in_slack.md").read_text(encoding="utf-8")
        # Share the Slack guidance without loading diagnosis instructions into a chat turn.
        shared, modes = guide.split("\n## General conversation\n", 1)
        chat, diagnosis = modes.split("\n## Diagnosis sessions\n", 1)
        if not self.url:
            return f"{shared.rstrip()}\n\n## General conversation\n{chat.rstrip()}"
        context = [
            f"Toolkit root: {config.root}",
            f"SILICA_REPO: {config.silica_repo}",
            f"SILICA_ENV_REPO: {config.env_repo}",
        ]
        if config.profile_name:
            servers = ", ".join(config.profile_config.get("mcp_servers", {}))
            context.extend((f"Selected local Codex profile: {config.profile_name}",
                            f"MCP servers in this profile: {servers}"))
        return (
            f"{shared.rstrip()}\n\n## Diagnosis sessions\n{diagnosis.rstrip()}"
            "\n\n## Listener context\n\n" + "\n".join(context)
        )

    async def run(self):
        failure = None
        deadline = asyncio.timeout(SESSION_SECONDS)
        try:
            async with deadline:
                if self.resume_thread:
                    await self.manager.post(
                        self, "Resuming this session. Previous processes were interrupted; "
                        "old approvals and input prompts are no longer valid.",
                    )
                elif self.url:
                    root_ts, issue = await read_issue(
                        self.manager.user_client, self.manager.config, self.url, self.target_ts
                    )
                    await self.manager.post(self, f"working on thread {root_ts}")
                self.codex = self.manager.codex_factory(
                    self.manager.config, self.request, self.activity.feed
                )
                await self.codex.start(self.instructions(), resume_thread=self.resume_thread)
                if self.resume_thread:
                    text = (
                        "Listener recovery: Resumed in the same Slack DM thread after the previous "
                        "process ended.\n\nUser follow-up:\n" + await self.inputs.get()
                    )
                elif self.url:
                    text = (
                        f"Issue permalink: {self.url}\nAgent session ID: {self.codex.session_id}\n"
                        "Issue thread JSON:\n"
                        + json.dumps(issue, ensure_ascii=False)
                    )
                else:
                    text = await self.inputs.get()
                self.manager.store.save(self)
                while True:
                    answer = await self.codex.turn(text)
                    await self.activity.rotate()
                    await self.manager.report(self, answer)
                    text = await self.inputs.get()
        except ApprovalPaused:
            self.approval_paused = True
        except TimeoutError:
            if deadline.expired() and (
                self.approval_paused or any(
                    approval.session is self and not approval.future.done()
                    for approval in self.manager.approvals.values()
                )
            ):
                self.approval_paused = True
            else:
                failure = "timed out after 2h" if deadline.expired() else "operation timed out"
        except asyncio.CancelledError:
            raise
        except Exception as error:
            failure = safe_error(error)
        finally:
            for approval in self.manager.approvals.values():
                if approval.session is self and not approval.future.done():
                    approval.future.cancel()
            try:
                if self.codex:
                    await self.codex.close()
                if failure or self.approval_paused:
                    await self.activity.rotate()
                await self.activity.close()
            finally:
                self.manager.sessions.pop((self.channel, self.thread), None)
        if self.approval_paused:
            await self.manager.post(
                self, "Session paused while waiting for approval. Reply in this thread to resume. "
                "The agent will request fresh approval if needed.",
            )
        elif failure:
            await self.manager.post(self, "failed: " + failure)


class Manager:
    def __init__(self, config, bot_client, user_client, codex_factory=Codex):
        self.config, self.bot_client, self.user_client = config, bot_client, user_client
        self.codex_factory = codex_factory
        self.sessions = {}
        self.approvals = {}
        self.store = SessionStore(config)

    async def post(self, session, text):
        if not session.channel.startswith("D"):
            raise ValueError("bot writes are restricted to private DMs")
        result = None
        # Plain text blocks prevent commands/logs from becoming mentions or misleading links.
        for chunk in split_text(text):
            result = await self.bot_client.chat_postMessage(
                channel=session.channel,
                thread_ts=session.thread,
                text=chunk,
                blocks=[
                    {
                        "type": "section",
                        "text": {"type": "plain_text", "text": chunk, "emoji": False},
                    }
                ],
                unfurl_links=False,
                unfurl_media=False,
            )
        return result

    async def report(self, session, text):
        if not session.channel.startswith("D"):
            raise ValueError("bot writes are restricted to private DMs")
        text = await format_report(
            text, diagnosis=bool(session.url),
            source_roots=(self.config.root, self.config.silica_repo, self.config.env_repo),
        )
        return await self.bot_client.chat_postMessage(
            channel=session.channel,
            thread_ts=session.thread,
            text=html.escape(text, quote=False),
            blocks=report_blocks(text),
            mrkdwn=False,
            parse="none",
            unfurl_links=False,
            unfurl_media=False,
        )

    async def publish_activity(self, session, ts, entries):
        if not session.channel.startswith("D"):
            raise ValueError("bot writes are restricted to private DMs")
        text = "\n".join(entry.text for entry in entries)
        payload = dict(
            channel=session.channel, text=html.escape(text, quote=False),
            blocks=[entry.block() for entry in entries], mrkdwn=False, parse="none",
        )
        if ts is None:
            return await self.bot_client.chat_postMessage(
                thread_ts=session.thread, unfurl_links=False, unfurl_media=False, **payload,
            )
        return await self.bot_client.chat_update(ts=ts, **payload)

    async def message(self, event, event_id):
        if (
            event.get("user") != self.config.user_id
            or event.get("channel_type") != "im"
            or not event.get("channel", "").startswith("D")
            or event.get("bot_id")
            or event.get("subtype")
        ):
            return
        identity = event_id or (event["channel"], event["ts"])
        if not self.store.claim_event(identity):
            return
        channel, text = event["channel"], event.get("text", "").strip()
        thread = event.get("thread_ts")
        if thread:
            session = self.sessions.get((channel, thread))
            if session is None and text:
                saved = self.store.find(channel, thread)
                if saved:
                    session = Session(
                        self, channel, thread, saved["issue_url"], saved["target_ts"],
                        resume_thread=saved["codex_thread"],
                    )
                    self.sessions[(channel, thread)] = session
                    session.task = asyncio.create_task(session.run())
                    session.task.add_done_callback(self._task_done)
            if session is None:
                await self.post(
                    Session(self, channel, thread, "", ""), "session not found, start a new one"
                )
            elif text:
                if session.question and not session.question.done():
                    session.question.set_result(text)
                else:
                    await session.inputs.put(text)
            return
        if not text:
            return
        url, ts = "", ""
        if is_debug_request(text):
            try:
                url, ts = parse_permalink(text, self.config)
            except ValueError as error:
                await self.post(Session(self, channel, event["ts"], "", ""), "failed: " + str(error))
                return
        session = Session(self, channel, event["ts"], url, ts)
        if self.store.find(channel, event["ts"]):
            return  # A redelivered trigger must not replace a saved conversation.
        if not url:
            session.inputs.put_nowait(text)
        self.sessions[(channel, event["ts"])] = session
        session.task = asyncio.create_task(session.run())
        session.task.add_done_callback(self._task_done)

    @staticmethod
    def _task_done(task):
        if not task.cancelled() and task.exception():
            LOG.error(
                "Session could not deliver its failure report (%s)", type(task.exception()).__name__
            )

    async def approve(self, session, params):
        if not session.channel.startswith("D"):
            raise ValueError("bot writes are restricted to private DMs")
        loop = asyncio.get_running_loop()
        key = secrets.token_hex(16)
        approval = Approval(session, loop.create_future(), loop.time() + APPROVAL_SECONDS)
        self.approvals[key] = approval
        status = "Approval request closed."
        details_blocks = []
        text = ""
        timeout = asyncio.timeout_at(approval.deadline)
        try:
            async with timeout:
                blocks = approval_blocks(key, params, self.config.root)
                # Stay below Slack's 4,000-character recommendation, including
                # the status appended when the buttons are removed.
                batches = [[]]
                batch_length = 0
                for block in blocks:
                    block_length = len(approval_block_text(block))
                    if batch_length + 1 + block_length > 3900:
                        batches.append([])
                        batch_length = 0
                    batches[-1].append(block)
                    batch_length += block_length + 1
                for batch in batches[:-1]:
                    await self.bot_client.chat_postMessage(
                        channel=session.channel, thread_ts=session.thread,
                        text="\n".join(approval_block_text(b) for b in batch), blocks=batch,
                        mrkdwn=False, parse="none", unfurl_links=False, unfurl_media=False,
                    )
                details_blocks = batches[-1]
                text = "\n".join(approval_block_text(b) for b in details_blocks)
                response = await self.bot_client.chat_postMessage(
                    channel=session.channel,
                    thread_ts=session.thread,
                    text=text,
                    mrkdwn=False,
                    parse="none",
                    unfurl_links=False,
                    unfurl_media=False,
                    blocks=details_blocks + [
                        {
                            "type": "actions",
                            "elements": [
                                {
                                    "type": "button",
                                    "text": {"type": "plain_text", "text": label},
                                    "action_id": action,
                                    "value": key,
                                }
                                for label, action in (
                                    ("✅ Approve", "debug_approve"),
                                    ("❌ Deny", "debug_deny"),
                                    ("💬 Others", "debug_other"),
                                )
                            ],
                        },
                    ],
                )
                approval.message_ts = response["ts"]
                decision = await approval.future
                status = {
                    "accept": "Approved for this request only.",
                    "decline": "Denied.",
                    "other": "Denied. Your instructions were queued as a follow-up.",
                }[decision]
        except SlackApiError as error:
            failure = f"Could not send approval to Slack ({safe_error(error)})"
            LOG.warning("%s", failure)
            raise RuntimeError(failure) from None
        except TimeoutError:
            if not timeout.expired():
                raise
            session.approval_paused = True
            status = "Approval expired without a response."
            raise ApprovalPaused from None
        finally:
            self.approvals.pop(key, None)
            if approval.message_ts:
                # Remove buttons but retain the command and reason for later review.
                with contextlib.suppress(Exception):
                    async with asyncio.timeout(5):
                        await self.bot_client.chat_update(
                            channel=session.channel,
                            ts=approval.message_ts,
                            blocks=details_blocks + [{
                                "type": "section",
                                "text": {"type": "plain_text", "text": status},
                            }],
                            text=text + "\n" + status,
                            mrkdwn=False,
                            parse="none",
                        )
        return "accept" if decision == "accept" else "decline"

    def pending_approval(self, body, key):
        if body.get("user", {}).get("id") != self.config.user_id:
            return None
        approval = self.approvals.get(key)
        if (
            not approval
            or approval.future.done()
            or asyncio.get_running_loop().time() >= approval.deadline
        ):
            return None
        return approval

    async def action(self, body):
        action = (body.get("actions") or [{}])[0]
        key = action.get("value")
        approval = self.pending_approval(body, key)
        if (
            not approval
            or body.get("channel", {}).get("id") != approval.session.channel
            or body.get("message", {}).get("ts") != approval.message_ts
        ):
            return
        match action.get("action_id"):
            case "debug_approve":
                approval.future.set_result("accept")
            case "debug_deny":
                approval.future.set_result("decline")
            case "debug_other":
                await self.bot_client.views_open(
                    trigger_id=body["trigger_id"],
                    view={
                        "type": "modal",
                        "callback_id": "debug_approval_feedback",
                        "private_metadata": key,
                        "title": {"type": "plain_text", "text": "Approval feedback"},
                        "submit": {"type": "plain_text", "text": "Send instructions"},
                        "blocks": [{
                            "type": "input",
                            "block_id": "feedback",
                            "label": {"type": "plain_text", "text": "What should the agent do?"},
                            "hint": {"type": "plain_text", "text": (
                                "Submitting declines this request and sends your instructions "
                                "to the agent as a follow-up."
                            )},
                            "element": {
                                "type": "plain_text_input",
                                "action_id": "instructions",
                                "multiline": True,
                                "max_length": 3000,
                            },
                        }],
                    },
                )

    def approval_feedback(self, body):
        view = body["view"]
        key = view.get("private_metadata")
        approval = self.pending_approval(body, key)
        if not approval:
            return "This approval is closed. Reply in the original DM thread to follow up."
        entry = view["state"]["values"]["feedback"]["instructions"]
        feedback = (entry.get("value") or "").strip()
        if not feedback:
            return "Enter instructions for the agent."
        approval.session.inputs.put_nowait(
            f"User feedback on denied approval [{key[:8]}]:\n{feedback}"
        )
        approval.future.set_result("other")
        return None

    async def close(self):
        tasks = [s.task for s in list(self.sessions.values()) if s.task]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
