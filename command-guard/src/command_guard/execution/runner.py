"""One request per Docker container, with bounded output and guaranteed removal."""

import json
import os
import re
import selectors
import subprocess
import tempfile
import time
import uuid
from dataclasses import replace
from pathlib import Path

from ..models import digest
from .sandbox import build, seccomp_profile


class Runner:
    def __init__(self, policy):
        self.policy = policy

    def _docker(self, *args, timeout=15):
        return subprocess.run(
            [self.policy.docker, "--host", "unix:///var/run/docker.sock", *args],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=timeout,
            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
        )

    def cleanup(self):
        label = "io.commandguard.instance=" + digest(self.policy.state_dir)[:16]
        result = self._docker("ps", "-aq", "--no-trunc", "--filter", "label=" + label)
        if result.returncode:
            raise RuntimeError("Docker cleanup could not list this gateway's containers")
        identifiers = result.stdout.decode().split()
        if not all(re.fullmatch(r"[0-9a-f]{64}", value) for value in identifiers):
            raise RuntimeError("Docker returned invalid container identifiers")
        if identifiers and self._docker("rm", "--force", *identifiers).returncode:
            raise RuntimeError("Could not remove this gateway's containers")

    def run(self, request):
        if not Path(self.policy.docker).is_file():
            raise RuntimeError("Docker CLI is unavailable; execution was not attempted")
        info = self._docker("info", "--format", "{{.DockerRootDir}}")
        root = info.stdout.decode().strip()
        if info.returncode or not root.startswith("/"):
            raise RuntimeError("Docker daemon is unavailable")
        policy = replace(self.policy, protected_paths=(*self.policy.protected_paths, root))
        policy.validate(request)
        name = "command-guard-" + uuid.uuid4().hex
        Path(policy.state_dir).mkdir(parents=True, exist_ok=True, mode=0o700)
        with tempfile.TemporaryDirectory(prefix="execution-", dir=policy.state_dir) as directory:
            profile = Path(directory) / "seccomp.json"
            profile.write_text(json.dumps(seccomp_profile(request.network)))
            profile.chmod(0o600)
            created = False
            try:
                args = build(policy, request, name, str(profile), os.getuid(), os.getgid())
                result = subprocess.run(
                    args,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    timeout=15,
                    env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
                )
                if result.returncode:
                    raise RuntimeError(
                        "Docker container setup failed: "
                        + result.stderr.decode(errors="replace")[:1000]
                    )
                created = True
                return self._start(name)
            finally:
                removed = self._docker("rm", "--force", name)
                if removed.returncode and created:
                    raise RuntimeError("Docker cleanup failed; inspect container " + name)

    def _start(self, name):
        process = subprocess.Popen(
            [
                self.policy.docker,
                "--host",
                "unix:///var/run/docker.sock",
                "start",
                "--attach",
                name,
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"},
        )
        output = {"stdout": bytearray(), "stderr": bytearray()}
        deadline, timed_out, truncated = time.monotonic() + self.policy.timeout, False, False
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ, "stdout")
                selector.register(process.stderr, selectors.EVENT_READ, "stderr")
                while selector.get_map():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        timed_out = True
                        self._docker("kill", name)
                        break
                    for key, _ in selector.select(min(remaining, 0.25)):
                        chunk = os.read(key.fileobj.fileno(), 65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                        else:
                            buffer = output[key.data]
                            available = 1048576 - len(buffer)
                            buffer.extend(chunk[:available])
                            truncated |= len(chunk) > available
            process.wait(timeout=5)
            inspected = self._docker("inspect", "--format", "{{.State.ExitCode}}", name)
            code = int(inspected.stdout) if inspected.returncode == 0 else process.returncode
            return {
                "status": "finished",
                "exit_code": 124 if timed_out else code,
                "timed_out": timed_out,
                "output_truncated": truncated,
                **{key: value.decode(errors="replace") for key, value in output.items()},
            }
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
            process.stdout.close()
            process.stderr.close()
