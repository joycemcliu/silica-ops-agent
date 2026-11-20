---
title: Missing DGE renderer job in Nomad
slug: missing-nomad-renderer
services: [video-server, video-dge-renderer, nomad, consul]
tags: [rendering, nomad, terraform]
status: draft
last_verified:
applies_to:
  video-dge-module: "0.4.6"
  video-module: "1.6.5"
source_incidents:
  - "../../incidents/2026-11-19-ussrcbis-missing-nomad-renderer.md"
---

## Symptoms

- Several rooms stop producing new videos. Rerenders remain queued at zero progress, and trailers or highlights can stay pending on child renders.
- Prior uploads and ready video PCs can still be visible during the outage. Check the renderer job and worker registrations directly.

## Triage (read-only, in order)

1. Inspect a session from each affected room with `GET <platform>/video/render/task/<session>`. Look for runnable tasks with unchanged `queuing` status, zero progress, and no start timestamp across successive snapshots. Trace pending parent tasks to their unfinished dependencies. Healthy tasks advance to rendering. [Video inspection](../../platform/docs/domains/video-inspection.md)
2. Query Nomad `GET <nomad>/v1/jobs?namespace=*` with the available read-only credentials and find the job in the intended store and namespace. For the default renderer job, query `GET <nomad>/v1/job/video-dge%2Frenderer` and `GET <nomad>/v1/job/video-dge%2Frenderer/allocations?all=true` in that namespace. A valid-context 404 and no allocations support missing registration. A healthy job has a registration and running allocations. Check the HTTP result before interpreting an empty body or missing list item.
3. Query Consul `GET <consul>/v1/health/service/video-dge-renderer` and Nomad `GET <nomad>/v1/nodes`, followed by `GET <nomad>/v1/node/<node-id>` for current video nodes. Healthy workers register in Consul. An empty service list supports worker absence. Ready nodes with `silica.video.render=true` and a healthy Docker driver can still have zero renderer allocations.
4. Compare the store's effective deployment declaration and exact module defaults with the last successful Terraform plan and apply. A renderer creation in a later refresh and apply confirms reconciliation of the missing registration. An earlier plan with no renderer change narrows the evidence for that specific apply. Preserve the job status, task counts, and relevant workflow links before recovery.
5. If the renderer exists and workers are registered but task progress stays flat, trace publication and JetStream delivery before deciding on recovery. [Render queue delivery flow](../../platform/docs/flows/nats-video-render-queue-delivery.md)

## Likely causes

| Cause | Evidence that confirms | Evidence that rules out |
| --- | --- | --- |
| Renderer job missing from live Nomad | Correct store and namespace return HTTP 404, no allocations, and no renderer service registrations. Terraform declares the job and plans to create it. | The intended job exists in the affected namespace. |
| Intentional deployment removal | The applicable config disables the job or an actual apply log shows it being destroyed. | The examined apply leaves the renderer in place and the current declaration enables it. This only covers the examined revision and apply. |
| No eligible or working video nodes | The job exists, but Nomad reports placement failures or its allocations fail to start. | Eligible nodes can run new allocations after re-registration. |
| Delivery stall with live workers | Workers are registered and healthy, but retained matching work and stagnant consumer delivery identify the queue handoff as the failure. | The affected store has no registered renderer job or workers. Check delivery separately if a backlog persists after recovery. |

## Remediation (HUMAN executes; agent never runs)

- **Reconcile with the normal store deployment workflow.** Verify the store and namespace, confirm the checked-in module enables the renderer, and review the full refreshed Terraform plan for unrelated changes before approval. Record the deployed commit, preserve the current Terraform state version through the backend's approved backup process, and retain the reviewed plan. Risk includes scheduling new workers and reconciling unrelated drift. If the plan includes unexpected changes, stop before applying. If the apply causes a regression, have the deployment owner review a rollback plan from the last known-good deployment inputs and reconcile through the same workflow. Avoid restoring stale state as a routine rollback.
- Verify the backlog after workers start. Escalate for a scoped retry only if delivery evidence and task readbacks warrant it. Duplicate renders can consume worker capacity and repeat uploads. Preserve affected task IDs and statuses before any retry. Retry and rollback behavior were not checked in the source incident.

## Validation checklist

- [ ] Nomad shows the intended job and running allocations for eligible video nodes.
- [ ] Consul registers the renderer, and previously stuck tasks show advancing progress in repeat task snapshots.
- [ ] Previously affected sessions reach the expected terminal states and report URLs for required uploads.
- [ ] An authorized operator opens affected uploads in the supported viewer and verifies playback. The task API only establishes that URLs were reported.

## Not yet verified

- The deregistration mechanism and actor in the source incident. Look for job audit records and correlate them with deployment history.
- JetStream retention and final backlog completion after worker restoration.
- Playback from authenticated guest video storage.
