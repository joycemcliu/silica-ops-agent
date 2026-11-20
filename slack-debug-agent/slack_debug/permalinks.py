"""Resolve Slack file citations against locally known published Git history."""

import asyncio
import contextlib
import re
from pathlib import Path
from urllib.parse import quote, unquote

REFERENCE = re.compile(
    r"```[\s\S]*?```|`[^`\n]*`"
    r"|\[(?P<label>[^\[\]\n]+)\]\((?P<link>[^()\n]+)\)"
    r"|(?<![\w:/])(?P<bare>(?:\$HOME/|\$\{HOME\}/|~/|/)[^\s<>`\[\]()]+?:\d+(?:-\d+)?)(?![\w/:-])"
)
LOCATION = re.compile(r"(?P<path>.+?)(?:(?::|#L)(?P<start>[1-9]\d*)(?:-L?(?P<end>[1-9]\d*))?)?$")
GITHUB_ORIGIN = re.compile(
    r"(?:git@github\.com:|ssh://git@github\.com/|https://(?:[^/@]+@)?github\.com/)"
    r"([\w.-]+/[\w.-]+?)(?:\.git)?/?", re.ASCII,
)


async def git(root, *args):
    process = await asyncio.create_subprocess_exec(
        "git", "--literal-pathspecs", "-C", str(root), *args,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), 2)
    finally:
        if process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
            await process.wait()
    return stdout.decode(errors="replace").strip() if process.returncode == 0 else None


async def link_file_references(text, roots):
    """Keep citations in code literal and use relative labels for unpublished files."""
    toolkit = roots[0]
    roots = tuple(sorted(roots, key=lambda root: len(root.parts), reverse=True))
    origins = {}
    sources = {}

    async def source_url(root, relative):
        try:
            if root not in origins:
                remote = await git(root, "config", "--get", "remote.origin.url")
                origins[root] = GITHUB_ORIGIN.fullmatch(remote or "")
            origin = origins[root]
            if not origin:
                return None
            revision = await git(root, "log", "-1", "--format=%H", "HEAD", "--", relative)
            if not revision or await git(root, "cat-file", "-t", f"{revision}:{relative}") != "blob":
                return None
            if await git(root, "diff", "--quiet", "--no-ext-diff", "--no-textconv",
                         revision, "--", relative) is None:
                return None
            if await git(root, "for-each-ref", "--count=1", f"--contains={revision}",
                         "--format=%(refname)", "refs/remotes/origin/"):
                return f"https://github.com/{origin[1]}/blob/{revision}/{quote(relative)}"
        except (OSError, TimeoutError):
            pass
        return None

    async def replace(match):
        target = match["link"] or match["bare"]
        if not target:
            return match[0]
        if target.startswith("file:///"):
            target = target.removeprefix("file://")
        elif "://" in target:
            return match[0]
        location = LOCATION.fullmatch(unquote(target))
        if not location:
            return match[0]
        path = location["path"]
        path = re.sub(r"^\$(?:HOME|\{HOME\})/", "~/", path)
        try:
            absolute = (Path.home() / path[2:] if path.startswith("~/") else toolkit / path).resolve()
        except (OSError, RuntimeError, ValueError):
            return match[0]
        for root in roots:
            if absolute.is_relative_to(root) and absolute.is_file():
                relative = absolute.relative_to(root).as_posix()
                label = match["label"] or relative
                key = (root, relative)
                if key not in sources:
                    sources[key] = await source_url(root, relative)
                url = sources[key]
                start, end = location["start"], location["end"]
                if url:
                    fragment = f"#L{start}" if start else ""
                    if end:
                        fragment += f"-L{end}"
                    return f"[{label}]({url}{fragment})"
                location_label = relative + (f":{start}" if start else "")
                if end:
                    location_label += f"-{end}"
                return f"{label} (`{location_label}`)" if match["label"] else f"`{location_label}`"
        return match[0]

    parts = []
    position = 0
    for match in REFERENCE.finditer(text):
        parts.extend((text[position:match.start()], await replace(match)))
        position = match.end()
    parts.append(text[position:])
    return "".join(parts)
