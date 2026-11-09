---
incident: 2026-11-07-uskirtot-wcap-short-recordings
date: 2026-11-09
store: USKIRTOT
session_id: (codex) 01a1bdf2-757a-77f1-bf1c-84b823a88b43
---

Source: [incident and evidence ledger](../../incidents/2026-11-07-uskirtot-wcap-short-recordings.md).

## Time sinks

- MCP startup/reconnection and tunnel persistence required repeated attempts; duration was not measured. Distinguish a listening forward, a successful MCP handshake and exposed query tools. [E02–E03]
- Broad session searches hit the result limit; the exact recorder-job query returned a complete bounded timeline. [E12]

## Asked the user, should have known

- Store-tunnel permission was required by policy. Repeated Grafana retries reflected unavailable tools/handshake failures; once tools appeared, use succeeded. [E02–E03]

## Wrong assumptions

- Tiny files initially left black imagery and truncated capture unresolved; probing proved one-frame files with nonblack gameplay. [E07–E08]
- Nomad no longer listing the incident allocation did not mean historical capture logs were lost; Loki retained them. [E05/E12]
- Completed render/upload status did not establish complete source footage. [E04/E07/E12]

## Toolkit friction

- [high] Grafana helper assumes Linux tools and failed on macOS because flock was absent. Proposal: document a supported macOS path and separately verify forwarding, handshake and tool exposure. No helper/config changes made. [E02]
- [med] Store helper emitted an unbound empty-array error under the local Bash; background forwards also required a held terminal. Proposal: handle empty arrays on supported shells and verify tunnel survival after helper exit. [E03]
- [med] Sandbox process discovery missed live forwards; elevated cleanup found and closed exactly the session-owned ones. Proposal: distinguish inaccessible process inventory from no active tunnels. [E16]
- [med] Required shared diagnose Python was missing. Proposal: check this prerequisite early and follow setup instructions before Python-dependent diagnosis; do not substitute interpreters. [E02]

## Blind spots

- WCap startup/first-frame readiness, precise initialization bottleneck, runtime binary attestation and controlled reproduction remain unavailable or unchecked. [E10/E14/E18]
- MP4 creation times support the delay hypothesis but are not direct readiness measurements. [E17]

## Platform facts learned

| Fact                                                                                               | Evidence    | verified / inferred       |
| -------------------------------------------------------------------------------------------------- | ----------- | ------------------------- |
| Version-matched recorder starts its duration timer at process launch                               | E10/E12     | verified                  |
| One-frame media can pass the observed duration-blind fps/dimension checks and be reported Success  | E07/E10/E12 | verified                  |
| Shorter media and late creation metadata fit an initialization delay                               | E07/E12/E17 | inferred                  |
| Unity request and timer/explicit-stop timelines distinguish intended duration from early game stop | E12–E13     | verified in this incident |

## What helped

- Compare frame counts, actual duration and sole decoded frames before pursuing rendering. [E07–E09]
- Read the deployed release tag instead of assuming current master matches recorder behavior. [E10]
- Combine exact-job Loki queries with Unity logs; disclose the remaining startup uncertainty. [E12–E14]
- Capture reusable steps in the [draft runbook](../../runbooks/docs/wcap-short-recordings.md); a separate platform document would duplicate these findings.
