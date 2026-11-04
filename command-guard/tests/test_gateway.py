from unittest.mock import Mock

import pytest

from command_guard.gateway import Gateway
from command_guard.models import Assessment


def gateway(policy, assessment):
    assessor = Mock()
    assessor.assess.return_value = assessment
    runner = Mock()
    runner.run.return_value = {"status": "finished", "exit_code": 0, "timed_out": False}
    return Gateway(policy, assessor, runner, Mock())


def test_automatic_read_only(policy, safe, tmp_path):
    guard = gateway(policy, safe)
    assert guard.submit(100, {"command": "pwd", "cwd": str(tmp_path)})["status"] == "finished"
    guard.runner.run.assert_called_once()


def test_offline_pauses_then_runs_exact_original_request(policy, tmp_path):
    guard = gateway(policy, Assessment({}, unavailable="no key"))
    result = guard.submit(100, {"command": "echo hello", "cwd": str(tmp_path)})
    assert result["status"] == "pending_approval"
    assert guard.resume(100, result["id"])["status"] == "pending_approval"
    guard.runner.run.assert_not_called()
    guard.decide(200, result["id"], True)
    assert guard.resume(100, result["id"])["status"] == "finished"
    assert guard.runner.run.call_args.args[0].command == "echo hello"
    with pytest.raises(KeyError):
        guard.resume(100, result["id"])


def test_decline_does_not_execute(policy, tmp_path):
    guard = gateway(policy, Assessment({}, unavailable="offline"))
    result = guard.submit(100, {"command": "true", "cwd": str(tmp_path)})
    guard.decide(200, result["id"], False)
    with pytest.raises(KeyError):
        guard.resume(100, result["id"])
    guard.runner.run.assert_not_called()
