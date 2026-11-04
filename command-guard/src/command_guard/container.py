"""Docker broker entrypoint: exclusive state lock, stale-socket recovery, and readiness probe."""

import fcntl
import os
import sys
from pathlib import Path

from .cli import exchange
from .policy import Policy


def main():
    if sys.argv[1:] == ["health"]:
        try:
            result = exchange("/run/command-guard/agent.sock", {"action": "health"})
        except (OSError, ValueError):
            raise SystemExit(1) from None
        raise SystemExit(0 if result.get("status") == "ready" else 1)
    os.umask(0o077)
    policy_file = sys.argv[sys.argv.index("--policy") + 1]
    state_dir = Path(Policy.load(policy_file).state_dir)
    lock = open(state_dir / "gateway.lock", "a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    os.set_inheritable(lock.fileno(), True)
    for name in ("agent.sock", "operator.sock"):
        path = Path("/run/command-guard") / name
        if path.exists():
            if not path.is_socket() or path.stat().st_uid != os.getuid():
                raise RuntimeError("Refusing to replace an unexpected gateway socket path")
            path.unlink()
    os.execvp("command-guard", ["command-guard", *sys.argv[1:]])


if __name__ == "__main__":
    main()
