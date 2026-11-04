"""Read host filesystem metadata through a mounted root without following image symlinks."""

import fnmatch
import glob
import os
from collections import deque
from pathlib import Path, PurePosixPath


class HostFS:
    def __init__(self, root="/"):
        self.root = Path(root)
        if not self.root.is_absolute() or not self.root.is_dir():
            raise ValueError("host_root must be an existing absolute directory")

    def path(self, host_path):
        value = PurePosixPath(host_path)
        if not value.is_absolute() or ".." in value.parts:
            raise ValueError("Expected an absolute normalized host path")
        return self.root.joinpath(*value.parts[1:])

    def canonical(self, host_path, *, strict=True):
        """Resolve absolute and relative symlink targets within the HOST root.

        Path.resolve() on /hostfs/etc/link would incorrectly follow an absolute
        target against the broker image. Resolve each link in host coordinates.
        """
        value = PurePosixPath(host_path)
        if not value.is_absolute():
            raise ValueError("Host path must be absolute")
        pending, resolved, links = deque(value.parts[1:]), [], 0
        while pending:
            part = pending.popleft()
            if part in {"", "."}:
                continue
            if part == "..":
                if resolved:
                    resolved.pop()
                continue
            candidate = self.root.joinpath(*resolved, part)
            try:
                candidate.lstat()
            except FileNotFoundError:
                if strict:
                    raise
                resolved.append(part)
                continue
            if candidate.is_symlink():
                links += 1
                if links > 40:
                    raise ValueError("Too many host symlinks")
                target = PurePosixPath(os.readlink(candidate))
                if target.is_absolute():
                    resolved.clear()
                    parts = target.parts[1:]
                else:
                    parts = target.parts
                pending.extendleft(reversed(parts))
            else:
                resolved.append(part)
        return "/" + "/".join(resolved)

    def glob(self, pattern):
        """Expand component globs using host-root-aware traversal (no recursive **)."""
        candidates = ["/"]
        for component in PurePosixPath(pattern).parts[1:]:
            expanded = []
            for parent in candidates:
                if glob.has_magic(component):
                    physical = self.path(self.canonical(parent))
                    try:
                        names = [entry.name for entry in physical.iterdir()]
                    except (FileNotFoundError, NotADirectoryError, PermissionError):
                        continue
                    names = [
                        name
                        for name in names
                        if not name.startswith(".") or component.startswith(".")
                    ]
                    expanded.extend(
                        str(PurePosixPath(parent) / name)
                        for name in names
                        if fnmatch.fnmatchcase(name, component)
                    )
                else:
                    candidate = str(PurePosixPath(parent) / component)
                    try:
                        self.canonical(candidate)
                    except (FileNotFoundError, NotADirectoryError, PermissionError):
                        continue
                    expanded.append(candidate)
            candidates = expanded
        return candidates
