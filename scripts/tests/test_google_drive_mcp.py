"""Exercise RCA rendering and Drive requests without publishing a document."""

import importlib.util
import json
import os
from pathlib import Path
from shutil import copyfile
import stat
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "mcp-servers/google-drive-mcp/google-drive-mcp.py"
spec = importlib.util.spec_from_file_location("google_drive_mcp", SCRIPT)
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


REPORT = {
    "store_code": "staging",
    "store_or_env_name": "Staging Wonderland",
    "incident_title": "Trailer <export> stopped early",
    "date": "2026-11-26",
    "slack_thread_id": "1700000000.123456",
    "severity": "SEV3",
    "status": "Resolved",
    "summary": {
        "what_happened": "A trailer ended early.",
        "who_was_affected": "One session in the staging store.",
        "current_state": "The complete trailer is available.",
    },
    "root_cause": {
        "trigger": "Output volume filled.",
        "underlying_cause": "The renderer had no output space.",
        "detection_gap": "Output-volume capacity had no alert.",
    },
    "follow_up": [{"action": "Alert on free space", "owner": "Ops"}],
    "timeline": {"detected": {"time": "2026-11-26T00:30:00+08:00", "detail": "Support reported it."}},
}


def response(data):
    return Mock(ok=True, json=Mock(return_value=data))


class ReportTests(unittest.TestCase):
    def test_upload_renders_native_doc_in_fixed_folder(self):
        report = server.RCAReport.model_validate(REPORT)
        client = Mock()
        client.request.return_value = response({"id": "new-id"})
        server.upload_report(client, report, None)

        request = client.request.call_args
        self.assertEqual(request.args, ("POST", server.DRIVE_UPLOAD))
        self.assertEqual(request.kwargs["params"]["supportsAllDrives"], "true")
        body = request.kwargs["data"].decode()
        metadata = json.loads(body.split("\r\n\r\n", 2)[1].split("\r\n", 1)[0])
        self.assertEqual(metadata, {
            "name": "Staging Wonderland Trailer <export> stopped early",
            "mimeType": server.DOC_MIME,
            "parents": ["0ACoH-lkKZePWUk9PVA"],
            "appProperties": {"slack_thread_id": REPORT["slack_thread_id"]},
        })
        self.assertIn("Trailer &lt;export&gt; stopped early</h1>", body)
        for heading in ("Summary and impact", "Root cause", "Recovery", "Follow-up", "Incident timeline"):
            self.assertIn(f"<h2>{heading}</h2>", body)
        self.assertIn("duration: N/A", body)
        self.assertIn("affected_session: N/A", body)
        self.assertIn("2026-11-25T16:30:00Z", body)
        self.assertIn("<th>Due</th>", body)
        self.assertIn("<th>Time (UTC)</th>", body)

    def test_retry_reuses_existing_doc_and_explicit_update_keeps_id(self):
        report = server.RCAReport.model_validate(REPORT)
        document = {"id": "existing-id", "name": report.title, "webViewLink": "https://docs.google.com/document/d/existing-id/edit"}
        with TemporaryDirectory() as directory:
            key = Path(directory) / "key.json"
            key.write_text("{}")
            with (
                patch.dict(os.environ, {"RCA_GOOGLE_CREDENTIALS_FILE": str(key)}),
                patch.object(server.Credentials, "from_service_account_info"),
                patch.object(server, "AuthorizedSession") as session,
            ):
                request = session.return_value.__enter__.return_value.request
                request.return_value = response({"files": [document]})
                self.assertEqual(server.create_rca_doc(report)["action"], "existing")
                request.assert_called_once()
                self.assertIn(REPORT["slack_thread_id"], request.call_args.kwargs["params"]["q"])
                request.side_effect = [response({"files": [document]}), response(document)]
                self.assertEqual(server.create_rca_doc(report, replace_existing=True)["url"], document["webViewLink"])
                self.assertEqual(request.call_args.args, ("PATCH", f"{server.DRIVE_UPLOAD}/existing-id"))
                request.side_effect = [response({"files": []})]
                with self.assertRaisesRegex(RuntimeError, "No existing RCA document"):
                    server.create_rca_doc(report, replace_existing=True)

    def test_invalid_configured_credentials_fail_without_creating_local_draft(self):
        report = server.RCAReport.model_validate(REPORT)
        with TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(server, "ROOT", root), patch.dict(os.environ, {"RCA_GOOGLE_CREDENTIALS_FILE": "missing.json"}):
                with self.assertRaisesRegex(RuntimeError, "Correct RCA_GOOGLE_CREDENTIALS_FILE in config.env"):
                    server.create_rca_doc(report)
            self.assertEqual(list(root.iterdir()), [])


class StdioTests(unittest.IsolatedAsyncioTestCase):
    async def test_tool_saves_and_revises_report_with_credentials_unset(self):
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            script = root / SCRIPT.relative_to(ROOT)
            script.parent.mkdir(parents=True)
            copyfile(SCRIPT, script)
            params = StdioServerParameters(command=sys.executable, args=[str(script)])
            async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
                await session.initialize()
                tools = (await session.list_tools()).tools
                self.assertEqual([tool.name for tool in tools], ["create_rca_doc"])
                self.assertFalse(tools[0].annotations.readOnlyHint)

                result = await session.call_tool("create_rca_doc", {"report": REPORT})
                self.assertFalse(result.isError, result.content)
                path = root / "knowledge/rca/drafts/1700000000.123456.html"
                self.assertEqual(result.structuredContent, {"action": "local_draft", "path": str(path)})
                original = path.read_text(encoding="utf-8")
                self.assertIn("Trailer &lt;export&gt; stopped early</h1>", original)
                self.assertIn("<h2>Incident timeline</h2>", original)
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

                revised = {"report": {**REPORT, "incident_title": "Revised title"}}
                await session.call_tool("create_rca_doc", revised)
                self.assertEqual(path.read_text(encoding="utf-8"), original)
                update = await session.call_tool("create_rca_doc", {**revised, "replace_existing": True})
                self.assertEqual(update.structuredContent, result.structuredContent)
                self.assertIn("Revised title</h1>", path.read_text(encoding="utf-8"))
                self.assertEqual(list(path.parent.iterdir()), [path])
