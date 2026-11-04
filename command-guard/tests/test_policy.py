from dataclasses import replace

import pytest

from command_guard.models import Assessment, Command
from command_guard.policy import Policy


def test_only_confident_no_effects_are_automatic(policy, safe, tmp_path):
    request = Command("cat /etc/os-release", str(tmp_path))
    assert policy.reasons(request, safe) == []
    assert policy.reasons(replace(request, network=True), safe)
    assert policy.reasons(replace(request, write_paths=(str(tmp_path),)), safe)
    assert policy.reasons(request, Assessment({}, unavailable="offline"))
    changed = {k: dict(v) for k, v in safe.answers.items()}
    changed["file_changes"] = {"choice": "yes", "confidence": 1.0}
    assert policy.reasons(request, Assessment(changed))
    changed["file_changes"] = {"choice": "no", "confidence": 0.5}
    assert policy.reasons(request, Assessment(changed))


def test_protected_overlap_and_symlink_rejected(policy, tmp_path):
    with pytest.raises(ValueError):
        policy.validate(Command("true", str(tmp_path), write_paths=(str(tmp_path),)))
    link = tmp_path / "alias"
    link.symlink_to(policy.protected_paths[0])
    with pytest.raises(ValueError):
        Command.parse({"command": "true", "cwd": str(tmp_path), "write_paths": [str(link)]})
    with pytest.raises(ValueError):
        policy.validate(Command("true", str(tmp_path), read_paths=policy.protected_paths))


def test_replaced_symlink_target_is_rejected(policy, tmp_path):
    path = tmp_path / "writable"
    path.mkdir()
    request = Command.parse({"command": "true", "cwd": str(tmp_path), "write_paths": [str(path)]})
    path.rmdir()
    path.symlink_to(policy.protected_paths[0])
    with pytest.raises(ValueError):
        policy.validate(request)


def test_read_exception_must_be_sensitive(policy, tmp_path):
    with pytest.raises(ValueError):
        policy.validate(Command("true", str(tmp_path), read_paths=(str(tmp_path),)))
    policy.validate(Command("true", str(tmp_path), read_paths=policy.sensitive_paths))


@pytest.mark.parametrize(
    "data",
    [
        {"command": "true", "network": "false"},
        {"command": "true", "approved": True},
        {"command": ""},
        {"command": "true", "cwd": "relative"},
    ],
)
def test_request_types_and_approval_injection(data, tmp_path):
    with pytest.raises((ValueError, TypeError)):
        Command.parse({"cwd": str(tmp_path), **data})


def test_policy_globs_and_validation(tmp_path):
    secret = tmp_path / "user" / ".ssh"
    secret.mkdir(parents=True)
    path = tmp_path / "policy.yaml"
    path.write_text(f'protected_paths: ["/opt/guard"]\nsensitive_paths: ["{tmp_path}/*/.ssh"]\n')
    assert Policy.load(path).sensitive_paths == (str(secret),)
    path.write_text('protected_paths: []\nsensitive_paths: ["/root"]\n')
    with pytest.raises(ValueError):
        Policy.load(path)
