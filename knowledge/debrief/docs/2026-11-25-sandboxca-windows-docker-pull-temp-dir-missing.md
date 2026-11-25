---
incident: 2026-11-25-sandboxca-windows-docker-pull-temp-dir-missing
date: 2026-11-25
store: SANDBOXCA
session_id: "codex 01a21107-c85c-7860-b314-e95211b25da2"
---

[Incident and evidence ledger](../../incidents/2026-11-25-sandboxca-windows-docker-pull-temp-dir-missing.md)

## Time sinks

- Nomad allocation history | One repeated query | The first response included complete task event objects and truncated. Selecting node, task state, timestamp, and failure message surfaced the failure sequence. E02.
- WinRM recovery | One timed-out attempt | The first repair command asked Docker for its root before touching the filesystem. The retry reused the already verified root and limited the command to the filesystem and ACL. E03, E07.

## Asked the user, should have known

- None.

## Wrong assumptions

- The first allocation query during recovery assumed at least one allocation. Nomad temporarily returned an empty list, so the follow-up handled zero explicitly before checking the later running allocation. E08.

## Toolkit friction

- [med] [open] `docs/diagnose_toolkit.md` omits SANDBOXCA from the direct dev access table. The user's office IPs worked for direct Nomad, Consul, and WinRM access. E01, E03.\
  Proposal — Add SANDBOXCA to the direct dev access table.\
  Status checked — 2026-11-25. Direct access was verified live. The table still omits the store.\
  Remaining — Update the toolkit entry.
- [med] [open] Windows audit coverage could not attribute the directory loss. E05.\
  Proposal — Assess targeted file-access auditing for deletion and rename on the Docker temp directory and its parent.\
  Status checked — 2026-11-25. File System auditing was off and the retained USN journal started after the failure window.\
  Remaining — Approve and validate targeted auditing before relying on it for a recurrence.

## Blind spots

- The available logs could not identify what removed or moved the directory. The `Harddisk2` event sample could not be tied to the Docker data volume. E05–E06.
- Recovery confirmed task startup. Recording output was outside the check. E08–E09.
- A teammate reported a similar failure on a second PC with insufficient space. The exact error and recovery are unverified. For comparison, capture the error, free space on the Docker volume, whether the temp directory exists, and any cleanup activity before making changes. E10–E12.

## Platform facts learned

| Fact                                                                                                                     | Evidence | Verified / inferred        |
| ------------------------------------------------------------------------------------------------------------------------ | -------- | -------------------------- |
| Nomad can report a healthy Docker driver while new pulls fail at layer staging.                                          | E01–E03  | Verified                   |
| Docker 24.0.6 creates the temp directory at daemon startup. The pull opens a temporary file in the configured directory. | E04      | Verified                   |
| Recreating the missing directory with inherited SYSTEM access let the same recorder image pull while Docker stayed up.   | E07–E08  | Verified for this incident |

## What helped

- Matching the Nomad event with the Docker provider event and a direct WinRM path check identified the failed operation. The final Nomad check verified both the prestart task and the recorder process. E02–E03, E08.
