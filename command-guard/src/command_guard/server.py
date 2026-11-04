"""Two Unix sockets, with separate groups and SO_PEERCRED identity checks."""

import json
import os
import socket
import socketserver
import struct
import threading
from pathlib import Path

MAX_MESSAGE = 65536


class Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    block_on_close = False
    request_queue_size = 16

    def __init__(self, path, gateway, operator, gid):
        self.gateway, self.operator = gateway, operator
        self.slots = threading.BoundedSemaphore(8)
        parent = Path(path).parent
        if not parent.is_dir() or parent.stat().st_mode & 0o022:
            raise ValueError("Socket directory must exist and must not be group/world writable")
        if Path(path).exists():
            raise ValueError(f"Socket already exists: {path}; remove stale sockets explicitly")
        super().__init__(path, Handler)
        os.chown(path, -1, gid)
        os.chmod(path, 0o660)

    def process_request(self, request, client_address):
        if not self.slots.acquire(blocking=False):
            request.close()
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.request.settimeout(70)
        uid = struct.unpack(
            "3i", self.request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
        )[1]
        try:
            raw = self.rfile.readline(MAX_MESSAGE + 1)
            if len(raw) > MAX_MESSAGE or not raw.endswith(b"\n"):
                raise ValueError("Invalid request size/framing")
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError("Request must be an object")
            action = data["action"]
            gateway = self.server.gateway
            if action == "health" and set(data) == {"action"}:
                result = {"status": "ready"}
            elif self.server.operator:
                if action == "list" and set(data) == {"action"}:
                    result = {"requests": gateway.grants.list()}
                elif action == "inspect" and set(data) == {"action", "id"}:
                    result = gateway.grants.inspect(data["id"])
                elif action in {"approve", "decline"} and set(data) == {"action", "id"}:
                    result = gateway.decide(uid, data["id"], action == "approve")
                else:
                    raise ValueError("Operator socket accepts list, approve, decline only")
            elif action == "submit" and set(data) == {"action", "request"}:
                result = gateway.submit(uid, data["request"])
            elif action == "resume" and set(data) == {"action", "id"}:
                result = gateway.resume(uid, data["id"])
            else:
                raise ValueError("Agent socket accepts submit and resume only")
        except (ValueError, KeyError, TypeError, OSError, RuntimeError):
            # Details are intentionally absent; avoid disclosing protected filesystem metadata.
            result = {
                "status": "error",
                "message": "Request invalid, expired, or execution unavailable",
            }
        self.wfile.write(json.dumps(result, ensure_ascii=True).encode() + b"\n")
