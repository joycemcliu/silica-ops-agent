import os

import yaml

from command_guard.project_setup import initialize, read_env


def test_project_setup_preserves_migrated_and_subsequently_edited_secrets(tmp_path, monkeypatch):
    # Ownership is applied by the root setup container; exercise generation and real file modes here.
    monkeypatch.setattr(os, "chown", lambda *args: None)
    root = tmp_path / "repo"
    root.mkdir()
    legacy = tmp_path / "legacy-config"
    old_state = tmp_path / "legacy-state"
    legacy.mkdir()
    old_state.mkdir()
    template = tmp_path / "template.yaml"
    template.write_text("protected_paths: [/var/lib/docker]\nsensitive_paths: [/root]\n")
    (legacy / "policy.yaml").write_bytes(template.read_bytes())
    (legacy / "service.env").write_text("TYPESAFE_API_KEY=test-secret\n")
    (legacy / "compose.env").write_text(
        "GUARD_UID=12345\nGUARD_GID=12345\nGUARD_OPERATOR_GID=12346\n"
    )
    (old_state / "audit.jsonl").write_text('{"event":"old"}\n')
    data = root / ".command-guard"
    args = (data, root, os.getuid(), os.getgid(), "worker-image", "gateway-image", template)
    initialize(*args, legacy_config=legacy, legacy_state=old_state, docker_gid=986)
    policy = yaml.safe_load((data / "config/policy.yaml").read_text())
    assert policy["state_dir"] == str(data / "state")
    assert {str(root / "command-guard.sh"), str(data), str(root / "command-guard")} <= set(
        policy["protected_paths"]
    )
    assert (data / "config/service.env").read_text() == "TYPESAFE_API_KEY=test-secret\n"
    assert (data / "config/service.env").stat().st_mode & 0o777 == 0o600
    assert read_env(data / "config/compose.env")["GUARD_UID"] == "12345"
    assert (data / "state/audit.jsonl").read_text() == '{"event":"old"}\n'
    assert (data / ".gitignore").read_text() == "*\n"
    (data / "config/service.env").write_text("TYPESAFE_API_KEY=edited-secret\n")
    (data / "state/audit.jsonl").write_text('{"event":"new"}\n')
    initialize(*args, legacy_config=legacy, legacy_state=old_state, docker_gid=986)
    assert (data / "config/service.env").read_text() == "TYPESAFE_API_KEY=edited-secret\n"
    assert (data / "state/audit.jsonl").read_text() == '{"event":"new"}\n'
    assert (data / "legacy-backup/service.env").stat().st_mode & 0o777 == 0o600


def test_fresh_setup_uses_a_separate_nonroot_identity_without_host_accounts(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "chown", lambda *args: None)
    root = tmp_path / "repo"
    root.mkdir()
    template = tmp_path / "template.yaml"
    template.write_text("protected_paths: [/var/lib/docker]\nsensitive_paths: [/root]\n")
    data = root / ".command-guard"
    initialize(data, root, 60000, 60000, "worker", "gateway", template, docker_gid=986)
    values = read_env(data / "config/compose.env")
    assert int(values["GUARD_UID"]) not in (0, 60000)
    assert values["GUARD_AGENT_GID"] != values["GUARD_OPERATOR_GID"]
    assert (data / "config/service.env").stat().st_mode & 0o777 == 0o600
