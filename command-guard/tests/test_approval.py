import concurrent.futures

import pytest

from command_guard.approval.grants import Grants
from command_guard.approval.requests import render
from command_guard.models import Command


def test_approval_is_single_use_owner_bound_and_expiring(safe):
    now = [0]
    grants = Grants(10, lambda: now[0])
    request = Command("echo hello", "/")
    identifier = grants.create(100, request, safe, ["test"], "policy")
    assert grants.consume(identifier, 100, "policy") is None
    grants.decide(identifier, True)
    with pytest.raises(ValueError):
        grants.consume(identifier, 101, "policy")
    with pytest.raises(ValueError):
        grants.consume(identifier, 100, "changed-policy")
    assert grants.consume(identifier, 100, "policy") == request
    with pytest.raises(KeyError):
        grants.consume(identifier, 100, "policy")
    expired = grants.create(100, request, safe, [], "policy")
    grants.decide(expired, True)
    now[0] = 11
    with pytest.raises(KeyError):
        grants.consume(expired, 100, "policy")


def test_concurrent_replay_executes_once(safe):
    grants = Grants(300)
    identifier = grants.create(100, Command("true", "/"), safe, [], "p")
    grants.decide(identifier, True)

    def consume():
        try:
            return grants.consume(identifier, 100, "p") is not None
        except KeyError:
            return False

    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        assert sum(pool.map(lambda _: consume(), range(20))) == 1


def test_display_escapes_terminal_control_sequences():
    assert "\x1b" not in render({"command": "echo \x1b[2J"})
    assert "\\u001b" in render({"command": "echo \x1b[2J"})
