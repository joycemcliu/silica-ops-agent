"""Audit metadata only: never persist raw commands, output, credentials, or file contents."""

import datetime
import json
import threading


class Audit:
    def __init__(self, path):
        self.path = path
        self.lock = threading.Lock()

    def record(self, event, **metadata):
        row = {"time": datetime.datetime.now(datetime.UTC).isoformat(), "event": event, **metadata}
        with self.lock, open(self.path, "a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
