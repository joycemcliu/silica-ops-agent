#!/usr/bin/env python3
"""Gather every registered video task for one session through the application API."""

from inspection_http import Client, emit, parser, report, segment, show_evidence, text


FIELDS = ("session", "item", "request_id", "holodeck", "video_type", "dependencies", "status",
          "render_progress", "upload_progress", "error", "video_url", "created_at", "updated_at",
          "start_render_at", "end_render_at")


def validate_tasks(data):
    if not isinstance(data, dict) or any(not isinstance(task, dict) for task in data.values()):
        raise ValueError("Expected a map of task IDs to task objects")
    for task in data.values():
        deps = task.get("dependencies")
        if deps is not None and (not isinstance(deps, list) or any(not isinstance(dep, str) for dep in deps)):
            raise ValueError("Expected task dependencies to be an array of IDs or null")


def collect(args, client):
    result = report(args)
    tasks = client.get(f"/video/render/task/{segment(args.session)}", validate_tasks)
    result["evidence"] = {"tasks": tasks}
    result["task_count"] = None
    result["issues"] = []
    if tasks["state"] == "retrieved":
        raw = tasks["data"]
        if any(task.get("session") != args.session or task.get("holodeck") != args.room for task in raw.values()):
            tasks.update(state="could_not_retrieve", data=None, error="Response session/room does not match target")
        else:
            result["task_count"] = len(raw)
            tasks["data"] = {key: {field: task.get(field) for field in FIELDS} for key, task in raw.items()}
            for key, task in raw.items():
                missing = [field for field in FIELDS if field not in task]
                if missing:
                    result["issues"].append(f"{key}: fields not reported: {', '.join(missing)}")
                for dep in task.get("dependencies") or []:
                    if dep not in raw:
                        result["issues"].append(f"{key}: dependency {dep} not present in returned task map")
    result["output_availability"] = "URL metadata only; file reachability and media validity not checked"
    return result


def summary(result):
    tasks = result["evidence"]["tasks"]
    show_evidence("tasks", tasks)
    if tasks["state"] == "retrieved":
        print(f"Registered tasks: {result['task_count']}")
        for key, task in tasks["data"].items():
            print(f"  {text(key)}: status={text(task['status'])} render={text(task['render_progress'])} upload={text(task['upload_progress'])}")
            print(f"    dependencies={text(task['dependencies'])} error={text(task['error'])} video_url={text(task['video_url'])}")
    for issue in result["issues"]:
        print(f"Missing information: {text(issue)}")
    print(result["output_availability"])


def main():
    command = parser(__doc__)
    args = command.parse_args()
    try:
        client = Client(args)
    except (ValueError, OSError) as exc:
        command.error(f"Invalid CA configuration ({type(exc).__name__})")
    return emit(collect(args, client), args, summary)


if __name__ == "__main__":
    raise SystemExit(main())
