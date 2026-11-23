"""Check node discovery with a representative Consul catalog response."""

import importlib.util
import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "store-nodes.py"
spec = importlib.util.spec_from_file_location("store_nodes", SCRIPT)
store_nodes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(store_nodes)


class StoreNodesTests(unittest.TestCase):
    def test_prints_sorted_catalog_with_hostname_hints(self):
        nodes = [
            {"Node": "spc31", "Address": "10.26.3.21"},
            {"Node": "R4-VIDEO", "Address": "10.26.4.50"},
            {"Node": "R3-MOCAP", "Address": "10.26.3.40"},
            {"Node": "r2-pi1", "Address": "10.26.2.30"},
            {"Node": "long-backup-node", "Address": "2001:db8::1234"},
            {"Node": "h2", "Address": "10.26.2.21"},
            {"Node": "master-1", "Address": "10.26.0.101"},
        ]
        response = io.BytesIO(json.dumps(nodes).encode())
        response.headers = {}
        stdout = io.StringIO()
        with patch.object(store_nodes, "urlopen", return_value=response) as get, redirect_stdout(stdout):
            self.assertEqual(store_nodes.main(["--consul-addr", "127.0.0.1:18500"]), 0)
        get.assert_called_once_with("http://127.0.0.1:18500/v1/catalog/nodes", timeout=10)
        self.assertEqual(stdout.getvalue().splitlines(), [
            "NODE              IP              ROLE HINT",
            "R3-MOCAP          10.26.3.40      Windows PC (usually runs a motion capture server)",
            "R4-VIDEO          10.26.4.50      Windows video renderer",
            "h2                10.26.2.21      Room/holodeck PC",
            "long-backup-node  2001:db8::1234  Unknown",
            "master-1          10.26.0.101     Linux infrastructure",
            "r2-pi1            10.26.2.30      Linux PC",
            "spc31             10.26.3.21      Windows Unity player PC",
        ])

    def test_query_failure_returns_error(self):
        stderr = io.StringIO()
        with patch.object(store_nodes, "urlopen", side_effect=TimeoutError("timed out")), redirect_stderr(stderr):
            self.assertEqual(store_nodes.main(["--consul-addr", "http://127.0.0.1:18500"]), 1)
        self.assertIn("Could not list Consul nodes", stderr.getvalue())
