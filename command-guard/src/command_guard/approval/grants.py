"""In-memory, expiring, atomically consumed approvals; restart invalidates everything."""

import secrets
import threading
import time


class Grants:
    def __init__(self, ttl, clock=time.monotonic):
        self.ttl, self.clock = ttl, clock
        self.records = {}
        self.lock = threading.Lock()

    def _prune(self):
        now = self.clock()
        self.records = {k: v for k, v in self.records.items() if v["deadline"] > now}

    def create(self, owner, command, assessment, reasons, policy_hash):
        with self.lock:
            self._prune()
            if len(self.records) >= 256:
                raise ValueError("Approval queue is full")
            identifier = secrets.token_hex(16)
            self.records[identifier] = {
                "id": identifier,
                "owner_uid": owner,
                "request": command,
                "assessment": assessment.payload(),
                "reasons": reasons,
                "policy_hash": policy_hash,
                "deadline": self.clock() + self.ttl,
                "approved": False,
            }
            return identifier

    def list(self):
        with self.lock:
            self._prune()
            return [self._public(v) for v in self.records.values()]

    def inspect(self, identifier):
        with self.lock:
            self._prune()
            return self._public(self.records[identifier])

    def _public(self, record):
        return {
            **{k: v for k, v in record.items() if k not in {"request", "deadline"}},
            "request": record["request"].payload(),
            "expires_in_seconds": max(0, int(record["deadline"] - self.clock())),
            "confidence_note": "Classification confidence, not a guarantee of safety",
            "capability_note": "Approval grants exactly the listed paths and network setting",
        }

    def decide(self, identifier, approve):
        with self.lock:
            self._prune()
            record = self.records[identifier]
            if record["approved"]:
                raise ValueError("Request is already approved")
            if approve:
                record["approved"] = True
            else:
                del self.records[identifier]
            return {"status": "approved" if approve else "declined", "id": identifier}

    def consume(self, identifier, owner, policy_hash):
        with self.lock:
            self._prune()
            record = self.records[identifier]
            if record["owner_uid"] != owner:
                raise ValueError("Approval belongs to a different submitting user")
            if record["policy_hash"] != policy_hash:
                raise ValueError("Policy changed; resubmit")
            if not record["approved"]:
                return None
            del self.records[identifier]
            return record["request"]
