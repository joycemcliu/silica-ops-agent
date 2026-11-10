# INDEX — platform/

Start here. Each entry says **when to read** the doc. Rules for using and maintaining this folder: see [AGENTS.md](AGENTS.md).

## Templates

| File                                                | Use for                                       |
| --------------------------------------------------- | --------------------------------------------- |
| [docs/\_TEMPLATE-debug.md](docs/_TEMPLATE-debug.md) | Debug / testing guide for a domain or feature |
| [docs/\_TEMPLATE-flow.md](docs/_TEMPLATE-flow.md)   | Workflow across several microservices         |

## Domain debug guides (`docs/domains/`)

No domain debug guides yet. For queue-delivery triage, follow the runbook linked from the flow below.

## Flow docs (`docs/flows/`)

| Doc                                                                                | Read when                                                                                             | Services                               | Status |
| ---------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- | -------------------------------------- | ------ |
| [Video render queue delivery flow](docs/flows/nats-video-render-queue-delivery.md) | Video tasks stay Queuing despite healthy workers or zero consumer pending; locate the stalled handoff | video-server, nats, video-dge-renderer | draft  |

## By symptom (quick lookup)

| Symptom                                                              | Go to                                                                                          |
| -------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| Runnable video tasks stay Queuing despite healthy workers            | [Queue delivery failure points](docs/flows/nats-video-render-queue-delivery.md#failure-points) |
| Consumer pending is zero despite retained matching messages          | [Queue delivery failure points](docs/flows/nats-video-render-queue-delivery.md#failure-points) |
| Dependent highlights stay Pending while child tasks stop progressing | [Queue delivery sequence](docs/flows/nats-video-render-queue-delivery.md#sequence)             |
