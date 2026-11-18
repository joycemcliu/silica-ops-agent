#!/usr/bin/env python3
"""Gather one session's lifecycle and associated video records through GET APIs."""

from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from inspection_http import Client, emit, parser, report, segment, show_evidence, text


def validate_session(data):
    if not isinstance(data, dict) or not isinstance(data.get("id"), str):
        raise ValueError("Expected a session object with an id")
    if data.get("experienceProgress") is not None and not isinstance(data["experienceProgress"], dict):
        raise ValueError("Expected experienceProgress to be an object or null")


def validate_videos(data):
    if not isinstance(data, dict) or "rendering_list" not in data:
        raise ValueError("Expected video session details with rendering_list")
    records = data["rendering_list"]
    if records is not None and (not isinstance(records, list) or any(not isinstance(row, dict) for row in records)):
        raise ValueError("Expected rendering_list to be an array or null")


def local_time(value, zone, field, issues):
    if not value:
        issues.append(f"{field}: not reported")
        return None
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if instant.tzinfo is None or instant.year == 1:
            raise ValueError()
        return instant.astimezone(zone).isoformat()
    except (ValueError, TypeError, AttributeError):
        issues.append(f"{field}: invalid or offset-free timestamp")
        return None


def collect(args, client):
    result = report(args)
    result["timezone"] = args.timezone
    result["session_info"] = None
    result["issues"] = []
    session = client.get(f"/session/sessions/{segment(args.session)}", validate_session)
    videos = client.get(f"/video/holodecks/{segment(args.room)}/session/{segment(args.session)}", validate_videos)
    result["evidence"] = {"session": session, "video_records": videos}
    if session["state"] == "retrieved":
        raw = session["data"]
        if raw["id"] != args.session or raw.get("holodeckID") != args.room:
            session.update(state="could_not_retrieve", data=None, error="Response session/room does not match target")
        else:
            progress = raw.get("experienceProgress") or {}
            info = {"session_id": raw["id"], "experience": raw.get("experienceID"), "room": raw.get("holodeckID"),
                    "mode": raw.get("mode"), "latest_status": raw.get("status")}
            for key in ("experienceID", "mode", "status"):
                if raw.get(key) in (None, ""):
                    result["issues"].append(f"{key}: not reported")
            zone = ZoneInfo(args.timezone)
            for key, value in (("local_created_at", raw.get("createdAt")),
                               ("local_start_time", progress.get("startTime")),
                               ("local_end_time", progress.get("endTime"))):
                info[key] = local_time(value, zone, key, result["issues"])
            result["session_info"] = info
            # Keep customer/player data out of retained inspection reports.
            session["data"] = info
    return result


def summary(result):
    for name, evidence in result["evidence"].items():
        show_evidence(name, evidence)
    if result["session_info"]:
        for key, value in result["session_info"].items():
            print(f"  {key}: {text(value)}")
    videos = result["evidence"]["video_records"]
    if videos["state"] == "retrieved":
        rows = videos["data"]["rendering_list"] or []
        print(f"Associated video records: {len(rows)} (not a full task inventory)")
        for row in rows:
            print(f"  name={text(row.get('name'))} status={text(row.get('status'))} video_url={text(row.get('video_url'))}")
    for issue in result["issues"]:
        print(f"Missing information: {issue}")


def main():
    command = parser(__doc__)
    command.add_argument("--timezone", required=True, help="Store IANA timezone, e.g. America/New_York")
    args = command.parse_args()
    try:
        ZoneInfo(args.timezone)
        client = Client(args)
    except (ZoneInfoNotFoundError, ValueError, OSError) as exc:
        command.error(f"Invalid timezone or CA configuration ({type(exc).__name__})")
    return emit(collect(args, client), args, summary)


if __name__ == "__main__":
    raise SystemExit(main())
