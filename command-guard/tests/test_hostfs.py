from dataclasses import replace

import pytest

from command_guard.execution.sandbox import host_view
from command_guard.hostfs import HostFS
from command_guard.models import Command
from command_guard.policy import Policy


@pytest.fixture
def root(tmp_path):
    root = tmp_path / "host-root"
    (root / "etc").mkdir(parents=True)
    (root / "home" / "worker" / "project").mkdir(parents=True)
    (root / "etc" / "host-only").write_text("host")
    (root / "home" / "worker" / "project" / "alias").symlink_to("/etc/host-only")
    return root


def test_absolute_symlinks_resolve_in_host_root(root):
    fs = HostFS(root)
    assert fs.canonical("/home/worker/project/alias") == "/etc/host-only"
    assert fs.path(fs.canonical("/home/worker/project/alias")).read_text() == "host"
    with pytest.raises(FileNotFoundError):
        fs.canonical("/usr/bin/python")  # An image path must not satisfy a host path.
    (root / "home" / "worker" / "project" / "relative").symlink_to("../../../etc/host-only")
    assert fs.canonical("/home/worker/project/relative") == "/etc/host-only"
    with pytest.raises(ValueError):
        fs.path("/../etc/passwd")


def test_globs_follow_host_symlinks_and_policy_uses_host_coordinates(root, tmp_path):
    (root / "homes").symlink_to("/home")
    (root / "home" / "worker" / ".secret").write_text("secret")
    fs = HostFS(root)
    assert fs.glob("/homes/*/.secret") == ["/homes/worker/.secret"]
    path = tmp_path / "policy.yaml"
    path.write_text(
        f'host_root: "{root}"\nprotected_paths: ["/gateway"]\nsensitive_paths: ["/homes/*/.secret"]\n'
    )
    assert Policy.load(path).sensitive_paths == ("/home/worker/.secret",)


def test_commands_and_mount_sources_remain_host_paths(root):
    command = Command.parse({"command": "pwd", "cwd": "/home/worker/project"}, host_root=str(root))
    assert command.cwd == "/home/worker/project"
    policy = Policy(
        ("/gateway",), ("/etc/host-only",), host_root=str(root), read_only_roots=("/home",)
    )
    mounts = host_view(policy, command)
    assert ("/home", "/host/home", False) in mounts
    assert not any(str(root) in source for source, _, _ in mounts)
    with pytest.raises(ValueError):
        Command.parse(
            {
                "command": "true",
                "cwd": "/home/worker/project",
                "read_paths": ["/home/worker/project/alias"],
            },
            host_root=str(root),
        )
    request = replace(command, read_paths=("/etc/host-only",))
    policy.validate(request)
    assert ("/etc/host-only", "/host/etc/host-only", False) in host_view(policy, request)


def test_symlink_loop_fails_closed(root):
    (root / "etc" / "loop").symlink_to("loop")
    with pytest.raises(ValueError, match="symlinks"):
        HostFS(root).canonical("/etc/loop")
