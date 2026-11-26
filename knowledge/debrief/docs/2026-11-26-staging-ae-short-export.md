---
incident: 2026-11-26-staging-ae-short-export
date: 2026-11-26
store: staging
session_id: "codex 01a216ca-0b56-70a0-82c7-12724eeb78da"
---

[Incident record](../../incidents/2026-11-26-staging-ae-short-export.md)

## Time sinks

- Several remote checks looked for native logs and partial output. Starting with server progress and a single host check for space, crash events, and artifact presence would have narrowed the investigation sooner.

## Asked the user, should have known

- None.

## Wrong assumptions

- An interim update counted three short outputs. The analytics events showed two short outputs and a separate native crash.

## Toolkit friction

- [med] [open] [Staging renderer logs] Grafana had server and analytics events. The host paths checked lacked native logs for the affected export. See incident evidence E1 and E5.\
  Retain the final native progress and error lines for failed exports, keyed by request and attempt.\
  Status checked 2026-11-26. Verified the gap for this incident using Grafana and WinRM.\
  Remaining work is to verify supported log retention and test it on a failed export.

## Blind spots

- Exact reason the final short export stopped, incident-time system-drive free space, and the recovered file's independently measured duration.

## Platform facts learned

| Fact                                                                                            | Evidence           | Confidence                 |
| ----------------------------------------------------------------------------------------------- | ------------------ | -------------------------- |
| DGE calculates expected length from the named AE composition's parsed work area and frame rate. | Incident E2        | Verified                   |
| Server progress can identify how far AE got even when its native log is unavailable.            | Incident E1 and E5 | Verified for this incident |

## What helped

- Matching render progress, analytics, and Windows events by attempt distinguished the short outputs from the crash. Follow-up logs independently verified recovery.
