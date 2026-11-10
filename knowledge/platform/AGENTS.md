# AGENTS.md — platform/

## Purpose

`platform/` holds **reusable platform knowledge** for troubleshooting and root cause analysis (RCA):

- **Debug guides** (`docs/domains/`): how to debug a platform domain or feature (e.g. video-dge, rendering) and how to test it.
- **Flow docs** (`docs/flows/`): how a workflow moves across several microservices (sequence, contracts, failure points).

## How to use this folder (read path)

1. Read `INDEX.md` first. Do not scan the whole `docs/` tree.
2. Open only the docs whose "read when" line matches your task or symptom.
3. Follow `Related` links from those docs instead of searching broadly.
4. Treat docs with `status: stale` or an old `last_verified`(>3 months) as hints, not facts. Confirm against code, logs, or metrics.

## Scope boundary

In scope (belongs here):

- Cross-service behavior and end-to-end workflows
- Domain-level debugging procedures that apply to more than one service
- Reusable test procedures and how to read their results

Out of scope (keep in the owning service's repo/README):

- Single-service internals, setup, and API reference
- One-off incident write-ups (only the reusable lesson goes here, as a short entry under `Known incidents`)
- Anything that is just a copy of code, schemas, or configs. Link to the source instead.

## Writing rules

- Start from a template: `docs/_TEMPLATE-debug.md` or `docs/_TEMPLATE-flow.md`.
- Filenames are lowercase kebab-case, e.g. `video-dge.md`, `render-request-lifecycle.md`.
- Fill in the frontmatter completely. `INDEX.md` is built from it.
- Debug guides are organized by **symptom**, not by component.
- Every "likely cause" must include **how to confirm it** (exact query, command, log line, or metric) and what normal vs. abnormal looks like.
- Link to the source of truth (proto, OpenAPI, code path, dashboard) rather than copying details.
- Mark anything you have not verified with `(unverified)`.
- **Never** include secrets, tokens, credentials, or customer data. Use placeholders such as `<TRACE_ID>`.

## Maintenance rules

- After every RCA, update or add the relevant doc in the same change.
- When you edit a doc, update `last_verified` only if you actually re-verified its content.
- Add, rename, or remove a doc and `INDEX.md` in the same change.
- If you find a doc that is wrong, fix it or set `status: stale` and say why at the top.

## Definition of done for a doc

- [ ] Frontmatter complete
- [ ] Symptoms (debug) or sequence and failure points (flow) are filled in
- [ ] Each cause or failure point has a confirmation step
- [ ] Links point to real sources of truth
- [ ] No secrets
- [ ] `INDEX.md` updated
