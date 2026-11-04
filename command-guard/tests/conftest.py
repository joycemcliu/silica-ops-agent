import pytest

from command_guard.models import Assessment
from command_guard.policy import Policy


@pytest.fixture
def policy(tmp_path):
    protected = tmp_path / "protected"
    sensitive = tmp_path / "secret"
    protected.mkdir()
    sensitive.mkdir()
    return Policy((str(protected),), (str(sensitive),), read_only_roots=(str(tmp_path),))


@pytest.fixture
def safe():
    return Assessment("read-only-command")
