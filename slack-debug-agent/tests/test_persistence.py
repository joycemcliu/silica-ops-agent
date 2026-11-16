import dataclasses
import stat
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from test_agent import URL, FakeCodex, Slack, config, event, until

from slack_debug.app import Manager, Session
from slack_debug.state import SessionStore


class PersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.settings = dataclasses.replace(
            config(), session_db=Path(self.directory.name) / "private" / "sessions.sqlite3",
        )
        FakeCodex.instances.clear()
        self.managers = []

    async def asyncTearDown(self):
        for manager in self.managers:
            await manager.close()
            manager.store.close()
        self.directory.cleanup()

    def manager(self, settings=None):
        manager = Manager(settings or self.settings, Slack(), Slack(), FakeCodex)
        self.managers.append(manager)
        return manager

    async def test_new_manager_resumes_saved_thread_on_explicit_reply(self):
        first = self.manager()
        await first.message(event(), "initial")
        await until(lambda: len(first.bot_client.posts) == 2)
        previous = FakeCodex.instances[-1]
        await first.close()
        second = self.manager()
        self.assertFalse(second.sessions)  # No automatic command retry on startup.
        await second.message(event("continue", thread_ts=event()["ts"]), "followup")
        await until(lambda: len(second.bot_client.posts) == 2)
        resumed = FakeCodex.instances[-1]
        self.assertEqual(resumed.resumed_thread, previous.thread_id)
        self.assertIn("Verify their actual state before retrying", resumed.texts[0])
        self.assertIn("User follow-up:\ncontinue", resumed.texts[0])
        self.assertFalse(second.user_client.reads)
        self.assertTrue(previous.closed)
        self.assertTrue(all(p["thread_ts"] == event()["ts"] for p in second.bot_client.posts))
        saved = second.store.find("D123", event()["ts"])
        self.assertEqual(saved["codex_thread"], previous.thread_id)

    async def test_duplicate_messages_stay_deduplicated_across_restart(self):
        first = self.manager()
        await first.message(event(), "initial")
        await until(lambda: len(first.bot_client.posts) == 2)
        await first.close()
        second = self.manager()
        await second.message(event(), "initial")
        self.assertFalse(second.sessions)
        self.assertFalse(second.bot_client.posts)
        self.assertEqual(len(FakeCodex.instances), 1)

    async def test_other_users_channels_and_configurations_cannot_resume(self):
        first = self.manager()
        await first.message(event(), "initial")
        await until(lambda: len(first.bot_client.posts) == 2)
        await first.close()
        second = self.manager()
        await second.message(event("continue", thread_ts=event()["ts"], user="U999"), "other-user")
        await second.message(event("continue", thread_ts=event()["ts"], channel="D999"), "other-dm")
        self.assertFalse(second.sessions)
        changed = self.manager(dataclasses.replace(self.settings, profile_name="other"))
        await changed.message(event("continue", thread_ts=event()["ts"]), "changed-profile")
        self.assertFalse(changed.sessions)
        self.assertIn("session not found", changed.bot_client.posts[-1]["text"])

    async def test_stale_approval_does_not_restore_a_session(self):
        manager = self.manager()
        await manager.action({
            "user": {"id": "U123"}, "channel": {"id": "D123"},
            "message": {"ts": "old-approval"},
            "actions": [{"value": "old-key", "action_id": "debug_approve"}],
        })
        self.assertFalse(manager.sessions)
        self.assertFalse(manager.bot_client.posts)

    async def test_missing_codex_history_reports_failure_without_creating_new_thread(self):
        manager = self.manager()
        session = Session(manager, "D123", "thread", URL, "1794800000.000001")
        session.codex = FakeCodex(self.settings, session.request)
        manager.store.save(session)

        class Missing(FakeCodex):
            async def start(self, instructions, resume_thread=None):
                raise RuntimeError("Saved Codex history is unavailable")

        manager.codex_factory = Missing
        await manager.message(event("continue", thread_ts="thread"), "resume-missing")
        await until(lambda: manager.bot_client.posts and manager.bot_client.posts[-1]["text"].startswith("failed:"))
        self.assertIn("unavailable", manager.bot_client.posts[-1]["text"])
        self.assertFalse(manager.sessions)
        self.assertEqual(manager.store.find("D123", "thread")["codex_thread"], "actual-thread-id")

    def test_default_path_private_permissions_and_identity_scope(self):
        settings = dataclasses.replace(
            self.settings, session_db=None, root=Path(self.directory.name),
            codex_home=Path(self.directory.name) / "codex-home",
        )
        store = SessionStore(settings)
        try:
            path = settings.root / "slack-debug-agent" / "state" / "sessions.sqlite3"
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
            self.assertTrue(store.claim_event("event"))
            self.assertFalse(store.claim_event("event"))
        finally:
            store.close()

    def test_legacy_database_is_imported_once_without_overwriting_local_state(self):
        settings = dataclasses.replace(
            self.settings, root=Path(self.directory.name), session_db=None,
            codex_home=Path(self.directory.name) / "codex-home",
        )
        legacy = settings.codex_home / "slack-debug" / "sessions.sqlite3"
        source = SessionStore(dataclasses.replace(settings, session_db=legacy))
        try:
            source.db.execute("PRAGMA journal_mode=WAL")
            source.claim_event("saved-event")
            source.save(SimpleNamespace(
                channel="D123", thread="saved-thread", url=URL, target_ts="timestamp",
                codex=SimpleNamespace(thread_id="saved-codex-thread"),
            ))
            imported = SessionStore(settings)
            try:
                self.assertEqual(imported.find("D123", "saved-thread")["codex_thread"],
                                 "saved-codex-thread")
                self.assertFalse(imported.claim_event("saved-event"))
                self.assertTrue(imported.claim_event("local-event"))
                self.assertTrue(legacy.is_file())
            finally:
                imported.close()
        finally:
            source.close()
        reopened = SessionStore(settings)
        try:
            self.assertFalse(reopened.claim_event("local-event"))
        finally:
            reopened.close()
