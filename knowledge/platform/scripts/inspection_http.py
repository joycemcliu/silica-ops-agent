"""Shared GET-only transport and command options for evidence collectors."""

import argparse
from datetime import datetime, timezone
from http.client import HTTPException
import json
import math
import ssl
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener, HTTPSHandler


def now():
    return datetime.now(timezone.utc).isoformat()


def identifier(value):
    if not value or value in (".", "..") or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_." for c in value):
        raise argparse.ArgumentTypeError("Use an identifier containing letters, numbers, hyphens, underscores or dots.")
    return value


def base_url(value):
    parsed = urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise argparse.ArgumentTypeError("Use an HTTP(S) platform URL without credentials, query or fragment.")
    return value.rstrip("/")


def timeout(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("Timeout must be a finite positive number.")
    return number


def parser(description):
    result = argparse.ArgumentParser(description=description)
    result.add_argument("--environment", choices=("dev", "prod"), required=True)
    result.add_argument("--store", type=identifier, required=True)
    result.add_argument("--base-url", type=base_url, required=True, help="Platform root through an existing access path; no /session or /video suffix")
    result.add_argument("--session", type=identifier, required=True)
    result.add_argument("--room", type=identifier, required=True)
    result.add_argument("--timeout", type=timeout, default=15.0)
    result.add_argument("--ca-file", help="Trusted CA bundle for HTTPS")
    result.add_argument("--json", action="store_true", help="Emit JSON instead of the human summary")
    return result


class NoRedirect(HTTPRedirectHandler):
    # A login page or another service must not silently become evidence.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    def __init__(self, args):
        self.base_url = args.base_url
        self.timeout = args.timeout
        self.opener = build_opener(NoRedirect(), HTTPSHandler(context=ssl.create_default_context(cafile=args.ca_file)))

    def get(self, path, validate):
        result = {"path": path, "collected_at": now(), "state": "could_not_retrieve", "http_status": None, "data": None}
        try:
            request = Request(self.base_url + path, headers={"Accept": "application/json"}, method="GET")
            with self.opener.open(request, timeout=self.timeout) as response:
                result["http_status"] = response.status
                if response.headers.get_content_type() != "application/json":
                    raise ValueError("Expected application/json")
                body = response.read(8 * 1024 * 1024 + 1)
                if len(body) > 8 * 1024 * 1024:
                    raise ValueError("Response exceeds 8 MiB; collection incomplete")
                data = json.loads(body)
                validate(data)
                result.update(state="retrieved", data=data)
        except HTTPError as exc:
            result["http_status"] = exc.code
            result["state"] = "not_found" if exc.code == 404 else "could_not_retrieve"
            result["error"] = f"HTTP {exc.code}"
        except (ValueError, UnicodeError) as exc:
            result["error"] = f"Invalid response: {exc}"
        except (URLError, OSError, HTTPException) as exc:
            result["error"] = f"Transport failed ({type(exc).__name__})"
        return result


def segment(value):
    return quote(value, safe="")


def report(args):
    return {"environment": args.environment, "store": args.store, "base_url": args.base_url,
            "session_id": args.session, "room": args.room, "collected_at": now()}


def emit(result, args, summary):
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=True))
    else:
        print(f"{args.environment}/{args.store} room={args.room} session={args.session}")
        summary(result)
    return 0 if all(value["state"] == "retrieved" for value in result["evidence"].values()) else 1


def show_evidence(name, evidence):
    print(f"{name}: {evidence['state']} ({evidence['path']})")
    if "error" in evidence:
        print(f"  {evidence['error']}")


def text(value):
    """Keep API strings on one terminal line, including control characters."""
    return json.dumps(value, ensure_ascii=True)
