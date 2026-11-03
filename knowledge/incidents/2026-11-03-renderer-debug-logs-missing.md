---
title: Renderer debug messages missing from Grafana Loki
incident_date: 2026-11-03
timezone: Asia/Hong_Kong
runbook: ../runbooks/renderer-debug-logs-missing-in-loki.md
---

## Report and scope

The operator reported debug messages missing from Grafana Loki, then clarified that the source is `video-dge/renderer`, not Unity. The initial Unity investigation followed the wrong pipeline and does not diagnose this report. The later attachment was the AE install cron template. Environment, allocation, effective runtime log level, expected message, and Grafana query remain unspecified.

Reusable procedure: [Renderer debug logs missing in Loki](../runbooks/renderer-debug-logs-missing-in-loki.md).

## Evidence ledger

Repository inspection only; no live Grafana, Loki, Nomad, or Windows queries were executed. Commands below were run through the required `rtk` wrapper after loading its instructions. Initial attempts to use the wrapper were denied by the sandbox; subsequent reads used approved escalation. Broad searches of nonexistent `apps/experience`, `apps/bundle`, and `packages` directories failed and supplied no evidence about those components.

| Tag | Command/query or evidence source | Result summary |
| --- | --- | --- |
| observed | `cat runbooks/AGENTS.md`; `cat runbooks/scripts/fix-empty-friendlyname.ps1` | Read documentation rules and attached script; script inspects or changes device metadata, with no debug logging or log shipping |
| observed | `rtk proxy cat CLAUDE.md runbooks/INDEX.md` | Root investigation instructions absent; existing index concerns a different failure mechanism |
| observed | `rtk proxy rg -n -i 'loglevel|output_log_|error_log_|-logfile|log-file' --hidden -g '!.git/**' -g '!node_modules/**' -g '!token.txt' -g '!.nx/**' .` | Found Unity collection patterns; no bundle `logLevel` implementation identified |
| observed | Read `apps/monitoring/terraform-module/templates/grafana-alloy/configs/logs/{unity-client,allocation,loki-write,unity-analytics,runtime}.alloy` with `rtk proxy cat` | Unity file streams have no severity filter or explicit level label; output/error entries older than 168h are dropped after timestamp processing; session ID is structured metadata; Loki receives logs independently of the analytics filter |
| observed | Read `apps/monitoring/terraform-module/grafana-alloy-windows.tf` and `templates/grafana-alloy/grafana-alloy-windows.nomad.hcl.tftpl` beneath that module with `rtk proxy cat` | Windows job mounts `C:\log`; Unity collection is conditional on `meta.silica.player_number` |
| observed | `rtk proxy cat apps/monitoring/terraform-module/templates/grafana-alloy/configs/logs/runtime.alloy` | Alloy's own logger uses `warn`; this setting is separate from application log processing |
| observed | `rtk git status --short` | Existing untracked incident/runbook content and token file; token contents were not read |
| inferred | Static pipeline inspection | A stream selector requiring a `level` label can exclude Unity logs; this is a possible query mismatch, not a confirmed root cause |
| observed | `rtk proxy cat apps/video-dge/terraform-module/templates/renderer-ae-install-cron.hcl.tftpl apps/video-dge/terraform-module/renderer.tf apps/video-dge/terraform-module/templates/renderer.hcl.tftpl` | Cron job is separate; renderer `execute` task receives `LOG_LEVEL` from `var.renderer.log_level` |
| observed | `rtk proxy cat libs/go/log/logger_config.go libs/go/log/logger.go`; `rtk proxy cat libs/go/log/logger_env.go` | Application log level is parsed case-insensitively; JSON logging writes to stderr |
| observed | Read renderer config, AE scanner, command wrapper, and composition extractor under `apps/video-dge/render` using `rtk proxy cat` | Renderer uses shared logger; AE stdout is relogged at debug with `AE Log:` prefix |
| observed | Searched renderer, log-level, and job-prefix declarations in `apps/video-dge/terraform-module/variables.tf` and `locals.tf` with `rtk proxy rg -n -C 6` | Renderer defaults to `info`; job prefix defaults to `video-dge/` |
| observed | Read `apps/monitoring/docs/allocation-logs.md` and discoverer adapter/resolver/handler using `rtk proxy cat` | Non-Docker tasks receive log targets too; terminal allocations have a one-hour discovery grace period |
| observed | Inspected allocation collector | Both stdout and stderr file patterns are included; no renderer severity drop; `task` is moved into structured metadata |
| inferred | Renderer threshold defaults to info | A deployed `LOG_LEVEL=info` would suppress debug before Loki, but the live value has not been checked |
| not-checked | Corrected renderer LogQL and Nomad stderr check in linked runbook | No live query execution or confirmation of messages in allocation logs |

## Outcome and remaining work

No runtime or logging configuration changed. Corrected the suggested query to renderer JSON logs and requested the environment, expected message, and whether the deployed Terraform setting was changed. Effective `execute` task `LOG_LEVEL`, stderr contents, collector health, and Loki ingestion remain unverified. No scripts were executed. Replaced the initial Unity runbook with a renderer-specific runbook because the operator corrected the scope; the initial static findings above are retained as investigation history, not evidence about the renderer.
