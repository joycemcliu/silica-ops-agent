"""Trusted approval UI uses JSON escaping to neutralize terminal control characters."""

import json


def render(record):
    return json.dumps(record, indent=2, ensure_ascii=True)
