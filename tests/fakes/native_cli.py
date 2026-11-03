#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys
import time


home = Path(os.environ["HOME"])
state = json.loads((home / "fake-state.json").read_text())
binary = Path(sys.argv[0]).name
with (home / "calls.jsonl").open("a") as calls:
    calls.write(json.dumps({"binary": binary, "args": sys.argv[1:], "environment_keys": list(os.environ)}) + "\n")

if binary == "kubectl":
    (home / "forward.pid").write_text(str(os.getpid()))
    if state.get("forward_fail"):
        sys.exit(1)
    if not state.get("forward_hang"):
        print("Forwarding from 127.0.0.1:43210 -> 22", flush=True)
    time.sleep(120)
elif binary == "ssh-keyscan":
    print("[127.0.0.1]:43210 ssh-ed25519 synthetic-key")
elif binary == "ssh-keygen":
    print("256 " + state["fingerprint"] + " test-key (ED25519)")
elif binary == "sshpass":
    if state.get("ssh_hang"):
        time.sleep(120)
    if state.get("ssh_flood"):
        while True:
            print("diagnostic evidence " * 1000, flush=True)
    if state.get("echo_password"):
        print(os.environ["SSHPASS"])
    sys.stdout.write(state.get("stdout", "seeded service failure\n"))
    sys.stderr.write(state.get("stderr", ""))
    sys.exit(state.get("ssh_status", 0))
