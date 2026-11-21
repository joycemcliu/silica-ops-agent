---
incident: 2026-11-20-usforcro-experience-timer-host-clock-skew
date: 2026-11-21
store: USFORCRO
session_id: "codex 01a1fb94-5d26-7660-b9ee-6787bccb3661"
---

[Incident and evidence ledger](../../incidents/2026-11-20-usforcro-experience-timer-host-clock-skew.md)

## Time sinks

- Broad log searches | About 1 minute | Start with experience server progress payloads and compare end times to receipt times. See E03–E04.
- Standard store tunnel | About 1 minute | A noninteractive preflight could detect the local sudo prompt before opening the SSH forward. See E07.

## Asked the user, should have known

- None.

## Wrong assumptions

- Expected the standard store tunnel to run noninteractively. It reached the store proxy and then stopped at a local sudo prompt. See E07.

## Toolkit friction

- [med] [open] `scripts/store-sshuttle.sh` required interactive sudo in the agent environment. See E07.\
  Proposal — Add a noninteractive preflight and document how to request a scope-limited WinRM fallback.\
  Status checked — 2026-11-21. The standard tunnel triggered a prompt. The approved two-host forwarding fallback worked and closed after the check.\
  Remaining — Implement and test the preflight and document the fallback.

## Blind spots

- The Windows logs available in Grafana did not explain the loss of time synchronization. See E06 and E09.

## Platform facts learned

| Fact | Evidence | Verified / inferred |
| --- | --- | --- |
| A full timer window can display zero when the host reports a past end time. | E03, E05, E08 | Verified |
| A Windows Time service in the Running state can still have no upstream synchronization. | E08 | Verified |

## What helped

- Comparing the payload with the API receipt time surfaced the size of the skew. Sampling an affected and healthy room with the same WinRM check confirmed where it originated. See E03 and E08.
