---
title:
slug:
services: []
tags: []            # e.g. jetstream, nomad, postgres
status: draft       # keep draft
last_verified:      # human sets only after recurrence validates the steps
applies_to: {}
source_incidents: []
---
## Symptoms
- What you see (alerts, log lines, metric shapes, user impact)

## Triage (read-only, in order)
1. Command or query → what a bad result looks like
   (LogQL / TraceQL / PromQL / nomad / consul / nats commands, copy-pasteable)

## Likely causes
| Cause | Evidence that confirms | Evidence that rules out |

## Remediation (HUMAN executes; agent never runs)
- Action → risk → rollback

## Validation checklist
- [ ] Metric/log/health check that proves it's fixed

## Not yet verified
- Anything the agent inferred but didn't confirm in the incident
