#!/usr/bin/env python3
"""Read-only check of a store deployment: env repo Terraform files vs live Nomad/Consul.

Expected jobs come from `module "<name>"` blocks and expected DNS names from
`<name>.service.silica` references in the store's *.tf files. Module-to-job
mapping is a name heuristic, so unmatched modules are WARN, not FAIL.
"""

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

MODULE_RE = re.compile(r'^\s*module\s+"([^"]+)"', re.M)
DNS_RE = re.compile(r"([A-Za-z0-9-]+)\.service\.silica")
RESTART_WARN = 20  # restart counts are lifetime totals, so keep this high
LEVELS = {"OK": 0, "WARN": 1, "FAIL": 2}


def norm(name):
    return re.sub(r"[^a-z0-9]", "", name.lower())


def find_store_dir(env_root, store):
    root = Path(env_root)
    for candidate in (root / store, root / store.upper()):
        if candidate.is_dir():
            return candidate
    raise SystemExit(f"Store directory not found for '{store}' under {root}")


def parse_expected(store_dir):
    modules, dns = set(), set()
    for tf in sorted(store_dir.glob("*.tf")):
        text = tf.read_text(errors="replace")
        modules.update(MODULE_RE.findall(text))
        dns.update(DNS_RE.findall(text))
    return sorted(modules), sorted(dns)


def http_json(base, path, timeout=10):
    url = base.rstrip("/") + path
    if "://" not in base:
        url = "http://" + url
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.load(resp)


def check_nomad(base, modules):
    results = []
    jobs = http_json(base, "/v1/jobs")
    allocs = http_json(base, "/v1/allocations")
    job_names = {norm(j["Name"]) for j in jobs}
    # Jobs are named "<module>/<job>"; sub-modules (e.g. X-deployer) live under X.
    namespaces = {norm(j["Name"].split("/")[0]) for j in jobs}

    for module in modules:
        key = norm(module)
        if key not in namespaces and not any(key.startswith(ns) for ns in namespaces) \
                and not any(key in n for n in job_names):
            results.append(("WARN", f"module {module}", "no Nomad job with a matching name"))

    groups = {}
    for a in allocs:
        groups.setdefault((a["JobID"], a["TaskGroup"]), []).append(a)
    for (job_id, group), items in sorted(groups.items()):
        if any(a["ClientStatus"] == "running" for a in items):
            running = [a for a in items if a["ClientStatus"] == "running"]
            restarts = max(
                sum(t.get("Restarts", 0) for t in (a.get("TaskStates") or {}).values())
                for a in running
            )
            if restarts >= RESTART_WARN:
                results.append(("WARN", f"alloc {job_id}/{group}", f"{restarts} restarts"))
            continue
        latest = max(items, key=lambda a: a.get("ModifyIndex", 0))
        job = next((j for j in jobs if j["ID"] == job_id), {})
        if latest["ClientStatus"] in ("failed", "lost"):
            results.append(("FAIL", f"alloc {job_id}/{group}", f"latest allocation {latest['ClientStatus']}"))
        elif latest["ClientStatus"] == "pending" and job.get("Type") == "service":
            results.append(("FAIL", f"alloc {job_id}/{group}", "stuck pending"))
    return results


def check_consul(base, dns_names):
    results = []
    for name in dns_names:
        entries = http_json(base, f"/v1/health/service/{urllib.parse.quote(name)}")
        passing = [
            e for e in entries if all(c["Status"] == "passing" for c in e.get("Checks", []))
        ]
        if not entries:
            results.append(("FAIL", f"dns {name}.service.silica", "service not registered"))
        elif not passing:
            results.append(("FAIL", f"dns {name}.service.silica", "no passing instance"))
    return results


def run(args):
    store_dir = find_store_dir(args.env_root, args.store)
    modules, dns_names = parse_expected(store_dir)
    results = [("OK", "env repo", f"{store_dir.name}: {len(modules)} modules, {len(dns_names)} DNS names")]
    for label, check, arg in (
        ("Nomad", check_nomad, modules),
        ("Consul", check_consul, dns_names),
    ):
        addr = args.nomad_addr if label == "Nomad" else args.consul_addr
        try:
            found = check(addr, arg)
        except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
            results.append(("FAIL", label, f"query failed: {exc}"))
            continue
        results.extend(found or [("OK", label, "no problems found")])
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--store", required=True, help="Store code, e.g. ATWIECOL")
    parser.add_argument("--env-root", required=True, help="silica-environments root (SILICA_ENV_REPO)")
    parser.add_argument("--nomad-addr", required=True, help="e.g. 127.0.0.1:4646")
    parser.add_argument("--consul-addr", required=True, help="e.g. 127.0.0.1:8500")
    parser.add_argument("--json", action="store_true", help="Print JSON instead of text")
    args = parser.parse_args(argv)

    results = run(args)
    if args.json:
        print(json.dumps([dict(zip(("level", "subject", "detail"), r)) for r in results], indent=2))
    else:
        for level, subject, detail in results:
            print(f"{level:<4}  {subject}: {detail}")
    return 1 if any(LEVELS[r[0]] == 2 for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
