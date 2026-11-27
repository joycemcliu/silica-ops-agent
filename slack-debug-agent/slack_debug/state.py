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
        self.namespace = [
            config.workspace_host, config.history_token_owner_id, config.channel_id,
            str(config.root), str(config.silica_repo), str(config.env_repo),
            str(config.codex_home), config.profile_name,
        ]
        self.owner = config.history_token_owner_id
        self.scope = self.owner_scope(self.owner)
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
            CREATE TABLE IF NOT EXISTS findings (
                id INTEGER PRIMARY KEY,
                scope TEXT NOT NULL, channel TEXT NOT NULL, slack_thread TEXT NOT NULL,
                text TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS findings_by_thread
            ON findings (scope, channel, slack_thread, id);
            CREATE TABLE IF NOT EXISTS thread_links (
                scope TEXT NOT NULL, source_channel TEXT NOT NULL, source_thread TEXT NOT NULL,
                dm_channel TEXT NOT NULL, dm_thread TEXT NOT NULL,
                PRIMARY KEY (scope, source_channel, source_thread)
            );
        """)

    def owner_scope(self, owner):
        # Keep the original owner's keys compatible and bind new keys to both identities.
        return json.dumps(
            self.namespace if owner == self.owner else [*self.namespace, owner]
        )

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
                self.owner_scope(getattr(session, "owner", self.owner)),
                session.channel, session.thread, session.url, session.target_ts,
                session.codex.thread_id,
            ))

    def find(self, channel, thread, owner=None):
        return self.db.execute(
            "SELECT * FROM sessions WHERE scope = ? AND channel = ? AND slack_thread = ?",
            (self.owner_scope(owner or self.owner), channel, thread),
        ).fetchone()

    def save_finding(self, session, text):
        with self.db:
            self.db.execute(
                "INSERT INTO findings (scope, channel, slack_thread, text) VALUES (?, ?, ?, ?)",
                (self.owner_scope(session.owner), session.channel, session.thread, text),
            )

    def link_thread(self, session, channel, thread):
        with self.db:
            self.db.execute("""
                INSERT INTO thread_links VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (scope, source_channel, source_thread) DO UPDATE SET
                    dm_channel = excluded.dm_channel, dm_thread = excluded.dm_thread
                WHERE excluded.dm_thread >= thread_links.dm_thread
            """, (self.owner_scope(session.owner), channel, thread, session.channel, session.thread))

    def linked_thread(self, owner, channel, thread):
        return self.db.execute(
            "SELECT dm_channel, dm_thread FROM thread_links "
            "WHERE scope = ? AND source_channel = ? AND source_thread = ?",
            (self.owner_scope(owner), channel, thread),
        ).fetchone()

    def findings(self, channel, thread, owner):
        return [row["text"] for row in self.db.execute(
            "SELECT text FROM findings WHERE scope = ? AND channel = ? AND slack_thread = ? "
            "ORDER BY id",
            (self.owner_scope(owner), channel, thread),
        )]

    def close(self):
        self.db.close()
