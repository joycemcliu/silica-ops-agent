"""Offline checks for evidence boundaries; no store access required."""

from contextlib import redirect_stdout
from email.message import Message
import importlib.util
import io
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
import inspection_http as http


def load(name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


session = load("gather-session-info")
video = load("gather-video-info")


def args():
    return SimpleNamespace(environment="dev", store="staging", session="sample-session", room="1",
                           base_url="https://platform.invalid", timeout=0.1, ca_file=None,
                           timezone="America/New_York", json=False)


def response(data, content_type="application/json"):
    result = Mock()
    result.status = 200
    result.headers = Message()
    result.headers["Content-Type"] = content_type
    result.read.return_value = json.dumps(data).encode()
    result.__enter__ = Mock(return_value=result)
    result.__exit__ = Mock(return_value=False)
    return result


class GatherTests(unittest.TestCase):
    def client(self, *responses):
        client = http.Client(args())
        client.opener = Mock()
        client.opener.open.side_effect = responses
        return client

    def test_session_times_are_progress_times_and_customer_data_is_excluded(self):
        raw = {"id": "sample-session", "holodeckID": "1", "experienceID": "game", "mode": "guest",
               "status": "completed", "createdAt": "2026-11-01T04:00:00Z",
               "bookingStartedAt": "2026-11-01T03:00:00Z", "players": [{"name": "private"}],
               "experienceProgress": {"startTime": "2026-11-01T05:30:00Z", "endTime": "2026-11-01T06:30:00Z"}}
        client = self.client(response(raw), response({"rendering_list": []}))
        result = session.collect(args(), client)
        info = result["session_info"]
        self.assertEqual(info["local_start_time"], "2026-11-01T01:30:00-04:00")
        self.assertEqual(info["local_end_time"], "2026-11-01T01:30:00-05:00")
        self.assertNotIn("private", json.dumps(result))
        self.assertEqual(client.opener.open.call_args_list[0].args[0].full_url,
                         "https://platform.invalid/session/sessions/sample-session")
        for call in client.opener.open.call_args_list:
            self.assertEqual(call.args[0].get_method(), "GET")

    def test_session_survives_video_failure_and_does_not_invent_end_time(self):
        raw = {"id": "sample-session", "holodeckID": "1", "createdAt": "2026-11-01T04:00:00Z"}
        result = session.collect(args(), self.client(response(raw), URLError("offline")))
        self.assertEqual(result["evidence"]["session"]["state"], "retrieved")
        self.assertEqual(result["evidence"]["video_records"]["state"], "could_not_retrieve")
        self.assertIsNone(result["session_info"]["local_start_time"])
        self.assertIsNone(result["session_info"]["local_end_time"])
        self.assertTrue(result["issues"])

    def test_parent_and_child_are_preserved_individually(self):
        tasks = {"parent": {"session": "sample-session", "holodeck": "1", "status": "pending", "dependencies": ["child"]},
                 "child": {"session": "sample-session", "holodeck": "1", "status": "queuing", "render_progress": 0, "dependencies": []}}
        result = video.collect(args(), self.client(response(tasks)))
        self.assertEqual(result["task_count"], 2)
        self.assertEqual(result["evidence"]["tasks"]["data"]["child"]["status"], "queuing")
        self.assertEqual(result["evidence"]["tasks"]["data"]["parent"]["dependencies"], ["child"])
        output = io.StringIO()
        with redirect_stdout(output):
            video.summary(result)
        self.assertIn('status="pending"', output.getvalue())
        self.assertIn('status="queuing"', output.getvalue())

    def test_empty_map_is_zero_but_failed_request_is_unknown(self):
        empty = video.collect(args(), self.client(response({})))
        failed = video.collect(args(), self.client(URLError("offline")))
        self.assertEqual(empty["task_count"], 0)
        self.assertIsNone(failed["task_count"])
        output = io.StringIO()
        with redirect_stdout(output):
            code = http.emit(failed, SimpleNamespace(**{**vars(args()), "json": True}), lambda _: None)
        self.assertEqual(code, 1)
        self.assertIsNone(json.loads(output.getvalue())["task_count"])

    def test_http_404_is_distinct_from_other_errors(self):
        for code, state in ((404, "not_found"), (403, "could_not_retrieve"), (500, "could_not_retrieve"), (302, "could_not_retrieve")):
            with self.subTest(code=code):
                error = HTTPError("https://platform.invalid", code, "", {}, None)
                result = self.client(error).get("/test", video.validate_tasks)
                self.assertEqual(result["state"], state)
                self.assertEqual(result["http_status"], code)

    def test_html_bad_json_and_wrong_shapes_are_failures(self):
        malformed = response({})
        malformed.read.return_value = b'{"unfinished"'
        for reply in (response({}, "text/html"), malformed, response([]), response({"task": []})):
            result = self.client(reply).get("/test", video.validate_tasks)
            self.assertEqual(result["state"], "could_not_retrieve")
            self.assertIsNone(result["data"])

    def test_transport_timeout_is_reported(self):
        result = self.client(TimeoutError()).get("/test", video.validate_tasks)
        self.assertEqual(result["state"], "could_not_retrieve")
        self.assertIn("TimeoutError", result["error"])

    def test_wrong_target_does_not_become_evidence(self):
        result = video.collect(args(), self.client(response({"task": {"session": "other", "holodeck": "1"}})))
        self.assertIsNone(result["task_count"])
        self.assertEqual(result["evidence"]["tasks"]["state"], "could_not_retrieve")
        result = session.collect(args(), self.client(response({"id": "other", "holodeckID": "1"}), response({"rendering_list": []})))
        self.assertIsNone(result["session_info"])

    def test_missing_dependency_is_explicit(self):
        task = {"session": "sample-session", "holodeck": "1", "dependencies": ["missing"]}
        result = video.collect(args(), self.client(response({"parent": task})))
        self.assertTrue(any("dependency missing not present" in item for item in result["issues"]))

    def test_unsafe_inputs_are_rejected(self):
        import argparse
        for value in ("..", "../session", "x?y", "x\n"):
            with self.assertRaises(argparse.ArgumentTypeError):
                http.identifier(value)
        for value in ("file:///tmp/file", "https://user:password@host", "https://host?token=secret"):
            with self.assertRaises(argparse.ArgumentTypeError):
                http.base_url(value)


if __name__ == "__main__":
    unittest.main()
