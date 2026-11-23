#!/usr/bin/env python3
"""List nodes registered in a store's Consul catalog."""

import argparse
import json
import re
import sys
from ipaddress import ip_address
from urllib.parse import urlsplit
from urllib.request import urlopen


# Match hostname components so r4-video gets the more specific renderer role.
ROLE_HINTS = (
    (r"master[0-9]*", "Linux infrastructure"),
    (r"video[0-9]*", "Windows video renderer"),
    (r"exp[0-9]*", "Windows Unity/Photon server"),
    (r"mocap[0-9]*", "Windows PC (usually runs a motion capture server)"),
    (r"webcam[0-9]*", "Linux webcam PC"),
    (r"pi[0-9]*", "Linux PC"),
    (r"spc[a-z0-9-]+[1-6]", "Windows Unity player PC"),
    (r"[rh][0-9][a-z0-9]*", "Room/holodeck PC"),
)


def role_hint(name):
    for pattern, role in ROLE_HINTS:
        if re.search(rf"(?:^|[-_.]){pattern}(?:$|[-_.])", name, re.IGNORECASE):
            return role
    return "Unknown"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--consul-addr", required=True, help="Store Consul address, e.g. 127.0.0.1:8500")
    args = parser.parse_args(argv)
    base = args.consul_addr
    if "://" not in base:
        base = "http://" + base

    try:
        addr = urlsplit(base)
        if (
            addr.scheme not in ("http", "https")
            or not addr.hostname
            or addr.username is not None
            or addr.path not in ("", "/")
            or addr.query
            or addr.fragment
        ):
            raise ValueError("expected a Consul HTTP(S) host and port")
        with urlopen(base.rstrip("/") + "/v1/catalog/nodes", timeout=10) as response:
            nodes = json.load(response)
            filtered = response.headers.get("X-Consul-Results-Filtered-By-ACLs") == "true"
        if not isinstance(nodes, list):
            raise ValueError("expected a list of Consul catalog nodes")
        rows = []
        for node in nodes:
            name, address = node["Node"], node["Address"]
            if not isinstance(name, str) or not name.isprintable() or not isinstance(address, str):
                raise ValueError("expected a printable node name and an IP address")
            rows.append((name, str(ip_address(address))))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(f"Could not list Consul nodes: {exc}", file=sys.stderr)
        return 1

    if filtered:
        print("Consul filtered some nodes based on ACLs.", file=sys.stderr)
    if not rows:
        print("Consul returned no registered nodes.", file=sys.stderr)

    table = [("NODE", "IP", "ROLE HINT")]
    table.extend((name, ip, role_hint(name)) for name, ip in sorted(rows, key=lambda row: row[0]))
    name_width = max(len(name) for name, _, _ in table)
    ip_width = max(len(ip) for _, ip, _ in table)
    for name, ip, role in table:
        print(f"{name:<{name_width}}  {ip:<{ip_width}}  {role}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
