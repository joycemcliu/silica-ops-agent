---
title: Renderer debug logs missing in Loki
slug: renderer-debug-logs-missing-in-loki
services: [video-dge-renderer, grafana-alloy, loki]
tags: [logging, debug, nomad]
status: draft
last_verified:
applies_to:
  logger: shared Go zerolog logger and renderer Terraform templates
source_incidents:
  - ../../incidents/2026-11-03-renderer-debug-logs-missing.md
---

## Symptoms

New renderer debug messages cannot be found in Grafana Loki. Adding debug calls to a binary alone does not establish that the deployed runtime permits debug output.

## Triage (read-only, in order)

1. Inspect [renderer configuration wiring](../../apps/video-dge/terraform-module/renderer.tf) and [the execute task](../../apps/video-dge/terraform-module/templates/renderer.hcl.tftpl). `renderer.log_level` supplies `LOG_LEVEL`; [the variable](../../apps/video-dge/terraform-module/variables.tf) defaults to `info`. The separate AE install cron does not configure this logger.
2. Inspect [the shared logger](../../libs/go/log/logger.go). It parses the configured severity case-insensitively and writes JSON to stderr. [AE output scanning](../../apps/video-dge/render/internal/adapters/aftereffect/cmd/scan_log.go) relogs child stdout as debug messages prefixed `AE Log:`.
3. Inspect [allocation collection](../../apps/monitoring/terraform-module/templates/grafana-alloy/configs/logs/allocation.alloy). It collects stdout and stderr, with no renderer severity filter. `level` remains in application JSON; `task` is structured metadata. An absent indexed level/task label does not establish that the log is absent.
4. Perform the live checks under “Not yet verified.” Static code does not confirm deployed settings or the running binary.

## Likely causes

| Cause | Evidence that confirms | Evidence that rules out |
| --- | --- | --- |
| Runtime threshold still info | Running execute task has `LOG_LEVEL=info` | Debug enabled and expected line emitted in stderr |
| Running binary lacks new messages | Deployed binary version predates the added calls | Exact message exists in running allocation stderr |
| Wrong stream/query | Querying stderr/application JSON finds the missing entries | Exact line exists in stderr but broad Loki job query cannot find it |
| Relevant code did not execute | Render event or AE invocation never reaches that call | Exact message exists in stderr |
| Collection or ingestion failure | Line exists in stderr; collector targets or Loki writes fail | Same expected line appears in Loki |
| Renderer debug filtering by inspected Alloy config | No such filter found | Checked allocation template has no renderer severity drop |

## Remediation (HUMAN executes; agent never runs)

For a confirmed runtime threshold mismatch, change the target environment's `renderer.log_level` to `debug` through its normal Terraform deployment. Guard: identify environment/job and verify the current effective value first. Backup: save the current configuration and deployment plan. Risk: renderer allocation replacement and increased log volume. Rollback: restore the previous setting through the same deployment process. No deployment command was run or validated in this investigation.

For a query mismatch, copy the existing query before editing. Risk: saved dashboard results change. Rollback: restore the copied query.

## Validation checklist

Machine checks:

- [ ] Running execute task has the intended `LOG_LEVEL` and binary version.
- [ ] Expected debug message appears in allocation stderr and then Loki.

Human checks:

- [ ] Operator confirms the specific diagnostic text in Grafana. Unrelated startup debug messages do not prove the main application logger permits debug.

## Not yet verified

All live checks below remain unexecuted. In Nomad, inspect the running job's `execute` task environment and stderr. `LOG_LEVEL=info` explains suppression before collection; a matching debug line in stderr moves the investigation to query/collection/ingestion.

In Grafana, select the intended datasource, cluster, and run time range, then substitute the actual job:

```logql
{job="<renderer-job>"}
```

If entries exist, filter application JSON:

```logql
{job="<renderer-job>"} | json | level="debug"
```

The inspected default job prefix produces `video-dge/renderer`. Start without severity/task filters to distinguish an empty stream from a parsing mismatch. If no JSON debug entries exist, source stderr is the next discriminating check. If collection is failing, inspect deployed target configuration, agent errors, and Loki write rejections. Neither the live deployment nor the root cause has been verified.
