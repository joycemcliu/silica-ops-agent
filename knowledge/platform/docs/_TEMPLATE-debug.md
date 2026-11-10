---
title: <Domain or feature> debugging guide
type: debug
domain: <e.g. video-dge>
services: [<service-a>, <service-b>]
symptoms:
  - <short symptom phrase, e.g. "render stuck in pending">
  - <another symptom>
last_verified: YYYY-MM-DD
status: draft # draft | verified | stale
---

# <Domain or feature> debugging guide

> **Read when:** <one line, e.g. "renders hang, frames are dropped, or DGE jobs never complete">

## Overview

<2-4 bullet points: what this domain does and which services are involved. Link to the related flow doc for the full picture.>

## Prerequisites / access

- Dashboards: <link>
- Log source and label conventions: <e.g. Loki `{app="dge"}`>
- Metrics: <e.g. Prometheus metric names>
- Tools or permissions needed: <...>

---

## Symptom: <symptom 1, as an observer would describe it>

### Quick triage (first 3 checks)

1. <Check 1: exact command, query, or dashboard panel>
2. <Check 2>
3. <Check 3>

### Likely causes

#### Cause A: <name>

- **Why it happens:** <short explanation>
- **How to confirm:**
  - Query / command: `<exact query or command>`
  - **Normal:** <what healthy looks like>
  - **Abnormal:** <what confirms this cause>
- **Fix / mitigation:** <steps, or link to runbook>

#### Cause B: <name>

- **Why it happens:**
- **How to confirm:**
  - Query / command: `<...>`
  - **Normal:**
  - **Abnormal:**
- **Fix / mitigation:**

### If none of the above match

<Where to look next, who to escalate to, what data to collect first (trace IDs, timestamps, job IDs).>

---

## Symptom: <symptom 2>

<Repeat the structure above.>

---

## How to test this domain

<Reusable test procedure: setup, inputs, how to run, expected results, how to read failures.>

1. <Step>
2. <Step>
3. Expected result: <...>

## Related

- Flow: [<flow doc>](../flows/<file>.md)
- Source of truth: <proto / OpenAPI / code path / dashboard>
- Other guides: <...>

## Known incidents

Short, dated, and only the reusable lesson. No secrets.

| Date       | What happened | Root cause | Lesson / doc change |
| ---------- | ------------- | ---------- | ------------------- |
| YYYY-MM-DD | <...>         | <...>      | <...>               |
