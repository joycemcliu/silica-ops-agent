"""Conservative single-command allowlist; Docker enforces actual access."""

import shlex

from ..models import Assessment

# These tools have no command-execution or file-write options. Other tools and
# shell expressions require approval rather than attempting a full shell parser.
READ_COMMANDS = frozenset(
    {"cat", "head", "tail", "wc", "ls", "stat", "readlink", "pwd", "true", "false", "printf"}
)


class Rules:
    def assess(self, request):
        if any(c in request.command for c in "$`\n\r;|&<>(){}*?[]~"):
            return Assessment(
                "shell-expression",
                ("Shell expressions, expansions or compound commands require approval",),
            )
        try:
            words = shlex.split(request.command, comments=False, posix=True)
        except ValueError:
            return Assessment("invalid-shell", ("Cannot parse command; review required",))
        if not words or words[0] not in READ_COMMANDS:
            return Assessment(
                "unrecognized-command", ("Command is outside the read-only allowlist",)
            )
        return Assessment("read-only-command")
