"""Exercise the shell CLI with fake tools; never contact production or use sudo."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "store-sshuttle.sh"


class StoreSshuttleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "calls.jsonl"
        tool = self.bin / "fake-tool"
        tool.write_text("""#!/usr/bin/python3
import json, os, sys, time
name = os.path.basename(sys.argv[0])
args = sys.argv[1:]
with open(os.environ['CALL_LOG'], 'a') as log:
    log.write(json.dumps([name, args]) + '\\n')
if name == 'kubectl' and args[:2] == ['get', 'statefulset']:
    if os.environ.get('QUERY_FAIL'):
        sys.exit(1)
    print(os.environ.get('SUBNET', '26'))
elif name == 'kubectl' and 'port-forward' in args:
    time.sleep(30)
elif name == 'pgrep':
    if os.environ.get('NO_EXISTING_FORWARD'):
        sys.exit(1)
    print('4242')
elif name == 'ps':
    print('kubectl port-forward ' + os.environ.get('FORWARD_TARGET', 'svc/hkcwbmid-ssh') + ' 40026:22')
elif name == 'sshuttle':
    sys.exit(int(os.environ.get('SSHUTTLE_STATUS', '0')))
elif name == 'nc':
    sys.exit(int(os.environ.get('NC_STATUS', '0')))
""")
        tool.chmod(0o755)
        for name in ("kubectl", "sshuttle", "pgrep", "ps", "nc", "sshpass"):
            (self.bin / name).symlink_to(tool)
        self.env = dict(os.environ)
        for key in ("PROD_SSH_NODE", "PN_NODE", "PROD_SSH_USER"):
            self.env.pop(key, None)
        self.env.update(PATH=f"{self.bin}:/usr/bin:/bin", HOME=str(self.root),
                        PROD_SSH_PASSWORD_FILE="", CALL_LOG=str(self.log))

    def run_script(self, *args, cwd=None, **env):
        return subprocess.run(["bash", str(SCRIPT), *args], cwd=cwd or self.root,
                              env={**self.env, **env}, capture_output=True, text=True, timeout=10)

    def calls(self, name):
        if not self.log.exists():
            return []
        return [args for tool, args in map(json.loads, self.log.read_text().splitlines()) if tool == name]

    def test_store_code_is_case_insensitive_without_local_store_files(self):
        for code in ("hkcwbmid", "HKCWBMID", "HkCwBmId"):
            with self.subTest(code=code):
                self.log.unlink(missing_ok=True)
                result = self.run_script(code)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.calls("kubectl")[0][:3], ["get", "statefulset", "hkcwbmid-socat-shared"])
                self.assertEqual(self.calls("sshuttle")[0][-1], "10.26.0.0/16")
                self.assertIn("silica@127.0.0.1:40026", self.calls("sshuttle")[0])

    def test_store_option_and_node_target(self):
        for flag in ("--store", "--cluster", "-c"):
            with self.subTest(flag=flag):
                result = self.run_script(flag, "HKCWBMID", "--node", "1", FORWARD_TARGET="pod/hkcwbmid-socat-shared-1")
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn("pod/hkcwbmid-socat-shared-1", result.stderr)

    def test_bad_subnet_or_lookup_failure_never_starts_sshuttle(self):
        for overrides in ({"SUBNET": ""}, {"SUBNET": "256"}, {"SUBNET": "nope"}, {"QUERY_FAIL": "1"}):
            with self.subTest(overrides=overrides):
                self.log.unlink(missing_ok=True)
                result = self.run_script("HKCWBMID", **overrides)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.calls("sshuttle"), [])

    def test_invalid_arguments_fail_before_kubernetes(self):
        for args in (("../HKCWBMID",), ("hkcwbmid", "another"), ("--store",), ("--unknown",)):
            with self.subTest(args=args):
                result = self.run_script(*args)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(self.calls("kubectl"), [])

    def test_existing_directory_mode_is_preserved(self):
        store = self.root / "HKCWBMID"
        store.mkdir()
        (store / "AGENTS.md").write_text("store_type: corporate\n")
        (store / "infra-cluster.json").write_text('{"network":{"cidr":"10.26.0.0/16"}}')
        result = self.run_script(cwd=store)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls("sshuttle")[0][-1], "10.26.0.0/16")
        self.assertFalse(any(args[:2] == ["get", "statefulset"] for args in self.calls("kubectl")))

    def test_sshuttle_exit_status_is_preserved(self):
        result = self.run_script("HKCWBMID", SSHUTTLE_STATUS="7")
        self.assertEqual(result.returncode, 7, result.stderr)

    def test_existing_forward_uses_bounded_netcat_probe(self):
        result = self.run_script("hkcwbmid")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls("nc"), [["-z", "-w", "1", "127.0.0.1", "40026"]])

    def test_unresponsive_existing_forward_never_starts_sshuttle(self):
        result = self.run_script("hkcwbmid", NC_STATUS="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not responding", result.stderr)
        self.assertEqual(self.calls("sshuttle"), [])

    def test_new_forward_uses_netcat_probe(self):
        result = self.run_script("hkcwbmid", NO_EXISTING_FORWARD="1")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Starting SSH port-forward", result.stderr)
        self.assertEqual(self.calls("nc"), [["-z", "-w", "1", "127.0.0.1", "40026"]])

    def test_native_password_file_permissions(self):
        password_file = self.root / "password"
        password_file.write_text("test-password\n")
        for mode, allowed in ((0o600, True), (0o640, False), (0o604, False)):
            with self.subTest(mode=oct(mode)):
                self.log.unlink(missing_ok=True)
                password_file.chmod(mode)
                result = self.run_script("hkcwbmid", PROD_SSH_PASSWORD_FILE=str(password_file))
                if allowed:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertIn("sshpass", self.calls("sshuttle")[0][1])
                else:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("must not be accessible", result.stderr)
                    self.assertEqual(self.calls("sshuttle"), [])


if __name__ == "__main__":
    unittest.main()
