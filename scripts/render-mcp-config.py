"""Render the shared MCP server registry (config/mcp-servers.toml) for Codex or Hermes.

Usage: render-mcp-config.py {codex,hermes} [--registry PATH]
Prints only the MCP server section; merge it into the runtime's config yourself.
"""

import argparse
import json
import os
from pathlib import Path
import re
import sys
import tomllib


REPO = Path(__file__).resolve().parents[1]
PLACEHOLDER = re.compile(r"\{(repo|home|env:[A-Za-z_][A-Za-z0-9_]*)\}")


def expand(value):
    """Return the expanded string, or None when an {env:NAME} variable is unset."""
    missing = False

    def sub(match):
        nonlocal missing
        key = match[1]
        if key == "repo":
            return str(REPO)
        if key == "home":
            return str(Path.home())
        found = os.environ.get(key[4:])
        missing = missing or found is None
        return found or ""

    result = PLACEHOLDER.sub(sub, value)
    return None if missing else result


def resolve(server):
    env = {k: v for k, v in ((k, expand(v)) for k, v in server.get("env", {}).items()) if v is not None}
    return {
        "type": server["type"],
        "url": server.get("url"),
        "host_header": server.get("host_header"),
        "bearer_env": server.get("bearer_token_env"),
        "bearer_file": expand(server["bearer_token_file"]) if "bearer_token_file" in server else None,
        "command": expand(server["command"]) if "command" in server else None,
        "args": [expand(a) for a in server.get("args", [])],
        "env": env,
        "approve": server.get("codex_approve_tools", []),
        "approval_mode": server.get("codex_default_tools_approval_mode"),
    }


def toml_str(value):
    return json.dumps(value)


def render_codex(servers):
    out = []
    for name, s in servers.items():
        out.append(f"[mcp_servers.{name}]")
        if s["type"] == "http":
            out.append(f"url = {toml_str(s['url'])}")
            if s["host_header"]:
                out.append(f"http_headers = {{ Host = {toml_str(s['host_header'])} }}")
            if s["bearer_file"]:
                helper = f"{REPO}/scripts/mcp-bearer-header.sh {s['bearer_file']}"
                out.append(f"http_headers_helper = {toml_str(helper)}")
            elif s["bearer_env"]:
                out.append(f"bearer_token_env_var = {toml_str(s['bearer_env'])}")
        else:
            out.append(f"command = {toml_str(s['command'])}")
            out.append("args = [" + ", ".join(toml_str(a) for a in s["args"]) + "]")
            if s["env"]:
                pairs = ", ".join(f"{k} = {toml_str(v)}" for k, v in s["env"].items())
                out.append(f"env = {{ {pairs} }}")
        out.append("enabled = true")
        if s["approval_mode"]:
            out.append(f"default_tools_approval_mode = {toml_str(s['approval_mode'])}")
        out.append("")
        for tool in s["approve"]:
            out += [f"[mcp_servers.{name}.tools.{tool}]", 'approval_mode = "approve"', ""]
    return "\n".join(out)


def render_hermes(servers):
    out = ["mcp_servers:"]
    for name, s in servers.items():
        out.append(f"  {name}:")
        if s["type"] == "http":
            out.append(f"    url: {json.dumps(s['url'])}")
            headers = {}
            if s["host_header"]:
                headers["Host"] = s["host_header"]
            if s["bearer_env"]:
                headers["Authorization"] = "Bearer ${" + s["bearer_env"] + "}"
            if headers:
                out.append("    headers:")
                out += [f"      {k}: {json.dumps(v)}" for k, v in headers.items()]
        else:
            out.append(f"    command: {json.dumps(s['command'])}")
            out.append(f"    args: {json.dumps(s['args'])}")
            if s["env"]:
                out.append("    env:")
                out += [f"      {k}: {json.dumps(v)}" for k, v in s["env"].items()]
    return "\n".join(out)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("target", choices=["codex", "hermes"])
    parser.add_argument("--registry", type=Path, default=REPO / "config" / "mcp-servers.toml")
    args = parser.parse_args(argv)
    registry = tomllib.loads(args.registry.read_text())
    servers = {name: resolve(s) for name, s in registry["servers"].items()}
    print((render_codex if args.target == "codex" else render_hermes)(servers))


if __name__ == "__main__":
    sys.exit(main())
