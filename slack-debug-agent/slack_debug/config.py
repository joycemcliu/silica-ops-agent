"""Load immutable configuration once, before accepting Slack events."""

import os
import re
import shutil
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import dotenv_values

APPROVAL_SECONDS = 600
IDLE_SECONDS = 7200
DEBUG_COMMAND = re.compile(
    r"(?:please\s+)?(?:help\s+)?(?:debugging|debug|checking|check|investigating)(?:\s+on)?\s+"
    r"(?:<([^>|]+)(?:\|[^>]+)?>|(\S+))\s*",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Config:
    root: Path
    silica_repo: Path
    env_repo: Path
    codex_home: Path
    codex_bin: str
    history_token_owner_id: str
    channel_id: str
    workspace_host: str
    bot_token: str = field(repr=False)
    user_token: str = field(repr=False)
    app_token: str = field(repr=False)
    profile_name: str | None = None
    profile_config: dict = field(default_factory=dict, repr=False)
    activity_mode: str = "summary"
    session_db: Path | str | None = None
    allowed_users: frozenset[str] = frozenset()

    def allows(self, user):
        return user in self.allowed_users

    @classmethod
    def load(cls, root: Path, profile: str | None = None):
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

        activity_mode = os.environ.get("SLACK_DEBUG_ACTIVITY", "summary").strip()
        if activity_mode not in ("off", "summary"):
            raise ValueError("SLACK_DEBUG_ACTIVITY must be off or summary.")
        token_owner = required("SLACK_USER_TOKEN_OWNER_ID")
        channel = required("SLACK_DEBUG_CHANNEL_ID")
        host = required("SLACK_DEBUG_WORKSPACE_HOST")
        if not re.fullmatch(r"[UW][A-Z0-9]+", token_owner):
            raise ValueError("Invalid SLACK_USER_TOKEN_OWNER_ID.")
        allowed_users = frozenset(os.environ.get("SLACK_DEBUG_ALLOWED_USERS", "").replace(",", " ").split())
        if any(not re.fullmatch(r"[UW][A-Z0-9]+", entry) for entry in allowed_users):
            raise ValueError("Invalid user ID in SLACK_DEBUG_ALLOWED_USERS.")
        if not re.fullmatch(r"[CG][A-Z0-9]+", channel):
            raise ValueError("Invalid SLACK_DEBUG_CHANNEL_ID.")
        if not re.fullmatch(r"[a-z0-9-]+\.slack\.com", host):
            raise ValueError("SLACK_DEBUG_WORKSPACE_HOST must be a workspace.slack.com hostname.")
        home = Path(required("SLACK_DEBUG_CODEX_HOME")).expanduser().resolve()
        normal_home = Path.home() / ".codex"
        if home.is_relative_to(root) or (home == normal_home.resolve() and profile is None):
            raise ValueError("Use a dedicated SLACK_DEBUG_CODEX_HOME outside the repository.")
        if not (home / "config.toml").is_file():
            raise ValueError("Configure the dedicated Codex home before starting the listener.")
        profile_config = {}
        if profile is not None:
            if not re.fullmatch(r"[A-Za-z0-9_-]+", profile):
                raise ValueError(
                    "Profile names may contain letters, numbers, hyphens, and underscores."
                )
            profile_path = home / f"{profile}.config.toml"
            if not profile_path.is_file():
                raise ValueError(f"Codex profile not found: {profile_path}")
            with profile_path.open("rb") as source:
                profile_config = tomllib.load(source)
        else:
            # Dedicated deployments must not inherit silent command approvals.
            # Explicit --profile local testing reuses that home's existing rules.
            for rules in (home / "rules", root / ".codex" / "rules"):
                if rules.exists() and any(rules.rglob("*.rules")):
                    raise ValueError(
                        "Remove execpolicy rules from the Slack Codex profile (v1 has no allowlist)."
                    )
        codex = shutil.which("codex")
        if not codex:
            raise ValueError("codex is not on the service PATH.")
        tokens = [
            required(name) for name in ("SLACK_BOT_TOKEN", "SLACK_USER_TOKEN", "SLACK_APP_TOKEN")
        ]
        for value, prefix in zip(tokens, ("xoxb-", "xoxp-", "xapp-"), strict=True):
            if not value.startswith(prefix):
                raise ValueError(f"Expected a {prefix} token in the service environment.")
        return cls(
            root, *repos, home, codex, token_owner, channel, host, *tokens,
            profile, profile_config, activity_mode, allowed_users=allowed_users,
        )

    def child_environment(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("SLACK_")}
        env.update(
            CODEX_HOME=str(self.codex_home),
            SILICA_REPO=str(self.silica_repo),
            SILICA_ENV_REPO=str(self.env_repo),
        )
        return env


def is_debug_request(text: str) -> bool:
    if re.match(r"(?:please\s+)?help\s+debugging\s+on\b", text, re.IGNORECASE):
        return True
    match = DEBUG_COMMAND.fullmatch(text)
    return bool(match and "://" in (match.group(1) or match.group(2)))


def parse_permalink(text: str, config: Config):
    match = DEBUG_COMMAND.fullmatch(text.strip())
    if not match:
        raise ValueError("use: help debugging on <issue-permalink>")
    url = match.group(1) or match.group(2)
    channel, ts = slack_message_link(url, config)
    if channel != config.channel_id:
        raise ValueError("issue channel is not allowed")
    return url, ts


def slack_message_link(url, config):
    parsed = urlsplit(url)
    path = re.fullmatch(r"/archives/([CGD][A-Z0-9]+)/p(\d{10})(\d{6})/?", parsed.path)
    if (
        parsed.scheme != "https"
        or parsed.netloc != config.workspace_host
        or not path
        or parsed.fragment
    ):
        raise ValueError("invalid message permalink for the configured Slack workspace")
    return path.group(1), f"{path.group(2)}.{path.group(3)}"
