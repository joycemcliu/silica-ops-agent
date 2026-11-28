"""Google Drive MCP server for publishing Phase C RCA reports."""

import argparse
from datetime import date as Date, timezone
import fcntl
from html import escape
import json
import os
from pathlib import Path
import sys
from tempfile import NamedTemporaryFile
from typing import Annotated, Literal
from uuid import uuid4

from google.auth.exceptions import DefaultCredentialsError, GoogleAuthError
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.service_account import Credentials
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints
from requests import RequestException


ROOT = Path(__file__).resolve().parents[2]
RCA_FOLDER_ID = "0ACoH-lkKZePWUk9PVA"
DRIVE_FILES = "https://www.googleapis.com/drive/v3/files"
DRIVE_UPLOAD = "https://www.googleapis.com/upload/drive/v3/files"
DOC_MIME = "application/vnd.google-apps.document"
FILE_FIELDS = "id,name,webViewLink"
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"

mcp = FastMCP("google_drive_rca")
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
OneLine = Annotated[Text, StringConstraints(pattern=r"^[^\r\n]+$")]


class ReportFields(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Summary(ReportFields):
    what_happened: Text
    who_was_affected: Text
    current_state: Text


class RootCause(ReportFields):
    trigger: Text
    underlying_cause: Text
    detection_gap: Text


class Recovery(ReportFields):
    action: Text
    verification: Text
    recurrence_steps: Text


class FollowUp(ReportFields):
    action: Text
    owner: Text
    due: Date | None = None
    ticket: Text | None = None


class TimelineEntry(ReportFields):
    time: AwareDatetime | None = None
    detail: Text | None = None


class Timeline(ReportFields):
    issue_started: TimelineEntry | None = None
    detected: TimelineEntry | None = None
    mitigation_applied: TimelineEntry | None = None
    resolved: TimelineEntry | None = None


class RCAReport(ReportFields):
    store_code: OneLine
    store_or_env_name: OneLine | None = Field(default=None, description="Title prefix. Defaults to store_code.")
    incident_title: OneLine
    date: Date = Field(description="Incident date in UTC (YYYY-MM-DD).")
    affected_session: list[Text] = Field(default_factory=list, description="Affected session IDs. An empty list renders as N/A.")
    slack_thread_id: Annotated[str, StringConstraints(pattern=r"^[0-9]{10}\.[0-9]{6}$")] = Field(
        description="Root timestamp of the original Slack escalation thread, e.g. 1700000000.000000."
    )
    severity: Literal["SEV1", "SEV2", "SEV3"]
    status: Literal["Resolved", "Mitigated", "Monitoring"]
    summary: Summary = Field(description="Use 3–5 plain-language sentences across the three fields. Omit internal service names.")
    root_cause: RootCause = Field(description="Name the relevant services, components, versions, and configurations. Label uncertainty.")
    recovery: Recovery | None = None
    follow_up: list[FollowUp] = Field(default_factory=list)
    timeline: Timeline = Field(description="Use time zone aware timestamps. They are converted to UTC in the document.")

    @property
    def title(self):
        return f"{self.store_or_env_name or self.store_code} {self.incident_title}"


def escaped(text):
    return escape(text).replace("\n", "<br>")


def labeled_list(items):
    return "<ul>" + "".join(f"<li><b>{label}:</b> {escaped(value)}</li>" for label, value in items) + "</ul>"


def table(headers, rows):
    head = "".join(f"<th>{header}</th>" for header in headers)
    body = "".join("<tr>" + "".join(f"<td>{escaped(cell)}</td>" for cell in row) + "</tr>" for row in rows)
    return f'<table border="1" cellpadding="5"><tr>{head}</tr>{body}</table>'


def report_html(report):
    metadata = (
        ("store_code", report.store_code),
        ("date", report.date.isoformat()),
        ("affected_session", ", ".join(report.affected_session) or "N/A"),
        ("slack_thread_id", report.slack_thread_id),
        ("severity", report.severity),
        ("status", report.status),
        ("duration", "N/A"),
    )
    summary = report.summary
    cause = report.root_cause
    recovery = report.recovery
    follow_up = [(row.action, row.owner, row.due.isoformat() if row.due else "N/A", row.ticket or "") for row in report.follow_up]
    timeline = []
    for label, entry in (
        ("Issue started (first evidence)", report.timeline.issue_started),
        ("Detected", report.timeline.detected),
        ("Mitigation applied", report.timeline.mitigation_applied),
        ("Resolved", report.timeline.resolved),
    ):
        time = entry.time.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if entry and entry.time else "N/A"
        event = f"{label}: {entry.detail}" if entry and entry.detail else label
        timeline.append((time, event))

    return "\n".join([
        '<!doctype html><html><head><meta charset="utf-8"></head><body>',
        f"<h1>{escaped(report.title)}</h1>",
        "<p>" + "<br>".join(f"{label}: {escaped(value)}" for label, value in metadata) + "</p>",
        "<h2>Summary and impact</h2>",
        labeled_list((
            ("What happened", summary.what_happened),
            ("Who was affected", summary.who_was_affected),
            ("Current state", summary.current_state),
        )),
        "<h2>Root cause</h2>",
        labeled_list((
            ("Trigger", cause.trigger),
            ("Underlying cause", cause.underlying_cause),
            ("Detection gap", cause.detection_gap),
        )),
        "<h2>Recovery</h2>",
        labeled_list((
            ("Action", recovery.action),
            ("Verification", recovery.verification),
            ("If it happens again, Technical Supporter should", recovery.recurrence_steps),
        )) if recovery else "<p>N/A</p>",
        "<h2>Follow-up</h2>",
        table(("Action", "Owner", "Due", "Ticket"), follow_up) if follow_up else "<p>N/A</p>",
        "<h2>Incident timeline</h2>",
        table(("Time (UTC)", "Event"), timeline),
        "</body></html>",
    ])


def drive_request(client, method, url, **kwargs):
    try:
        response = client.request(method, url, timeout=20, **kwargs)
    except GoogleAuthError as error:
        raise RuntimeError("Google authentication failed. Check the RCA service account credentials.") from error
    except RequestException as error:
        raise RuntimeError("Drive did not respond. Check the existing report before retrying a write.") from error
    if not response.ok:
        raise RuntimeError(f"Drive returned HTTP {response.status_code}. Check the RCA credentials and folder access.")
    return response.json()


def existing_report(client, thread_id):
    params = {
        "q": (f"'{RCA_FOLDER_ID}' in parents and trashed = false and mimeType = '{DOC_MIME}' "
              f"and appProperties has {{ key='slack_thread_id' and value='{thread_id}' }}"),
        "includeItemsFromAllDrives": "true",
        "supportsAllDrives": "true",
        "fields": f"nextPageToken,incompleteSearch,files({FILE_FIELDS})",
    }
    found = None
    while True:
        page = drive_request(client, "GET", DRIVE_FILES, params=params)
        if page.get("incompleteSearch"):
            raise RuntimeError("Drive could not complete the search for an existing RCA document.")
        for file in page.get("files", []):
            if found:
                raise RuntimeError("Multiple RCA documents match this Slack thread. Resolve the duplicate in Drive.")
            found = file
        if not page.get("nextPageToken"):
            return found
        params["pageToken"] = page["nextPageToken"]


def upload_report(client, report, existing):
    metadata = {"name": report.title, "mimeType": DOC_MIME}
    if not existing:
        metadata.update(parents=[RCA_FOLDER_ID], appProperties={"slack_thread_id": report.slack_thread_id})
    boundary = uuid4().hex
    body = (
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{json.dumps(metadata)}\r\n"
        f"--{boundary}\r\nContent-Type: text/html; charset=UTF-8\r\n\r\n"
        f"{report_html(report)}\r\n--{boundary}--\r\n"
    ).encode("utf-8")
    return drive_request(
        client, "PATCH" if existing else "POST", f"{DRIVE_UPLOAD}/{existing['id']}" if existing else DRIVE_UPLOAD,
        params={"uploadType": "multipart", "supportsAllDrives": "true", "fields": FILE_FIELDS},
        headers={"Content-Type": f"multipart/related; boundary={boundary}"},
        data=body,
    )


def save_local_report(report, replace_existing):
    directory = ROOT / "knowledge/rca/drafts"
    if directory.resolve() != directory:
        raise RuntimeError("The RCA drafts directory must reside directly in the toolkit checkout.")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = directory / f"{report.slack_thread_id}.html"
    if path.is_symlink():
        raise RuntimeError("The RCA draft path must be a regular file in the drafts directory.")
    if replace_existing and not path.is_file():
        raise RuntimeError("No local RCA report matches this Slack thread.")

    if replace_existing or not path.is_file():
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=directory, delete=False) as draft:
            temp_path = Path(draft.name)
            try:
                draft.write(report_html(report))
                draft.close()
                if replace_existing:
                    temp_path.replace(path)
                else:
                    # Publish the complete file without overwriting another session's draft.
                    path.hardlink_to(temp_path)
            except FileExistsError:
                pass
            finally:
                temp_path.unlink(missing_ok=True)
    return {"action": "local_draft", "path": str(path)}


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=True))
def create_rca_doc(report: RCAReport, replace_existing: bool = False) -> dict[str, str]:
    """Publish an approved Phase C report to Drive or save it locally when credentials are unset.

    Returns a Google Docs URL in Drive mode or an absolute HTML file path in local mode.
    Reusing the original Slack thread timestamp returns the existing report for that destination.
    Set replace_existing only for an approved replacement of the full report body.
    """
    configured_path = os.environ.get("RCA_GOOGLE_CREDENTIALS_FILE")
    if not configured_path:
        return save_local_report(report, replace_existing)
    path = ROOT / Path(configured_path).expanduser()
    if not path.is_file():
        raise RuntimeError("Correct RCA_GOOGLE_CREDENTIALS_FILE in mcp-servers/env/.env.gdrive and start a new session.")

    # Stdio servers on the same host share this lock when they use the same credential file.
    with path.open() as credential_file:
        try:
            credentials = Credentials.from_service_account_info(json.load(credential_file), scopes=[DRIVE_SCOPE])
        except (DefaultCredentialsError, ValueError) as error:
            raise RuntimeError("Correct RCA_GOOGLE_CREDENTIALS_FILE in mcp-servers/env/.env.gdrive and start a new session.") from error
        with AuthorizedSession(credentials, refresh_timeout=20) as client:
            fcntl.flock(credential_file, fcntl.LOCK_EX)
            existing = existing_report(client, report.slack_thread_id)
            if replace_existing and not existing:
                raise RuntimeError("No existing RCA document matches this Slack thread.")
            if existing and not replace_existing:
                document, action = existing, "existing"
            else:
                document = upload_report(client, report, existing)
                action = "updated" if existing else "created"
    doc_id = document["id"]
    return {
        "document_id": doc_id,
        "title": document["name"],
        "url": document.get("webViewLink") or f"https://docs.google.com/document/d/{doc_id}/edit",
        "action": action,
    }


def run_http(host, port):
    configured_path = os.environ.get("RCA_MCP_HTTP_TOKEN_FILE")
    if not configured_path:
        sys.exit("HTTP mode requires RCA_MCP_HTTP_TOKEN_FILE.")
    path = ROOT / Path(configured_path).expanduser()
    try:
        token = path.read_text().strip()
    except OSError:
        sys.exit("Unable to read RCA_MCP_HTTP_TOKEN_FILE.")
    if not token:
        sys.exit("RCA_MCP_HTTP_TOKEN_FILE must contain a bearer token.")

    sys.path.insert(0, str(ROOT / "mcp-servers"))
    from mcp_http import serve_http

    serve_http(mcp, host, port, token)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--http", action="store_true", help="serve streamable HTTP at /mcp instead of stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=60011)
    args = parser.parse_args()
    if args.http:
        run_http(args.host, args.port)
    else:
        mcp.run()
