"""Bounded HTTPS call to the documented TypeSafe System One API."""

import json
import os
import urllib.request

from ..models import Assessment
from .questions import questions


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Jev:
    def __init__(self, policy):
        self.policy = policy

    def assess(self, command):
        key = os.environ.get("TYPESAFE_API_KEY")
        if not key:
            return Assessment({}, unavailable="TYPESAFE_API_KEY is not configured")
        query = questions()
        state = {
            "request": command.payload(),
            "execution": (
                "Fresh Docker container running /bin/sh -c; host files appear under /host. "
                "The request cwd and capability paths are host paths, mapped under /host. "
                "Image filesystem is read-only; no ambient service credentials."
            ),
            "policy": {
                "protected_paths": self.policy.protected_paths,
                "sensitive_paths": self.policy.sensitive_paths,
            },
            "script_contents": "Not supplied; never assume referenced scripts are read-only",
        }
        request = urllib.request.Request(
            "https://api.typesafe.ai/v1/systemone",
            data=json.dumps(
                {"model": self.policy.model, "state": state, "questions": query}
            ).encode(),
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            # Ignore ambient proxy configuration; never redirect the credential-bearing request.
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
            with opener.open(request, timeout=10) as response:
                raw = response.read(262145)
            if len(raw) > 262144:
                raise ValueError("Oversized assessment response")
            return Assessment.parse(json.loads(raw), query)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            # Do not expose HTTP response bodies, API keys, or command text in error logs.
            return Assessment({}, unavailable="TypeSafe request failed or response was invalid")
