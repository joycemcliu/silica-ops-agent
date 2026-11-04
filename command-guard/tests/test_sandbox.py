import os
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest

from command_guard.execution.runner import Runner
from command_guard.execution.sandbox import build, host_view, seccomp_profile
from command_guard.models import Assessment, Command, digest


def test_only_approved_capabilities_are_in_docker_argv(policy, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    request = Command("true", str(work), write_paths=(str(work),), network=True)
    with patch(
        "command_guard.execution.sandbox.host_view",
        return_value=[(str(work), "/host" + str(work), True)],
    ):
        args = build(policy, request, "test-container", "/profile.json", 1001, 1002)
    assert args[args.index("--network") + 1] == "bridge"
    assert args[args.index("--user") + 1] == "1001:1002"
    assert "--read-only" in args and "--cap-drop" in args
    assert "no-new-privileges" in args
    assert "seccomp=/profile.json" in args
    assert args[-3:] == ["/bin/sh", "-c", "true"]
    assert "/usr/bin/timeout" in args
    assert not any("docker.sock" in x for x in args if x.startswith("type=bind"))


def test_host_view_omits_exclusions_and_splits_write_scope(policy, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    request = Command("true", str(work), write_paths=(str(work),))
    mounts = host_view(policy, request)
    for source, _, _ in mounts:
        assert not any(
            Path(excluded).is_relative_to(source)
            for excluded in (
                *policy.protected_paths,
                *policy.sensitive_paths,
                "/run",
                "/proc",
                "/var/lib/docker",
            )
        )
    assert (str(work), "/host" + str(work), True) in mounts


def test_seccomp_preserves_default_deny_and_restricts_sockets():
    for network in (False, True):
        profile = seccomp_profile(network)
        assert profile["defaultAction"] == "SCMP_ACT_ERRNO"
        allowed = [r for r in profile["syscalls"] if r["action"] == "SCMP_ACT_ALLOW"]
        assert not any({"socketpair", "socketcall"} & set(r["names"]) for r in allowed)
        sockets = [r for r in allowed if "socket" in r["names"]]
        assert {r["args"][0]["value"] for r in sockets} == ({2, 10} if network else set())


def test_missing_backend_never_executes_host_shell(policy, tmp_path):
    marker = tmp_path / "must-not-exist"
    with pytest.raises(RuntimeError, match="Docker"):
        Runner(replace(policy, docker="/nonexistent/docker")).run(
            Command(f"touch {marker}", str(tmp_path))
        )
    assert not marker.exists()


@pytest.fixture
def live_runner(policy, tmp_path):
    available = shutil.which("docker") is not None
    if available:
        available = (
            subprocess.run(["docker", "info"], capture_output=True, timeout=10).returncode == 0
        )
    if not available:
        if os.environ.get("COMMAND_GUARD_REQUIRE_DOCKER") == "1":
            pytest.fail("Docker is required but unavailable")
        pytest.skip("Docker unavailable")
    yield Runner(replace(policy, state_dir=str(tmp_path / "state")))


def test_live_writes_require_explicit_mount(live_runner, tmp_path):
    work = tmp_path / "work"
    work.mkdir()
    request = Command("echo changed > target", str(work))
    result = live_runner.run(request)
    assert result["exit_code"] != 0, result
    assert not (work / "target").exists()
    result = live_runner.run(replace(request, write_paths=(str(work),)))
    assert result["exit_code"] == 0, result
    assert (work / "target").read_text() == "changed\n"


def test_live_sensitive_exception_and_protected_source(live_runner, policy, tmp_path):
    secret = Path(policy.sensitive_paths[0]) / "credential"
    secret.write_text("private-test-value")
    protected = Path(policy.protected_paths[0]) / "gateway.py"
    protected.write_text("protected-source")
    for file in (secret, protected):
        assert live_runner.run(Command(f"cat /host{file}", str(tmp_path)))["exit_code"] != 0
    result = live_runner.run(
        Command(f"cat /host{secret}", str(tmp_path), read_paths=(str(secret),))
    )
    assert result["stdout"] == "private-test-value", result
    assert live_runner.run(Command(f"cat /host{secret}", str(tmp_path)))["exit_code"] != 0


@pytest.mark.parametrize("network", [False, True])
def test_live_socket_boundaries(live_runner, tmp_path, network):
    script = """import socket
try:
 socket.socket(socket.AF_UNIX)
except PermissionError:
 pass
else:
 raise AssertionError("Unix sockets allowed")
try:
 socket.socket(socket.AF_INET).close()
except PermissionError:
 assert not NETWORK
else:
 assert NETWORK
""".replace("NETWORK", str(network))
    import shlex

    result = live_runner.run(
        Command("python -c " + shlex.quote(script), str(tmp_path), network=network)
    )
    assert result["exit_code"] == 0, result


def test_live_environment_output_limit_and_timeout(live_runner, tmp_path, monkeypatch):
    monkeypatch.setenv("TYPESAFE_API_KEY", "must-not-reach-command")
    result = live_runner.run(Command("env", str(tmp_path)))
    assert "must-not-reach-command" not in result["stdout"]
    result = live_runner.run(Command("python -c 'print(\"x\" * 2000000)'", str(tmp_path)))
    assert result["output_truncated"]
    assert len(result["stdout"].encode()) <= 1048576
    runner = Runner(replace(live_runner.policy, timeout=1))
    assert runner.run(Command("sleep 10", str(tmp_path)))["timed_out"]


def test_live_host_socket_cannot_be_contacted(live_runner, tmp_path):
    import shlex
    import socket

    path = tmp_path / "host.sock"
    with socket.socket(socket.AF_UNIX) as listener:
        listener.bind(str(path))
        listener.listen()
        script = f"import socket; s=socket.socket(socket.AF_UNIX); s.connect({str('/host' + str(path))!r})"
        result = live_runner.run(
            Command("python -c " + shlex.quote(script), str(tmp_path), network=True)
        )
        assert result["exit_code"] != 0
        assert "PermissionError" in result["stderr"]


def test_cleanup_leaves_no_command_containers(live_runner, tmp_path):
    live_runner.run(Command("true", str(tmp_path)))
    result = subprocess.run(
        [
            "docker",
            "ps",
            "-aq",
            "--filter",
            "label=io.commandguard.instance=" + digest(live_runner.policy.state_dir)[:16],
        ],
        capture_output=True,
        timeout=10,
    )
    assert result.stdout.strip() == b""


def test_cleanup_only_removes_this_gateway_instance(live_runner):
    label = "io.commandguard.instance=" + digest(live_runner.policy.state_dir)[:16]
    identifiers = []
    try:
        for value in (label, "io.commandguard.instance=another-instance"):
            created = live_runner._docker(
                "create",
                "--label",
                value,
                "--entrypoint",
                "/bin/sleep",
                live_runner.policy.docker_image,
                "30",
            )
            assert created.returncode == 0, created.stderr
            identifier = created.stdout.decode().strip()
            identifiers.append(identifier)
            assert live_runner._docker("start", identifier).returncode == 0
        live_runner.cleanup()
        assert live_runner._docker("inspect", identifiers[0]).returncode != 0
        assert live_runner._docker("inspect", identifiers[1]).returncode == 0
    finally:
        if identifiers:
            live_runner._docker("rm", "--force", *identifiers)


def test_read_roots_and_explicit_outside_grants(policy, tmp_path):
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside"
    workspace.mkdir()
    outside.mkdir()
    (workspace / "report").write_text("ok")
    secret = Path(policy.sensitive_paths[0])
    policy = replace(policy, read_only_roots=(str(workspace),))
    request = Command("pwd", str(workspace))
    assert host_view(policy, request) == [(str(workspace), "/host" + str(workspace), False)]
    granted = replace(request, read_paths=(str(outside),))
    policy.validate(granted)
    assert (str(outside), "/host" + str(outside), False) in host_view(policy, granted)
    assert policy.reasons(
        granted,
        Assessment("read-only-command"),
    )
    assert not any(source == str(secret) for source, _, _ in host_view(policy, request))


def test_live_outside_root_hidden_until_explicit_grant(live_runner, tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside-root-test")
    runner = Runner(replace(live_runner.policy, read_only_roots=(str(workspace),)))
    request = Command(f"cat /host{outside}", str(workspace))
    assert runner.run(request)["exit_code"] != 0
    result = runner.run(replace(request, read_paths=(str(outside),)))
    assert result["stdout"] == "outside-root-test", result
