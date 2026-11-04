import pytest

from command_guard.assessment.rules import Rules
from command_guard.models import Command


@pytest.mark.parametrize(
    "command", ["pwd", "ls -la", "cat -- report.txt", "head -n 10 log", "printf 'hello\\n'"]
)
def test_simple_reads_are_automatic(command):
    assert not Rules().assess(Command(command, "/")).reasons


@pytest.mark.parametrize(
    "command",
    [
        "find . -delete",
        "find . -exec sh -c id +",
        "rg --pre python x",
        "git status",
        "python -c 'print(1)'",
        "sh -c pwd",
        "/usr/bin/ls",
        "FOO=bar ls",
        "cat x > y",
        "ls | cat",
        "pwd; id",
        "cat $(id)",
        "cat `id`",
        "ls\nid",
        "cat *.txt",
        "printf '%s' \"$HOME\"",
        "cat 'unterminated",
        "source script.sh",
    ],
)
def test_unknown_and_shell_expressions_require_approval(command):
    result = Rules().assess(Command(command, "/"))
    assert result.reasons
    assert "confidence" not in result.payload()
