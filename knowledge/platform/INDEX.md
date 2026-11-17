# INDEX — platform/

Start here. Each entry says **when to read** the doc. Rules for using and maintaining this folder: see [AGENTS.md](AGENTS.md).

## Templates

| File                                                | Use for                                       |
| --------------------------------------------------- | --------------------------------------------- |
| [docs/\_TEMPLATE-debug.md](docs/_TEMPLATE-debug.md) | Debug / testing guide for a domain or feature |
| [docs/\_TEMPLATE-flow.md](docs/_TEMPLATE-flow.md)   | Workflow across several microservices         |

## Domain debug guides (`docs/domains/`)

| Doc                                                      | Read when                                                                 | Services                         | Status |
| -------------------------------------------------------- | ------------------------------------------------------------------------- | -------------------------------- | ------ |
| [Session inspection](docs/domains/session-inspection.md) | Session identity, room, timing, mode, or status is unclear                | session-server                   | draft  |
| [Video inspection](docs/domains/video-inspection.md)     | Locate video task progress, dependency waits, errors, or reported outputs | video-server, video-dge-renderer | draft  |

## Flow docs (`docs/flows/`)

| Doc                                                                                | Read when                                                                                               | Services                                                 | Status |
| ---------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- | -------------------------------------------------------- | ------ |
| [Video render queue delivery flow](docs/flows/nats-video-render-queue-delivery.md) | Video tasks stay Queuing despite healthy workers or zero consumer pending; locate the stalled handoff   | video-server, nats, video-dge-renderer                   | draft  |
| [Unity launch command delivery flow](docs/flows/unity-launch-command-delivery.md)  | Unity launch stalls across rooms; distinguish queue delivery, Nomad execution and application readiness | session-server, nats, experience-conductor, nomad, unity | draft  |

## By symptom (quick lookup)

| Symptom                                                                                              | Go to                                                                                          |
| ---------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| Session identity, timing, mode, or status is unclear                                                 | [Session inspection](docs/domains/session-inspection.md)                                       |
| Need individual video tasks, dependencies, progress, or errors                                       | [Video inspection](docs/domains/video-inspection.md)                                           |
| Runnable video tasks stay Queuing despite healthy workers                                            | [Queue delivery failure points](docs/flows/nats-video-render-queue-delivery.md#failure-points) |
| Consumer pending is zero despite retained matching messages                                          | [Queue delivery failure points](docs/flows/nats-video-render-queue-delivery.md#failure-points) |
| Dependent highlights stay Pending while child tasks stop progressing                                 | [Queue delivery sequence](docs/flows/nats-video-render-queue-delivery.md#sequence)             |
| Unity remains Checking then Error across rooms; launch consumers panic; broker write/quorum failures | [Unity launch failure points](docs/flows/unity-launch-command-delivery.md#failure-points)      |
