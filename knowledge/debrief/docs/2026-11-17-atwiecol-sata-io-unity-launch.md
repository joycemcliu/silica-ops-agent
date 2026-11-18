---
incident: 2026-11-14-atwiecol-sata-io-unity-launch
date: 2026-11-17
store: ATWIECOL
session_id: "Codex; conversation identifier and local PC IP not captured"
---

Diagnosis handoff: [incident report](../../incidents/2026-11-14-atwiecol-sata-io-unity-launch.md). The user accepted strong evidence of a SATA I/O induced launch incident, requested follow-up on NATS stability/sync volume and health checks, then accepted the findings/actions as sufficient and requested final closure. The diagnosis is complete. Component-level fault, historical initiating workload and permanent repair remain unconfirmed.

## Time sinks

- Grafana restoration | approximately 2 minutes waiting for the sandboxed attempt to time out before escalated startup acquired the helper lock | On credential-storage permission errors, surface the existing attempt's bounded retry/lock state and rerun with the required escalation.
- Repeated SSH authentication checks | multiple extra connections; duration not measured | Separate sudo invocations did not retain authentication. One authenticated read-only shell completed the mount inspection.

## Asked the user, should have known

None. Final recovery action/time was requested and not supplied; this was not inferable from the inspected evidence. Closure must retain that uncertainty.

## Wrong assumptions

- Initial guessed broker selector `nats.*` returned nothing; discovery showed `infra/nats`. Empty guessed selectors must not be used as evidence of normal service.
- Unprivileged Docker inspection was denied, and a subsequent `sudo -n` did not reuse authentication from an earlier sudo process. Final mount verification used one authenticated read-only shell.
- A remote timer filter assumed rg existed; it did not. Direct fstrim journal reads supplied the relevant evidence.
- Initial wording treated WriteFullState durations as small disk-write durations. Version-matched source shows that the timer covers state preparation before the file write. Corrected the report/runbook and user-facing interpretation; kernel timeouts and actual failed syncs remain independent evidence.

## Toolkit friction

- [med] [open] `scripts/grafana-mcp-forward.sh` — sandboxed gcloud credential access failed while the startup helper retained its serialization lock (incident E03). Proposal: document that status/process probes may require escalation and make authentication failure terminate startup early. Status checked: 2026-11-17 — runtime failure and bounded timeout observed; no helper change made. Remaining: implementation and validation of early failure behavior.
- [med] [open] `scripts/store-port-forward-ssh.sh` — authenticated privileged inspection required several manually composed attempts (E10/E16). Proposal: document a reviewed pattern for one credential-fed read-only privileged command, with shell quoting and no secret output. Status checked: 2026-11-17 — final single-shell inspection succeeded; no shared toolkit change. Remaining: document and validate a reusable approach; do not introduce broad sudo defaults.
- [low] [open] Grafana MCP response parsing — Prometheus results used a top-level data array, unlike the first parsing assumption; raw results expanded unnecessarily. Proposal: normalize supported result envelopes before output and summarize extrema/time windows. Status checked: 2026-11-17 — investigation-local parser corrected and summaries inspected; no toolkit implementation. Remaining: reusable parser and bounded-output validation.
- [med] [open] Disk workload attribution — retained metrics exposed host-level stalls but no process/container disk-I/O attribution (E27–E28). Proposal: retain bounded process/cgroup I/O telemetry with timestamps so demand can be separated from failed completion at recurrence. Status checked: 2026-11-17 — metric discovery found no matching retained attribution series; a current in-memory sample succeeded but did not reproduce the incident. Remaining: reviewed telemetry design, implementation and retention validation.

## Blind spots

- Exact deployed source revision, final recovery action/time and exhaustive impact per session were not established.
- Passing SMART and zero CRC counters did not identify the component causing queued-write timeouts.
- No maintenance experiment or repair validation occurred; vendor-specific SMART fields were not decoded without authoritative model support.
- Retained host-level disk metrics lacked process/container I/O attribution. A current passive sample could not reconstruct the workload at the historic stall.

## Platform facts learned

| Fact | Evidence | verified / inferred |
| --- | --- | --- |
| This deployment's NATS persistence is backed by the masters' local root disks | Incident E09/E16: mount resolution on all hosts and live container bind mount on one | verified |
| Shared launch consumers can crash after queue recovery fails | E06/E17: retained panics and inspected source call path | verified |
| A SMART PASSED summary can coexist with repeated host SATA write timeouts and resets | E08/E10/E15 | verified |
| Storage stalls caused the observed queue/launch disruption | Correlated kernel, broker, conductor and application evidence E04–E19 | inferred; strongly supported |
| A broker process can remain up while its Raft node holds a failed-write state | Follow-up lifecycle evidence and matching upstream source E22–E24 | verified |
| Enabled-only health can pass while full health reports failed consumer follower copies | Live full/narrow checks and leader-aware consumer readbacks E29–E30 | verified |

## Platform knowledge proposals

### Shared Unity launch delivery

- Action: create; implemented in this handoff.
- Document: [Unity launch command delivery flow](../../platform/docs/flows/unity-launch-command-delivery.md).
- Knowledge: distinguish lifecycle delivery, launch-command consumption, Nomad execution and application readiness; correlate kernel/broker evidence before attributing quorum churn to storage.
- Evidence: incident E04–E17 and source inspection during documentation completion. Status is draft; no repair validation implied.

## What helped

- Kernel timeouts plus broker sync failures established a storage mechanism independently of healthy NAS, SSH and allocation status.
- Per-host metrics showed stalls at different times and a multi-minute collapse in useful write completion.
- Explicit UTC journal reads prevented confusion between local Vienna timestamps and Grafana time bounds.

## Completion

Temporary store SSH helpers exited and final scoped process inspection found no remaining ATWIECOL SSH forwards. Both shared Grafana endpoints were reachable and left running. The incident report records proposed health alerts, leader-aware replica review, recurrence telemetry and a controlled SSD comparison; none was deployed or executed. Documentation changes only; unrelated local work preserved; no commit, push or external ticket update. Runbook remains draft with an empty last_verified; reusable flow remains draft. No existing content removed.
