"""Build a sanitized host view from disjoint bind mounts, never a bind of host /."""

import json
from pathlib import Path

from ..hostfs import HostFS
from ..models import digest
from ..policy import within

SYSTEM_PATHS = ("/proc", "/sys", "/dev", "/run", "/tmp", "/var/lib/docker", "/var/lib/containerd")


def host_view(policy, request):
    """Split ancestors of exclusions/grants so excluded sources are never mounted.

    Docker forbids private binds of / (an ancestor of its own data directory).
    Sources use canonical paths. Symlinks at split boundaries are omitted.
    """
    protected = (*SYSTEM_PATHS, policy.state_dir, *policy.protected_paths)
    boundaries = (*protected, *policy.sensitive_paths, *request.read_paths, *request.write_paths)
    mounts = []
    fs = HostFS(policy.host_root)

    def visit(value):
        path = fs.path(value)
        if path.is_symlink() or any(within(value, p) for p in protected):
            return
        hidden = any(within(value, p) for p in policy.sensitive_paths)
        readable = any(within(value, p) for p in request.read_paths)
        descendant_grant = any(within(p, value) for p in request.read_paths)
        if hidden and not readable and not descendant_grant:
            return
        must_split = value == "/" or any(p != value and within(p, value) for p in boundaries)
        if must_split and path.is_dir():
            for entry in sorted(path.iterdir()):
                visit(str(Path(value) / entry.name))
        elif path.is_file() or path.is_dir():
            writable = any(within(value, p) for p in request.write_paths)
            mounts.append((value, "/host" + value, writable))
            if len(mounts) > 2048:
                raise ValueError("Host view exceeds 2048 mounts; reduce policy fragmentation")

    roots = sorted(set((*policy.read_only_roots, *request.read_paths, *request.write_paths)))
    for root in roots:
        if not any(other != root and within(root, other) for other in roots):
            visit(root)
    return mounts


def seccomp_profile(network):
    """Tighten a vendored Docker default; never substitute an allow-all filter."""
    profile = json.loads((Path(__file__).parent / "profiles" / "default.json").read_text())
    rules = []
    for rule in profile["syscalls"]:
        rule["names"] = [
            n for n in rule["names"] if n not in {"socket", "socketpair", "socketcall"}
        ]
        if rule["names"]:
            rules.append(rule)
    if network:
        for family in (2, 10):
            rules.append(
                {
                    "names": ["socket"],
                    "action": "SCMP_ACT_ALLOW",
                    "args": [{"index": 0, "value": family, "op": "SCMP_CMP_EQ"}],
                }
            )
    profile["syscalls"] = rules
    return profile


def build(policy, request, name, seccomp_path, uid, gid):
    policy.validate(request)
    args = [
        policy.docker,
        "--host",
        "unix:///var/run/docker.sock",
        "create",
        "--name",
        name,
        "--label",
        "io.commandguard.instance=" + digest(policy.state_dir)[:16],
        "--pull",
        "never",
        "--read-only",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--security-opt",
        f"seccomp={seccomp_path}",
        "--user",
        f"{uid}:{gid}",
        "--pids-limit",
        "128",
        "--memory",
        "1g",
        "--memory-swap",
        "1g",
        "--cpus",
        "1",
        "--ulimit",
        "core=0:0",
        "--ulimit",
        "nofile=256:256",
        "--log-driver",
        "none",
        "--network",
        "bridge" if request.network else "none",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,noexec,size=64m,mode=1777",
        "--tmpfs",
        "/host:rw,nosuid,nodev,size=16m,mode=0755",
        "--env",
        "HOME=/tmp",
        "--env",
        "LANG=C.UTF-8",
        "--env",
        "TMPDIR=/tmp",
        "--env",
        "PATH=/usr/local/bin:/usr/bin:/bin",
        "--workdir",
        "/host" + request.cwd,
    ]
    for source, target, writable in host_view(policy, request):
        if any(ch in source for ch in (",", "\n", "\r")):
            raise ValueError("Mount source contains unsupported characters")
        mode = "" if writable else ",readonly"
        args.extend(
            ["--mount", f"type=bind,src={source},dst={target},bind-recursive=disabled{mode}"]
        )
    args.extend(
        [
            "--entrypoint",
            "/usr/bin/timeout",
            policy.docker_image,
            "--signal=KILL",
            str(policy.timeout),
            "/bin/sh",
            "-c",
            request.command,
        ]
    )
    return args
