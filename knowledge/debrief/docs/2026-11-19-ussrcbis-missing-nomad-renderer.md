---
incident: 2026-11-19-ussrcbis-missing-nomad-renderer
date: 2026-11-20
store: USSRCBIS
session_id: "codex 01a1f6e3-3355-79f2-8890-55f173ae19f3"
---

[Incident report and evidence ledger](../../incidents/2026-11-19-ussrcbis-missing-nomad-renderer.md)

## Time sinks

- Detached tunnel retries | About a minute on one follow-up | A bounded foreground mode and the first failing subprocess result would have made the fallback faster.

## Asked the user, should have known

- None. Temporary tunnel changes required explicit approval.

## Wrong assumptions

- The first tunnel attempt passed a relative store path to `--store`. The helper treated it as a store identifier. Passing the store code and the configured environments root resolved it. See E11.

## Toolkit friction

- [med] [open] `scripts/store-port-forward.sh` timed out without a useful subprocess error. Foreground forwarding to the approved proxy pods worked. See E11.\
  Proposal: Add a supported foreground diagnostic mode that surfaces discovery and proxy errors.\
  Status checked: 2026-11-20. The foreground fallback was verified against production. The toolkit still lacks that mode.\
  Remaining: Implement the mode and test live failure reporting and cleanup.
- [high] [open] The deployed GitHub Actions workflow could be read, but the production Grafana MCP tool was unavailable and Nomad denied job-event access. See E06–E08.\
  Proposal: Document which read-only source can establish a job deregistration, including any account or entitlement required.\
  Status checked: 2026-11-20. Nomad access was denied during diagnosis and no Grafana production tool was exposed.\
  Remaining: Verify whether a retained audit source can identify the operation and actor.

## Blind spots

- No administrative event established what removed the job. The published objects required authorized playback access. See E06, E10 and E13.

## Platform facts learned

| Fact | Evidence | Verified / inferred |
| --- | --- | --- |
| A ready, render-eligible node can coexist with an absent renderer job. | E04–E05 | Verified |
| Terraform can recreate the declared system job when it is missing from live Nomad. | E08–E09 | Verified |
| Task API upload URLs can be present while direct storage playback probes receive access denied. | E10 | Verified |

## What helped

- The exact Nomad job read plus Consul and node checks identified the missing registration quickly. Comparing the earlier and recovery apply logs separated the verified restoration from the unknown removal mechanism. See E04–E09.
