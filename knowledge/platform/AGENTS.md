# Platform knowledge

Write reusable Silica platform knowledge that helps diagnosis workers understand symptoms, interpret evidence, and choose what to check next.

## Before you write

1. Search the `tags` and `components` metadata in `docs/`.
2. Update an existing document if it covers the symptom family. Do not create a second one.
3. Otherwise, copy [docs/_TEMPLATE.md](docs/_TEMPLATE.md) to `docs/<component>-<symptom-slug>.md`. Use lowercase and hyphens.

## Writing rules

- Cover one symptom family per document. Keep it to about 60 lines; split larger documents.
- Always include YAML metadata: `title`, `description`, `tags`, `components`, `last_verified`, and `source_incidents`. Describe what the document helps diagnose in one sentence, starting with "Use when:".
- Explain relevant platform behavior and diagnosis clues. State which environments or versions the knowledge applies to.
- Every fact needs evidence and a status of `verified` or `inferred`. Cite source code, configuration, or observed results. No evidence means `inferred`.
- Each "How to verify" entry needs an exact command or query and expected output. Mark untested checks as `untested`.
- Update `last_verified` only when you run the relevant check, not when editing prose. Use `null` if the knowledge has never been verified.
- Add source debrief filenames to `source_incidents` and link the debriefs under "Related docs".
- Remove or rewrite facts contradicted by new evidence. Do not leave conflicting facts together.
- Empty sections are fine. Write none instead of padding.
- Add or update the document's row in [INDEX.md](INDEX.md), linking the slug to `docs/<slug>.md`. Link related platform docs and runbooks when available.

## Tag and component vocabulary

Use the terms below. Add new terms here in the same change, in alphabetical order, one row per term.

- Use lowercase, hyphenated, singular terms: `nats`, not `NATS` or `NATS-JetStream`.
- Use one canonical name per thing. Record aliases in the Aliases column, not as separate terms.
- `components` identifies services, applications, infrastructure, and hardware. `tags` identifies symptoms and concepts.

### Components

| Term | Aliases | Kind |
| --- | --- | --- |
| consul | | infra |
| nats | jetstream | infra |
| nomad | | infra |
| postgres | postgresql | infra |
| traefik | | infra |
| unity | | application |
| video-dge | | service |
| video-server | | service |
| webcam | | hardware |

### Tags

| Term | Meaning |
| --- | --- |
| consumer-lag | Consumer falling behind its stream |
| high-latency | Slower than expected end to end |
| no-logs | Expected logs absent |
| quorum-loss | JetStream or Raft group lost majority |
| restart-loop | Allocation or process keeps restarting |
| stream-stall | Stream stops accepting or delivering |
| trace-gap | Broken or missing trace correlation |

These are seed terms; update the vocabulary as platform knowledge grows.

## Stale docs

- If `last_verified` is older than 90 days, treat facts as `inferred` until re-checked.
