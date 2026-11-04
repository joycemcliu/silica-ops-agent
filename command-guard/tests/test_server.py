import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import threading
from pathlib import Path
from unittest.mock import Mock

import pytest

from command_guard.cli import exchange
from command_guard.gateway import Gateway
from command_guard.models import Assessment
from command_guard.server import MAX_MESSAGE, Server


@pytest.fixture
def socket_dir():
    with tempfile.TemporaryDirectory(prefix="cg-") as directory:
        yield Path(directory)


@pytest.fixture
def servers(socket_dir):
    tmp_path = socket_dir
    tmp_path.chmod(0o700)
    gateway = Mock()
    gateway.submit.return_value = {"status": "pending_approval", "id": "test"}
    gateway.grants.list.return_value = []
    with (
        Server(str(tmp_path / "agent.sock"), gateway, False, os.getgid()) as agent,
        Server(str(tmp_path / "operator.sock"), gateway, True, os.getgid()) as operator,
    ):
        for server in (agent, operator):
            threading.Thread(target=server.serve_forever, daemon=True).start()
        yield gateway, str(tmp_path / "agent.sock"), str(tmp_path / "operator.sock")
        agent.shutdown()
        operator.shutdown()


def test_agent_socket_cannot_approve_or_list(servers):
    gateway, agent, _ = servers
    for message in ({"action": "approve", "id": "test"}, {"action": "list"}):
        assert exchange(agent, message)["status"] == "error"
    gateway.decide.assert_not_called()


def test_readiness_probe_reaches_live_server_without_executing(servers):
    gateway, agent, _ = servers
    assert exchange(agent, {"action": "health"}) == {"status": "ready"}
    gateway.submit.assert_not_called()


def test_operator_socket_cannot_execute(servers):
    gateway, _, operator = servers
    assert exchange(operator, {"action": "submit", "request": {}})["status"] == "error"
    gateway.submit.assert_not_called()
    assert exchange(operator, {"action": "list"}) == {"requests": []}


def test_kernel_identity_not_caller_claims(servers):
    gateway, agent, _ = servers
    result = exchange(agent, {"action": "submit", "request": {"command": "true"}})
    assert result["status"] == "pending_approval"
    assert gateway.submit.call_args.args[0] == os.getuid()
    assert exchange(agent, {"action": "submit", "request": {}, "uid": 0})["status"] == "error"


def test_protocol_rejects_arrays_and_oversized_messages(servers):
    _, agent, _ = servers
    for raw in (b"[]\n", b"x" * (MAX_MESSAGE + 1) + b"\n"):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.connect(agent)
            client.sendall(raw)
            assert json.loads(client.recv(4096))["status"] == "error"


def test_socket_permissions(servers):
    _, agent, operator = servers
    assert os.stat(agent).st_mode & 0o777 == 0o660
    assert os.stat(operator).st_mode & 0o777 == 0o660


def test_socket_parent_must_be_trusted(tmp_path):
    tmp_path.chmod(0o777)
    with pytest.raises(ValueError):
        Server(str(tmp_path / "unsafe.sock"), Mock(), False, os.getgid())


def test_peer_credentials_supported():
    a, b = socket.socketpair()
    with a, b:
        uid = struct.unpack("3i", a.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))[1]
        assert uid == os.getuid()


def test_standalone_client_permission_round_trip(socket_dir, policy, tmp_path):
    assessor = Mock()
    assessor.assess.return_value = Assessment("unrecognized-command", ("Command requires review",))
    runner = Mock()
    runner.run.return_value = {
        "status": "finished",
        "exit_code": 0,
        "timed_out": False,
        "stdout": "ok",
        "stderr": "",
    }
    gateway = Gateway(policy, assessor, runner, Mock())
    agent_path = str(socket_dir / "a.sock")
    operator_path = str(socket_dir / "o.sock")
    client = Path(__file__).resolve().parents[2] / "scripts" / "command-guard-client.py"
    with (
        Server(agent_path, gateway, False, os.getgid()) as agent,
        Server(operator_path, gateway, True, os.getgid()) as operator,
    ):
        for server in (agent, operator):
            threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            pending = subprocess.run(
                [
                    sys.executable,
                    str(client),
                    "--socket",
                    agent_path,
                    "submit",
                    "--command",
                    "printf ok",
                    "--cwd",
                    str(tmp_path),
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert pending.returncode == 3, pending.stderr
            identifier = json.loads(pending.stdout)["id"]
            runner.run.assert_not_called()
            inspected = exchange(operator_path, {"action": "inspect", "id": identifier})
            assert inspected["assessment"]["rule"] == "unrecognized-command"
            assert (
                exchange(operator_path, {"action": "approve", "id": identifier})["status"]
                == "approved"
            )
            resumed = subprocess.run(
                [sys.executable, str(client), "--socket", agent_path, "resume", identifier],
                capture_output=True,
                text=True,
                timeout=10,
            )
            assert resumed.returncode == 0, resumed.stderr
            assert json.loads(resumed.stdout)["stdout"] == "ok"
            runner.run.assert_called_once()
            assert exchange(agent_path, {"action": "resume", "id": identifier})["status"] == "error"
        finally:
            agent.shutdown()
            operator.shutdown()
