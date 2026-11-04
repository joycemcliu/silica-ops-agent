"""The gateway never accepts an approval flag from the submitter."""

import threading

from .approval.grants import Grants
from .models import Command, digest


class Gateway:
    def __init__(self, policy, assessor, runner, audit):
        self.policy, self.assessor, self.runner, self.audit = policy, assessor, runner, audit
        self.grants = Grants(policy.approval_ttl)
        self.execution_lock = threading.Lock()

    def submit(self, uid, data):
        request = Command.parse(data, host_root=self.policy.host_root)
        self.policy.validate(request)
        assessment = self.assessor.assess(request)
        reasons = self.policy.reasons(request, assessment)
        self.audit.record(
            "assessed",
            uid=uid,
            request_hash=digest(request.payload()),
            needs_approval=bool(reasons),
            model=assessment.model,
        )
        if reasons:
            identifier = self.grants.create(
                uid, request, assessment, reasons, self.policy.fingerprint()
            )
            return {
                "status": "pending_approval",
                "id": identifier,
                "request": request.payload(),
                "assessment": assessment.payload(),
                "reasons": reasons,
                "expires_in_seconds": self.policy.approval_ttl,
                "next_step": "Ask the user to review this ID on the operator socket",
                "confidence_note": "Classification confidence, not a guarantee of safety",
                "capability_note": "Approval grants exactly the listed paths and network setting",
            }
        return self.execute(uid, request)

    def execute(self, uid, request):
        with self.execution_lock:
            self.policy.validate(request)
            self.audit.record("execution_started", uid=uid, request_hash=digest(request.payload()))
            result = self.runner.run(request)
            self.audit.record(
                "execution_finished",
                uid=uid,
                exit_code=result["exit_code"],
                timed_out=result["timed_out"],
            )
            return result

    def resume(self, uid, identifier):
        request = self.grants.consume(identifier, uid, self.policy.fingerprint())
        if request is None:
            return {"status": "pending_approval", "id": identifier}
        return self.execute(uid, request)

    def decide(self, uid, identifier, approve):
        self.audit.record("approval_decision", operator_uid=uid, id=identifier, approve=approve)
        return self.grants.decide(identifier, approve)
