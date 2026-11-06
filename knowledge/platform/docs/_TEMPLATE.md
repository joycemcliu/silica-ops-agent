---
title: <Topic>
description: >
    <One sentence. Start with "Use when: <symptom>". Say what it helps diagnose.>
tags: [] # symptom keywords and platform concepts. Use only terms from ../AGENTS.md
components: [] # affected parts. Use only names from the ../AGENTS.md vocabulary
last_verified: null # YYYY-MM-DD when the relevant check was run
source_incidents: [] # incident file names without .md
---

# <Topic>

<!-- One symptom family per doc. Max ~60 lines. Split if bigger. -->

## When to use

- <Symptoms or questions this doc helps investigate.>
- Applies to: <components, environments, versions; include limits.>

## Platform behavior

- <Behavior, dependency, or data flow.> Evidence: <source path, config key, or exact command + output>. Status: <verified / inferred>.

## Diagnosis clues

| Observation | What it suggests | How to verify (exact command/query → expected output) | Fix / next step | Status |
| --- | --- | --- | --- | --- |
| <Symptom, log, metric, or state> | <Possible explanation> | `<command>` → `<expected>`. Mark untested. | <Remedy, or `none known`> | <verified / inferred> |

## Unknowns

- <Missing evidence or open question. Write `none` if empty.>

## Related docs

- <Related platform docs, runbooks.>
- Source debriefs: <link each debrief that produced a fact in this doc.>
