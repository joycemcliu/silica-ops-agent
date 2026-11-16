import argparse
import asyncio
import ctypes
import logging
import signal
import sys
from pathlib import Path

from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_bolt.async_app import AsyncApp
from slack_sdk.web.async_client import AsyncWebClient

from .app import Manager, safe_error
from .config import Config


def protect_listener():
    if sys.platform != "linux":
        raise ValueError(
            "The listener runtime requires Linux; local tests and --check are supported here."
        )
    # Keep same-UID Codex children from reading Slack tokens via /proc or ptrace.
    # https://man7.org/linux/man-pages/man2/PR_SET_DUMPABLE.2const.html
    prctl = ctypes.CDLL(None, use_errno=True).prctl
    prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
    prctl.restype = ctypes.c_int
    if prctl(4, 0, 0, 0, 0) != 0:  # PR_SET_DUMPABLE, SUID_DUMP_DISABLE
        raise OSError(ctypes.get_errno(), "could not protect listener credentials")


async def run(config):
    protect_listener()
    bot = AsyncWebClient(token=config.bot_token, timeout=30)
    user = AsyncWebClient(token=config.user_token, timeout=30)
    bot_auth, user_auth = await asyncio.gather(bot.auth_test(), user.auth_test())
    if bot_auth["team_id"] != user_auth["team_id"] or user_auth["user_id"] != config.user_id:
        raise ValueError(
            "Bot and user tokens must belong to the same workspace and configured user."
        )
    manager = Manager(config, bot, user)
    app = AsyncApp(client=bot)

    @app.event("message")
    async def message(event, body):
        await manager.message(event, body.get("event_id"))

    @app.action("debug_approve")
    @app.action("debug_deny")
    async def action(ack, body):
        await ack()
        await manager.action(body)

    handler = AsyncSocketModeHandler(app, config.app_token)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, stop.set)
    try:
        await handler.connect_async()
        await stop.wait()
    finally:
        await manager.close()
        await handler.close_async()


def main():
    parser = argparse.ArgumentParser(description="Private Slack diagnosis listener")
    parser.add_argument(
        "--check", action="store_true", help="Validate local config without connecting to Slack"
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    try:
        config = Config.load(Path(__file__).resolve().parents[2])
        if args.check:
            print("Local configuration valid; Slack access and live approvals remain unverified.")
        else:
            asyncio.run(run(config))
    except Exception as error:
        parser.exit(1, f"Startup failed: {safe_error(error)}\n")


if __name__ == "__main__":
    main()
