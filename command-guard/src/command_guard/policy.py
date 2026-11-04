"""Administrator-owned policy and capability validation."""

import glob
from dataclasses import dataclass
from pathlib import Path

import yaml

from .hostfs import HostFS
from .models import digest


def within(path, parent):
    return Path(path).is_relative_to(Path(parent))


def overlap(a, b):
    return within(a, b) or within(b, a)


@dataclass(frozen=True)
class Policy:
    protected_paths: tuple[str, ...]
    sensitive_paths: tuple[str, ...]
    confidence_threshold: float = 0.95
    approval_ttl: int = 300
    timeout: int = 30
    model: str = "jev-latest"
    docker: str = "/usr/bin/docker"
    docker_image: str = (
        "python@sha256:b18b261e1b4974b4f321451ad5251ded85abb22c2b8b262da527dda1d031ab30"
    )
    state_dir: str = "/var/lib/command-guard"
    host_root: str = "/"

    @classmethod
    def load(cls, filename):
        data = yaml.safe_load(Path(filename).read_text())
        if not isinstance(data, dict):
            raise ValueError("Policy must be a mapping")
        allowed = set(cls.__dataclass_fields__)
        if set(data) - allowed:
            raise ValueError("Unknown policy fields")
        fs = HostFS(data.get("host_root", "/"))
        for key in ("protected_paths", "sensitive_paths"):
            values = data.get(key)
            if not isinstance(values, list) or not values:
                raise ValueError(f"{key} must be a nonempty list")
            expanded = []
            for value in values:
                if not isinstance(value, str) or not Path(value).is_absolute():
                    raise ValueError("Policy paths must be absolute")
                matches = fs.glob(value)
                if glob.has_magic(value) and not matches:
                    continue
                expanded.extend(fs.canonical(p, strict=False) for p in matches or [value])
            data[key] = tuple(sorted(set(expanded)))
        policy = cls(**data)
        if type(policy.confidence_threshold) not in (float, int) or not (
            0.5 <= policy.confidence_threshold <= 1
        ):
            raise ValueError("confidence_threshold must be between 0.5 and 1")
        for key in ("timeout", "approval_ttl"):
            if type(getattr(policy, key)) is not int or not 1 <= getattr(policy, key) <= 3600:
                raise ValueError(f"{key} must be between 1 and 3600 seconds")
        if not Path(policy.docker).is_absolute() or not Path(policy.state_dir).is_absolute():
            raise ValueError("docker and state_dir must be absolute")
        if (
            not isinstance(policy.docker_image, str)
            or not policy.docker_image
            or policy.docker_image.startswith("-")
        ):
            raise ValueError("docker_image must name a trusted local image")
        return policy

    def fingerprint(self):
        return digest(self.__dict__)

    def validate(self, request):
        fs = HostFS(self.host_root)
        # System mounts and the gateway itself cannot be exposed through approval.
        reserved = ("/proc", "/sys", "/dev", "/run", "/tmp", self.state_dir, *self.protected_paths)
        for path in (*request.write_paths, *request.read_paths):
            if fs.canonical(path) != path:
                raise ValueError("Capability target changed; resubmit the command")
            if any(overlap(path, p) for p in reserved):
                raise ValueError("Capability overlaps gateway or sandbox system paths")
            if not (fs.path(path).is_file() or fs.path(path).is_dir()):
                raise ValueError("Only regular files and directories can be granted")
        for path in request.read_paths:
            if not any(within(path, p) for p in self.sensitive_paths):
                raise ValueError("Read exceptions must be inside a sensitive exclusion")
        if any(within(request.cwd, p) for p in (*self.protected_paths, "/proc", "/sys", "/dev")):
            raise ValueError("Working directory is protected")

    def reasons(self, request, assessment):
        reasons = []
        if request.write_paths:
            reasons.append("Host file write access requested")
        if request.read_paths:
            reasons.append("Sensitive file read access requested")
        if request.network:
            reasons.append("Network access: may transfer data or modify remote systems")
        if assessment.unavailable:
            reasons.append("Jev assessment unavailable; classification confidence unavailable")
        else:
            for name, answer in assessment.answers.items():
                if answer["choice"] != "no" or answer["confidence"] < self.confidence_threshold:
                    reasons.append(
                        f"{name}: {answer['choice']} ({answer['confidence']:.1%} confidence)"
                    )
        return reasons
