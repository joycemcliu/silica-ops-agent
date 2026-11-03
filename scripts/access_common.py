import os
import re
import selectors
import signal
import subprocess
import time


class AccessError(Exception):
    pass


def redact(output, secrets=()):
    text = output.decode("utf-8", errors="replace") if isinstance(output, bytes) else output
    for secret in sorted(set(secrets), key=len, reverse=True):
        if secret:
            text = text.replace(secret, "[REDACTED]")
    text = re.sub(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(?:-----END [A-Z ]*PRIVATE KEY-----|$)",
        "[REDACTED PRIVATE KEY]", text, flags=re.DOTALL,
    )
    text = re.sub(
        r"(?i)\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis|https?)://[^\s<>\"']+",
        "[REDACTED URL]", text,
    )
    text = re.sub(
        r"(?i)(\b(?:authorization|proxy-authorization)\s*[:=]\s*)(?:bearer|basic)\s+[^\s,;\"']+",
        r"\1[REDACTED]", text,
    )
    text = re.sub(
        r"(?i)([\"']?\b(?:password|passwd|pwd|[\w-]*token|[\w-]*secret|api[_-]?key)"
        r"[\"']?\s*[:=]\s*)(?:\"[^\"]*(?:\"|$)|'[^']*(?:'|$)|[^\s,;}]+)",
        r"\1[REDACTED]", text,
    )
    return text


def child_environment(kubernetes=False):
    names = ["PATH", "HOME", "LANG", "LC_ALL"]
    if kubernetes:
        names += ["KUBECONFIG", "GOOGLE_APPLICATION_CREDENTIALS"]
    return {name: os.environ[name] for name in names if name in os.environ}


def stop_process(process):
    if process is None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    process.wait()
    if process.stdout:
        process.stdout.close()


def capture(process, timeout, limit):
    deadline = time.monotonic() + timeout
    captured = bytearray()
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return bytes(captured), 124
            ready = selector.select(min(remaining, 0.1))
            if not ready:
                continue
            chunk = os.read(process.stdout.fileno(), min(8192, limit + 1 - len(captured)))
            if not chunk:
                try:
                    return bytes(captured), process.wait(timeout=max(0.01, remaining))
                except subprocess.TimeoutExpired:
                    return bytes(captured), 124
            captured.extend(chunk)
            if len(captured) > limit:
                return bytes(captured[:limit]), 125


def bounded_integer(name, default, minimum, maximum):
    value = os.environ.get(name, str(default))
    if not value.isascii() or not value.isdigit() or not minimum <= int(value) <= maximum:
        raise AccessError("Invalid execution limit.")
    return int(value)
