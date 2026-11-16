"""Load immutable configuration once, before accepting Slack events."""

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

CODEX_VERSION = "0.169.0"
APPROVAL_SECONDS = 600
SESSION_SECONDS = 7200


@dataclass(frozen=True)
class Config:
    root: Path
    silica_repo: Path
    env_repo: Path
    codex_home: Path
    codex_bin: str
    user_id: str
    channel_id: str
    workspace_host: str
    bot_token: str = field(repr=False)
    user_token: str = field(repr=False)
    app_token: str = field(repr=False)

    @classmethod
    def load(cls, root: Path):
        root = root.resolve()
        if not (root / "config.env").is_file():
            raise ValueError("Copy config.example.env to config.env and configure it.")
        shared = dotenv_values(root / "config.env", interpolate=False)
        repos = []
        for key in ("SILICA_REPO", "SILICA_ENV_REPO"):
            value = shared.get(key)
            if not value:
                raise ValueError(f"Set {key} in config.env and start a new session.")
            path = (root / value).resolve()
            if not path.is_dir():
                raise ValueError(f"Correct {key} in config.env and start a new session.")
            repos.append(path)

        def required(key):
            value = os.environ.get(key, "").strip()
            if not value:
                raise ValueError(f"Set {key} in slack-debug-agent/deploy/service.env.")
            return value

        user, channel = required("SLACK_DEBUG_USER_ID"), required("SLACK_DEBUG_CHANNEL_ID")
        host = required("SLACK_DEBUG_WORKSPACE_HOST")
        if not re.fullmatch(r"[UW][A-Z0-9]+", user):
            raise ValueError("Invalid SLACK_DEBUG_USER_ID.")
        if not re.fullmatch(r"[CG][A-Z0-9]+", channel):
            raise ValueError("Invalid SLACK_DEBUG_CHANNEL_ID.")
        if not re.fullmatch(r"[a-z0-9-]+\.slack\.com", host):
            raise ValueError("SLACK_DEBUG_WORKSPACE_HOST must be a workspace.slack.com hostname.")
        home = Path(required("SLACK_DEBUG_CODEX_HOME")).expanduser().resolve()
        normal_home = Path.home() / ".codex"
        if home == normal_home.resolve() or home.is_relative_to(root):
            raise ValueError("Use a dedicated SLACK_DEBUG_CODEX_HOME outside the repository.")
        if not (home / "config.toml").is_file():
            raise ValueError("Configure the dedicated Codex home before starting the listener.")
        # Existing rules could silently approve commands that should reach Slack.
        for rules in (home / "rules", root / ".codex" / "rules"):
            if rules.exists() and any(rules.rglob("*.rules")):
                raise ValueError(
                    "Remove execpolicy rules from the Slack Codex profile (v1 has no allowlist)."
                )
        codex = shutil.which("codex")
        if not codex:
            raise ValueError("codex is not on the service PATH.")
        version = subprocess.run(
            [codex, "--version"], capture_output=True, text=True, check=True
        ).stdout.strip()
        if version != f"codex-cli {CODEX_VERSION}":
            raise ValueError(
                f"Expected codex-cli {CODEX_VERSION}; verify the protocol before upgrading."
            )
        tokens = [
            required(name) for name in ("SLACK_BOT_TOKEN", "SLACK_USER_TOKEN", "SLACK_APP_TOKEN")
        ]
        for value, prefix in zip(tokens, ("xoxb-", "xoxp-", "xapp-"), strict=True):
            if not value.startswith(prefix):
                raise ValueError(f"Expected a {prefix} token in the service environment.")
        return cls(root, *repos, home, codex, user, channel, host, *tokens)

    def child_environment(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("SLACK_")}
        env.update(
            CODEX_HOME=str(self.codex_home),
            SILICA_REPO=str(self.silica_repo),
            SILICA_ENV_REPO=str(self.env_repo),
        )
        return env


def parse_permalink(text: str, config: Config):
    match = re.fullmatch(r"help debugging on\s+(?:<([^>|]+)(?:\|[^>]+)?>|(\S+))\s*", text.strip())
    if not match:
        raise ValueError("use: help debugging on <issue-permalink>")
    url = match.group(1) or match.group(2)
    parsed = urlsplit(url)
    path = re.fullmatch(r"/archives/([CG][A-Z0-9]+)/p(\d{10})(\d{6})/?", parsed.path)
    if (
        parsed.scheme != "https"
        or parsed.netloc != config.workspace_host
        or not path
        or parsed.fragment
    ):
        raise ValueError("invalid issue permalink for the configured Slack workspace")
    if path.group(1) != config.channel_id:
        raise ValueError("issue channel is not allowed")
    return url, f"{path.group(2)}.{path.group(3)}"
