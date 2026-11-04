"""Exercise the broker image and sibling command containers without touching installed services."""

import json
import os
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

import pytest
import yaml

from command_guard.cli import exchange


def docker(*args):
    return subprocess.run(["docker", *args], capture_output=True, text=True, timeout=20)


def wait_ready(path):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        try:
            if exchange(str(path), {"action": "health"}) == {"status": "ready"}:
                return
        except OSError:
            pass
        time.sleep(0.1)
    pytest.fail("Containerized broker did not become ready")


def test_broker_container_approval_execution_and_crash_recovery():
    image = os.environ.get("COMMAND_GUARD_GATEWAY_IMAGE", "command-guard-gateway:local")
    try:
        available = docker("image", "inspect", image).returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        available = False
    if not available:
        if os.environ.get("COMMAND_GUARD_REQUIRE_DOCKER") == "1":
            pytest.fail("Build the gateway image before running required Docker tests")
        pytest.skip("Gateway image is unavailable")
    uid, gid = os.getuid(), os.getgid()
    operator_gid = gid + 1
    name = "command-guard-broker-test-" + uuid.uuid4().hex[:12]
    with tempfile.TemporaryDirectory(prefix="cg-broker-") as directory:
        base = Path(directory)
        state, sockets = base / "state", base / "sockets"
        state.mkdir(mode=0o700)
        sockets.mkdir(mode=0o700)
        policy_path = base / "policy.yaml"
        policy = yaml.safe_load(
            (Path(__file__).parents[1] / "config/policy.example.yaml").read_text()
        )
        policy.update(host_root="/hostfs", state_dir=str(state))
        policy["protected_paths"].append(str(Path(__file__).parents[1]))
        policy_path.write_text(yaml.safe_dump(policy))
        started = docker(
            "run",
            "-d",
            "--name",
            name,
            "--init",
            "--user",
            f"{uid}:{gid}",
            "--group-add",
            str(operator_gid),
            *[value for group in os.getgroups() for value in ("--group-add", str(group))],
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,noexec,size=64m",
            "--mount",
            "type=bind,src=/,dst=/hostfs,readonly,bind-propagation=rslave",
            "--mount",
            "type=bind,src=/var/run/docker.sock,dst=/var/run/docker.sock",
            "--mount",
            f"type=bind,src={state},dst={state}",
            "--mount",
            f"type=bind,src={sockets},dst=/run/command-guard",
            "--mount",
            f"type=bind,src={policy_path},dst=/policy.yaml,readonly",
            image,
            "--socket",
            "/run/command-guard/agent.sock",
            "serve",
            "--policy",
            "/policy.yaml",
            "--agent-group",
            str(gid),
            "--operator-group",
            str(operator_gid),
            "--audit",
            str(state / "audit.jsonl"),
        )
        try:
            assert started.returncode == 0, started.stderr
            agent = str(sockets / "agent.sock")
            operator = str(sockets / "operator.sock")
            wait_ready(agent)
            request = exchange(
                agent,
                {
                    "action": "submit",
                    "request": {
                        "command": "printf container-broker-tested",
                        "cwd": "/",
                        "network": True,
                    },
                },
            )
            assert request["status"] == "pending_approval", request
            assert exchange(agent, {"action": "approve", "id": request["id"]})["status"] == "error"
            assert (
                exchange(operator, {"action": "approve", "id": request["id"]})["status"]
                == "approved"
            )
            result = exchange(agent, {"action": "resume", "id": request["id"]})
            assert result["status"] == "finished" and result["exit_code"] == 0, result
            assert result["stdout"] == "container-broker-tested", result
            assert exchange(agent, {"action": "resume", "id": request["id"]})["status"] == "error"
            audit = [json.loads(line) for line in (state / "audit.jsonl").read_text().splitlines()]
            assert any(row["event"] == "execution_finished" for row in audit)
            # A SIGKILL leaves Unix socket files behind. The entrypoint must recover them safely.
            assert docker("kill", name).returncode == 0
            assert docker("start", name).returncode == 0
            wait_ready(agent)
            assert Path(agent).stat().st_uid == uid
        except BaseException:
            print(docker("logs", "--tail", "30", name).stdout)
            print(docker("logs", "--tail", "30", name).stderr)
            raise
        finally:
            docker("rm", "--force", name)
