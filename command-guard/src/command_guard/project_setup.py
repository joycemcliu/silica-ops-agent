"""Initialize Git-ignored project data from a trusted, short-lived Docker setup container."""

import argparse
import os
import shutil
from pathlib import Path

import yaml


def read_env(path):
    if not path.exists():
        return {}
    return dict(
        line.split("=", 1)
        for line in path.read_text().splitlines()
        if line.strip() and not line.startswith("#") and "=" in line
    )


def initialize(
    data,
    project_root,
    uid,
    gid,
    worker_image,
    gateway_image,
    template,
    legacy_config=None,
    legacy_state=None,
    docker_gid=None,
):
    data, root = Path(data), Path(project_root)
    config, state, sockets = data / "config", data / "state", data / "sockets"
    for directory in (config, state, sockets):
        directory.mkdir(parents=True, exist_ok=True)
    migrating = legacy_config is not None and not (config / "policy.yaml").exists()
    if migrating:
        legacy_config = Path(legacy_config)
        for name in ("policy.yaml", "service.env", "compose.env"):
            if (legacy_config / name).exists():
                shutil.copy2(legacy_config / name, config / name)
        if legacy_state and Path(legacy_state).exists():
            shutil.copytree(legacy_state, state, dirs_exist_ok=True)
        backup = data / "legacy-backup"
        shutil.copytree(legacy_config, backup, dirs_exist_ok=True)
        for path in (backup, *backup.rglob("*")):
            if not path.is_symlink():
                os.chown(path, uid, gid)
                path.chmod(0o700 if path.is_dir() else 0o600)
    old = read_env(config / "compose.env")
    # A numeric identity needs no host account and stays separate from the AI worker.
    broker_uid = int(old.get("GUARD_UID", "60000"))
    if broker_uid in (0, uid):
        broker_uid = 60001 if uid == 60000 else 60000
    broker_gid = int(old.get("GUARD_GID", str(broker_uid)))
    if broker_gid == 0:
        broker_gid = broker_uid
    operator_gid = int(old.get("GUARD_OPERATOR_GID", str(broker_gid)))
    if operator_gid == gid:
        operator_gid = broker_gid if broker_gid != gid else gid + 1
    if not all(0 <= value < 2**32 for value in (uid, gid, broker_uid, broker_gid, operator_gid)):
        raise ValueError("Invalid UID/GID")
    policy_path = config / "policy.yaml"
    policy = yaml.safe_load(
        policy_path.read_text() if policy_path.exists() else Path(template).read_text()
    )
    policy["protected_paths"] = sorted(
        set(policy["protected_paths"])
        | {
            str(root / "command-guard"),
            str(root / "command-guard.sh"),
            str(root / ".command-guard"),
        }
    )
    policy.update(
        host_root="/hostfs",
        state_dir=str(root / ".command-guard" / "state"),
        docker="/usr/bin/docker",
        docker_image=worker_image,
    )
    policy_path.write_text(yaml.safe_dump(policy, sort_keys=False))
    env_path = config / "service.env"
    if not env_path.exists():
        env_path.write_text("# TYPESAFE_API_KEY=your-key\n")
    compose = {
        "GUARD_UID": broker_uid,
        "GUARD_GID": broker_gid,
        "GUARD_AGENT_GID": gid,
        "GUARD_OPERATOR_GID": operator_gid,
        "GUARD_DOCKER_GID": docker_gid,
        "GUARD_GATEWAY_IMAGE": gateway_image,
    }
    (config / "compose.env").write_text(
        "".join(f"{key}={value}\n" for key, value in compose.items())
    )
    (data / ".gitignore").write_text("*\n")
    for path in (data, data / ".gitignore", config):
        os.chown(path, uid, broker_gid if path == config else gid)
        path.chmod(0o750 if path == config else (0o755 if path.is_dir() else 0o600))
    os.chown(policy_path, uid, broker_gid)
    policy_path.chmod(0o640)
    for path in (env_path, config / "compose.env"):
        os.chown(path, uid, gid)
        path.chmod(0o600)
    for path in (state, *state.rglob("*")):
        if not path.is_symlink():
            os.chown(path, broker_uid, broker_gid)
            path.chmod(0o700 if path.is_dir() else 0o600)
    os.chown(sockets, broker_uid, broker_gid)
    sockets.chmod(0o755)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--uid", required=True, type=int)
    parser.add_argument("--gid", required=True, type=int)
    parser.add_argument("--docker-gid", required=True, type=int)
    parser.add_argument("--worker-image", required=True)
    parser.add_argument("--gateway-image", required=True)
    args = parser.parse_args()
    initialize(
        "/data",
        args.project_root,
        args.uid,
        args.gid,
        args.worker_image,
        args.gateway_image,
        "/template.yaml",
        legacy_config="/legacy-config" if Path("/legacy-config").exists() else None,
        legacy_state="/legacy-state" if Path("/legacy-state").exists() else None,
        docker_gid=args.docker_gid,
    )


if __name__ == "__main__":
    main()
