"""Exercise store-deployment-check.py against fake Nomad/Consul HTTP servers."""

import importlib.util
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
import tempfile
import threading
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "store-deployment-check.py"
spec = importlib.util.spec_from_file_location("store_deployment_check", SCRIPT)
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


def serve(routes):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps(routes.get(self.path, [])).encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"127.0.0.1:{server.server_port}"


class DeploymentCheckTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = Path(tmp.name) / "ABCDEF"
        store.mkdir()
        (store / "module-a.tf").write_text(
            'module "video" {\n postgres = { service = "gateway.service.silica" }\n}\n'
            'module "alarm" {}\n'
        )
        self.env_root = tmp.name

    def run_check(self, nomad, consul):
        servers = [serve(nomad), serve(consul)]
        for s, _ in servers:
            self.addCleanup(s.shutdown)
        args = type("A", (), {
            "store": "abcdef", "env_root": self.env_root,
            "nomad_addr": servers[0][1], "consul_addr": servers[1][1],
        })
        return check.run(args)

    def test_healthy(self):
        nomad = {
            "/v1/jobs": [
                {"ID": "video", "Name": "video", "Type": "service", "Status": "running"},
                {"ID": "alarm", "Name": "alarm", "Type": "service", "Status": "running"},
            ],
            "/v1/allocations": [
                {"JobID": "video", "TaskGroup": "g", "ClientStatus": "running"},
            ],
        }
        consul = {"/v1/health/service/gateway": [{"Checks": [{"Status": "passing"}]}]}
        self.assertEqual({r[0] for r in self.run_check(nomad, consul)}, {"OK"})

    def test_problems(self):
        nomad = {
            "/v1/jobs": [{"ID": "video", "Name": "video", "Type": "service", "Status": "dead"}],
            "/v1/allocations": [
                {"JobID": "video", "TaskGroup": "g", "ClientStatus": "failed", "ModifyIndex": 1},
            ],
        }
        consul = {"/v1/health/service/gateway": [{"Checks": [{"Status": "critical"}]}]}
        got = {(r[0], r[1]) for r in self.run_check(nomad, consul)}
        self.assertIn(("WARN", "module alarm"), got)
        self.assertIn(("FAIL", "alloc video/g"), got)
        self.assertIn(("FAIL", "dns gateway.service.silica"), got)


if __name__ == "__main__":
    unittest.main()
