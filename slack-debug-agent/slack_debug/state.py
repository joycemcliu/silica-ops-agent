"""Durable Slack-to-Codex thread mappings, scoped to the configured identity."""

import json
import os
import sqlite3
import tempfile
from contextlib import closing
from pathlib import Path


class SessionStore:
    def __init__(self, config):
        path = config.session_db or config.root / "slack-debug-agent" / "state" / "sessions.sqlite3"
        if str(path) != ":memory:":
            path = Path(path)
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            legacy = config.codex_home / "slack-debug" / "sessions.sqlite3"
            if config.session_db is None and not path.exists() and legacy.is_file():
                # Import earlier deployments once; retain the source as a backup.
                with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as staging:
                    staged = Path(staging.name)
                try:
                    with (
                        closing(sqlite3.connect(legacy.as_uri() + "?mode=ro", uri=True)) as source,
                        closing(sqlite3.connect(staged)) as target,
                    ):
                        source.backup(target)
                    os.replace(staged, path)
                finally:
                    staged.unlink(missing_ok=True)
            # Set permissions before SQLite writes potentially private thread metadata.
            descriptor = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
            os.close(descriptor)
            path.chmod(0o600)
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.scope = json.dumps([
            config.workspace_host, config.user_id, config.channel_id,
            str(config.root), str(config.silica_repo), str(config.env_repo),
            str(config.codex_home), config.profile_name,
        ])
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                scope TEXT NOT NULL, channel TEXT NOT NULL, slack_thread TEXT NOT NULL,
                issue_url TEXT NOT NULL, target_ts TEXT NOT NULL, codex_thread TEXT NOT NULL,
                PRIMARY KEY (scope, channel, slack_thread)
            );
            CREATE TABLE IF NOT EXISTS events (
                scope TEXT NOT NULL, identity TEXT NOT NULL,
                PRIMARY KEY (scope, identity)
            );
        """)

    def claim_event(self, identity):
        with self.db:
            result = self.db.execute(
                "INSERT OR IGNORE INTO events VALUES (?, ?)",
                (self.scope, json.dumps(identity)),
            )
        return result.rowcount == 1

    def save(self, session):
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO sessions VALUES (?, ?, ?, ?, ?, ?)", (
                self.scope, session.channel, session.thread, session.url, session.target_ts,
                session.codex.thread_id,
            ))

    def find(self, channel, thread):
        return self.db.execute(
            "SELECT * FROM sessions WHERE scope = ? AND channel = ? AND slack_thread = ?",
            (self.scope, channel, thread),
        ).fetchone()

    def close(self):
        self.db.close()
