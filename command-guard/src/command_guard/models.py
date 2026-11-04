"""Immutable request and assessment types."""

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path

from .hostfs import HostFS


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class Command:
    command: str
    cwd: str
    write_paths: tuple[str, ...] = ()
    read_paths: tuple[str, ...] = ()
    network: bool = False

    @classmethod
    def parse(cls, data, host_root="/"):
        fs = HostFS(host_root)
        if not isinstance(data, dict):
            raise ValueError("Command request must be an object")
        if set(data) - {"command", "cwd", "write_paths", "read_paths", "network"}:
            raise ValueError("Unknown command fields")
        command = data.get("command")
        if not isinstance(command, str) or not command.strip() or "\0" in command:
            raise ValueError("A nonempty command is required")
        if len(command.encode()) > 16000:
            raise ValueError("Command exceeds 16000 bytes")
        cwd = data.get("cwd")
        if not isinstance(cwd, str) or not Path(cwd).is_absolute():
            raise ValueError("cwd must be absolute")
        cwd = fs.canonical(cwd)
        if not fs.path(cwd).is_dir():
            raise ValueError("cwd must be a directory")
        paths = {}
        for key in ("write_paths", "read_paths"):
            values = data.get(key, [])
            if not isinstance(values, list) or len(values) > 32:
                raise ValueError(f"{key} must be a list of at most 32 existing paths")
            normalized = []
            for value in values:
                if not isinstance(value, str) or not Path(value).is_absolute():
                    raise ValueError(f"{key} must contain absolute paths")
                resolved = fs.canonical(value)
                if resolved != value:
                    raise ValueError("Capability paths must be canonical, without symlinks or ..")
                normalized.append(resolved)
            paths[key] = tuple(sorted(set(normalized)))
        network = data.get("network", False)
        if type(network) is not bool:
            raise ValueError("network must be boolean")
        return cls(command, cwd, network=network, **paths)

    def payload(self):
        return asdict(self)


@dataclass(frozen=True)
class Assessment:
    answers: dict
    model: str | None = None
    unavailable: str | None = None

    @classmethod
    def parse(cls, response, expected):
        if not isinstance(response.get("model"), str) or not response["model"]:
            raise ValueError("Invalid assessment model")
        answers = response["answers"]
        if set(answers) != set(expected):
            raise ValueError("Missing or unexpected assessment answers")
        for answer in answers.values():
            if answer.get("type") != "choice" or answer.get("choice") not in {
                "yes",
                "no",
                "unknown",
            }:
                raise ValueError("Invalid assessment choice")
            probabilities = answer.get("probabilities", {})
            if set(probabilities) != {"yes", "no", "unknown"}:
                raise ValueError("Invalid probability keys")
            for value in [answer.get("confidence"), *probabilities.values()]:
                if (
                    type(value) not in (int, float)
                    or not math.isfinite(value)
                    or not 0 <= value <= 1
                ):
                    raise ValueError("Invalid probability/confidence")
            if abs(sum(probabilities.values()) - 1) > 0.001:
                raise ValueError("Probabilities must sum to one")
            if probabilities[answer["choice"]] != max(probabilities.values()):
                raise ValueError("Choice contradicts probabilities")
            calculated = (max(probabilities.values()) - 1 / 3) / (1 - 1 / 3)
            if abs(calculated - answer["confidence"]) > 0.01:
                raise ValueError("Confidence contradicts probabilities")
        return cls(answers, response["model"])

    def payload(self):
        return asdict(self)
